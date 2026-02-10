"""
The interfaces to chat with users or other agents.
"""
import re
import io
import random
import requests
import base64
from threading import Thread
import structlog

try:
    import zulip
    from PIL import Image
    ZULIP_AVAILABLE = True
except ImportError:
    ZULIP_AVAILABLE = False
    zulip = None
    Image = None

from mobileclaw.utils.interface import UniInterface
from .chat_utils import Chat_Client

logger = structlog.get_logger(__name__)


class Zulip_Client(Chat_Client):
    def __init__(self, agent):
        super().__init__(agent)
        from mobileclaw.agent import AutoAgent
        assert isinstance(agent, AutoAgent)
        self._tag = 'chat.client'
        self.org_manager_email = self.agent.config.chat_zulip_org_manager
        self.zulip_name = None
        self.zulip_email = None
        self._serving_thread = None
        # Maintain mapping of user names/ids to email addresses
        self._user_mapping = {}  # {name: email, id: email}
        # Log receiver for send_to_log messages
        self.log_receiver = None  # Set via /log_here command
        # Report receiver for send_message when receiver is None
        self.report_receiver = None  # Set via /report_here command

    def _open(self):
        if not ZULIP_AVAILABLE:
            logger.error('Zulip SDK not installed. Run: pip install zulip', action='start zulip client', status='failed')
            return

        try:
            self.client = zulip.Client(
                email=self.agent.config.chat_zulip_email,
                api_key=self.agent.config.chat_zulip_key,
                site=self.agent.config.chat_zulip_site
            )
            self.server_settings = self.client.get_server_settings()
            self.server_url = self.server_settings['realm_uri']
            self.profile = self.client.get_profile()
            self.zulip_name = self.profile['full_name']
            self.zulip_email = self.client.email
            if (self.profile.get('code') == 'UNAUTHORIZED'):
                logger.error('Zulip_Client UNAUTHORIZED', action='start zulip client', status='failed')
                self.client = None
            else:
                logger.debug('Zulip_Client started', action='start zulip client', status='done')
                self._serving_thread = Thread(target=self._start_serving)
                self._serving_thread.start()
        except Exception as e:
            logger.exception(f'Zulip_Client not started: {e}', action='start zulip client', status='failed')
            self.client = None

    def _close(self):
        if self._serving_thread is not None:
            self._serving_thread.join()

    def _start_serving(self):
        self.client.call_on_each_event(self._handle_event, event_types=['message'])

    def send_reply(self, content, previous_message):
        if previous_message['type'] == 'private':
            msg = {
                'type': 'private',
                'to': previous_message['sender_email'],
                'content': content,
            }
        else:
            msg = {
                'type': 'stream',
                'to': previous_message['display_recipient'],
                'subject': previous_message['subject'],
                'content': content,
            }
        self.client.send_message(msg)

    def _handle_event(self, event):
        event_type = event['type']
        if event_type != 'message':
            return

        msg = event['message']
        content = msg['content'].strip()

        if msg['sender_email'] in [self.zulip_email, 'notification-bot@zulip.com']:
            # Ignoring message sent by myself and notification bot
            return

        agent_name = self.zulip_name
        sender_email = msg['sender_email']
        sender_id = msg['sender_id']
        sender_name = msg['sender_full_name']

        # Handle commands (only from org_manager)
        if content.startswith('/') and sender_email == self.org_manager_email:
            self._handle_command(content.strip(), msg)
            return

        if msg['type'] == 'private':
            sender_name_new = sender_name
        else:
            if re.search(fr"@\*\*{agent_name}\*\*", content) or re.search(fr"@{agent_name}", content):
                # The agent has been mentioned
                pass
            group_name = msg['display_recipient']
            sender_name_new = f"group:{group_name}"

        # Maintain user mapping for future message sending
        self._user_mapping[sender_name] = sender_email
        self._user_mapping[str(sender_id)] = sender_email
        self._user_mapping[sender_email] = sender_email

        # self.send_reply(f'You said: {content}', msg)

        # Handle the message with "group:" prefix for sender
        history_messages = self.get_history_messages(msg)
        history_content = "\n".join([f'[{m[2]}] {m[0]}: {m[1]}' for m in history_messages])
        self.agent.handle_message(content, history=history_content, sender=sender_name_new, channel='zulip')

    def _handle_command(self, command: str, msg):
        """
        Handle bot commands from org_manager.

        Args:
            command: The command string (e.g., "/log_here")
            msg: The message object
        """
        try:
            # Determine receiver based on message type
            if msg['type'] == 'private':
                receiver = msg['sender_email']
            else:
                # For stream messages, use "group:stream_name" format
                receiver = f"group:{msg['display_recipient']}"

            if command.endswith("/log_here"):
                # Set local log receiver
                self.log_receiver = receiver
                # Set global log channel
                self.agent.chat.log_channel = 'zulip'
                response_text = "✅ Log receiver set to this chat. Logs will be sent here."
                logger.info(f"Log receiver set to: {receiver}, global log channel set to zulip")

            elif command.endswith("/stop_log_here"):
                self.log_receiver = None
                # Clear global log channel if it was zulip
                if self.agent.chat.log_channel == 'zulip':
                    self.agent.chat.log_channel = None
                response_text = "✅ Log receiver cleared. Logs will no longer be sent."
                logger.info("Log receiver cleared")

            elif command.endswith("/report_here"):
                # Set local report receiver
                self.report_receiver = receiver
                # Set global report channel
                self.agent.chat.report_channel = 'zulip'
                response_text = "✅ Report receiver set to this chat. Progress reports will be sent here."
                logger.info(f"Report receiver set to: {receiver}, global report channel set to zulip")

            elif command.endswith("/stop_report_here"):
                self.report_receiver = None
                # Clear global report channel if it was zulip
                if self.agent.chat.report_channel == 'zulip':
                    self.agent.chat.report_channel = None
                response_text = "✅ Report receiver cleared. Reports will be sent to org_manager."
                logger.info("Report receiver cleared")

            else:
                # Unknown command
                response_text = (
                    f"❓ Unknown command: {command}\n\n"
                    "Available commands:\n"
                    "/log_here - Set this chat as log receiver\n"
                    "/stop_log_here - Stop sending logs to this chat\n"
                    "/report_here - Set this chat as report receiver\n"
                    "/stop_report_here - Stop sending reports to this chat"
                )

            # Send response as reply
            self.send_reply(response_text, msg)

        except Exception as e:
            logger.exception(f"Error handling command: {e}")
    
    def send_message(self, message, receiver=None, subject=None):
        """
        Send a message to receiver.

        Args:
            message: Can be a string, an image/file (represented as a path) or a list of them
            receiver: Name/id of the message receiver (can be a user or a group/stream)
                     Use "group:" prefix for stream/group messages (e.g., "group:MyStream")
            subject: Subject/topic for stream messages (optional for private messages)
        """
        try:
            if receiver is None:
                # Use report_receiver if set, otherwise default to org_manager
                if self.report_receiver:
                    receiver = self.report_receiver
                else:
                    receiver = self.org_manager_email
            # Check if receiver has "group:" prefix
            if receiver.startswith("group:"):
                # Stream message - remove the prefix
                stream_name = receiver[6:]  # Remove "group:" prefix
                msg = {
                    'type': 'stream',
                    'to': stream_name,
                    'subject': subject if subject else 'General',
                    'content': message,
                }
            else:
                # Private message to user
                # Get email if receiver is a name/id, otherwise use receiver as email
                receiver_email = self._user_mapping.get(receiver, receiver)
                msg = {
                    'type': 'private',
                    'to': receiver_email,
                    'content': message,
                }
            result = self.client.send_message(msg)
            if result.get('result') != 'success':
                err_msg = ''
                if 'Invalid email' in result.get('msg', ''):
                    err_msg = 'The `receiver` param should either be a user name/id/email or a group name with "group:" prefix'
                raise Exception(f'send_message failed: {result}. {err_msg}')
            return result
        except Exception as e:
            # logger.exception(f'Error sending message: {e}', action='send_message', status='failed')
            raise

    def get_history_messages(self, msg, max_previous_messages=10):
        client = self.client
        if msg['type'] == 'private':
            query = {
                'anchor': msg['id'],
                'num_before': max_previous_messages,  # adjust this value as needed
                'num_after': 0,
                'apply_markdown': False,
                'include_anchor': False,
                'narrow': [{'operand': msg['sender_email'], 'operator': 'pm-with'}],
            }
        else:
            narrow = [
                {'operand': msg['display_recipient'], 'operator': 'stream'},
                {'operand': msg['subject'], 'operator': 'topic'}
            ]

            query = {
                'anchor': msg['id'],
                'num_before': max_previous_messages,  # adjust this value as needed
                'num_after': 0,
                'apply_markdown': False,
                'include_anchor': False,
                'narrow': narrow,
            }

        previous_messages = client.get_messages(query)['messages']
        # previous_messages.reverse()
        messages_to_return = []
        for msg in previous_messages:
            # Convert Unix timestamp to human-readable format
            from datetime import datetime
            timestamp = datetime.fromtimestamp(msg['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            messages_to_return.append((msg['sender_full_name'], msg['content'], timestamp))
        return messages_to_return

    # Function to convert messages to gpt4v format
    def convert_messages_vision(self, messages):
        new_messages = []
        # Updated pattern to match file paths with image extensions
        # url_pattern = r'\[IMG\]\(([^\s]+)\)'
        # url_pattern = r'\[\]\(([^\s]+\.(?:jpg|jpeg|png|gif|webp))\)'
        url_pattern = r'\[IMG\]\(([^\s]+)\)|\[.*?\]\(([^\s]+\.(?:jpg|jpeg|png|webp))\)'

        for message in messages:
            new_content = []
            last_index = 0
            for match in re.finditer(url_pattern, message["content"]):
                # Add text before the image URL
                if match.start() != last_index:
                    new_content.append({"type": "text", "text": message["content"][last_index:match.start()]})
                # Add image URL
                image_url = match.group(1) if match.group(1) else match.group(2)
                if image_url.startswith('/user_uploads'):   # user-uploaded images
                    try:
                        server_image_url = f'{self.server_url}/{image_url}'
                        r = self.client.session.get(server_image_url)
                        with Image.open(io.BytesIO(r.content)) as image:
                            image_format = image.format.upper()
                            if image_format not in ['JPEG', 'JPG', 'PNG', 'WEBP']:
                                image_format = 'JPEG'  # Default to JPEG if format is not one of the common types
                            
                            # Convert image to RGB if it's not already in a compatible format
                            if image.mode == 'P' or image.mode == 'RGBA' and image_format in ['JPEG', 'JPG']:
                                image = image.convert('RGB')
                            
                            image_stream = io.BytesIO()
                            image.save(image_stream, format=image_format)
                            image_base64 = base64.b64encode(image_stream.getvalue()).decode("utf-8")
                            image_url = f'data:image/{image_format.lower()};base64,{image_base64}'
                    except Exception as e:
                        logger.exception(f'Failed to convert image: {e}', action='send_reply', status='failed')
                        continue
                new_content.append({"type": "image_url", "image_url": {"url": image_url}})
                last_index = match.end()
            # Add any remaining text after the last image URL
            if last_index != len(message["content"]):
                new_content.append({"type": "text", "text": message["content"][last_index:]})
            new_messages.append({"role": message["role"], "content": new_content})
        return new_messages

    def _is_admin(self, msg):
        member = self.client.get_user_by_id(msg['sender_id'])
        return member.get("user", {}).get("is_admin")
    
    def _check_whether_stream_exists(self, stream_name):
        """
        Check whether a Zulip stream with the given name exists.

        Args:
            stream_name: Name of the stream to check

        Returns:
            True if the stream exists, False otherwise
        """
        try:
            result = self.client.get_stream_id(stream_name)
            # If get_stream_id returns successfully, the stream exists
            if result.get('result') == 'success':
                return True
            return False
        except Exception as e:
            logger.debug(f'Stream {stream_name} does not exist: {e}',
                        action='_check_whether_stream_exists', status='not_found')
            return False

    def _create_stream(self, stream_name, description=""):
        """
        Creates a Zulip stream with the given name.
        Adds the agent and the bound user as members.

        Args:
            stream_name: Name of the stream to create
            description: Optional description for the stream

        Returns:
            Result from the Zulip API
        """
        # Get the agent's email
        agent_email = self.client.email

        # Get the user's email from bind_user
        org_manager_email = self.org_manager_email

        # Create the stream and subscribe both agent and user
        subscribers = [agent_email]
        if org_manager_email:
            subscribers.append(org_manager_email)

        try:
            result = self.client.add_subscriptions(
                streams=[{
                    'name': stream_name,
                    'description': description
                }],
                principals=subscribers
            )
            logger.debug(f'Stream created: {stream_name}', action='create_stream', status='success')
            return result
        except Exception as e:
            logger.exception(f'Failed to create stream {stream_name}: {e}', action='create_stream', status='failed')
            raise

    def _send_to_stream(self, stream_name, message, subject="General", description=None):
        """
        Helper method to send a message to a stream, creating it if it doesn't exist.

        Args:
            stream_name: Name of the stream
            message: Message content to send
            subject: Subject/topic for the message (default: "General")
            description: Description for the stream if it needs to be created
        """
        # Check if stream exists, create if it doesn't
        if stream_name.startswith('group:'):
            stream_name = stream_name[6:]
        if not self._check_whether_stream_exists(stream_name):
            logger.debug(f'Stream does not exist, creating: {stream_name}')
            try:
                stream_description = description or f"Stream for {stream_name}"
                self._create_stream(stream_name, description=stream_description)
            except Exception as e:
                logger.exception(f'Failed to create stream: {e}')
                raise

        # Send the message
        try:
            self.send_message(message, receiver=f'group:{stream_name}', subject=subject)
            logger.debug(f'Message sent to stream: {stream_name}', action='_send_to_stream', status='success')
        except Exception as e:
            logger.exception(f'Failed to send message to stream {stream_name}: {e}')
            raise

    def send_to_org(self, message, subject="General"):
        """
        Sends a message to the organization stream.
        Creates the stream if it doesn't exist.

        Args:
            message: Message content to send
            subject: Subject/topic for the message (default: "General")
        """
        stream_name = f'{self.agent.org_name}'
        description = f"Organization stream of {self.agent.org_name}"
        self._send_to_stream(stream_name, message, subject, description)

    def send_to_log(self, message, subject="Log"):
        """
        Sends a message to the self-reporting stream.
        If log_receiver is set, sends to that receiver instead.

        Args:
            message: Message content to send
            subject: Subject/topic for the message (default: "Log")
        """
        if self.log_receiver is None:
            # Default behavior: send to agent's self-reporting stream
            stream_name = f'{self.agent.name}'
            description = f"Self-reporting stream of {self.agent.name}"
            self._send_to_stream(stream_name, message, subject, description)
        else:
            # Send to the configured log receiver
            try:
                self.send_message(message, receiver=self.log_receiver, subject=subject)
            except Exception as e:
                logger.exception(f'Error sending to log receiver: {e}')

