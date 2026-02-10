"""
The Lark/Feishu chat client implementation.
"""
import re
import json
import asyncio
from collections import OrderedDict
import structlog
import time

from mobileclaw.utils.interface import UniInterface
from .chat_utils import Chat_Client

logger = structlog.get_logger(__name__)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import *
    from lark_oapi.api.contact.v3 import *
    from PIL import Image
    LARK_AVAILABLE = True
except ImportError:
    LARK_AVAILABLE = False
    lark = None
    Image = None

# Message type display mapping
MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


class Lark_Client(Chat_Client):
    def __init__(self, agent):
        super().__init__(agent)
        from mobileclaw.agent import AutoAgent
        assert isinstance(agent, AutoAgent)
        self._tag = 'chat.client.lark'
        self.org_manager_open_id = self.agent.config.chat_lark_org_manager
        self.lark_name = None
        self.lark_open_id = None
        self._serving_thread = None
        self._ws_thread = None
        self._stop_serving = False
        self._ws_client = None
        self._loop = None
        # Message deduplication with OrderedDict (maintains insertion order)
        self._processed_message_ids = OrderedDict()
        # Maintain mapping of user names/ids to open_ids
        self._user_mapping = {}  # {name: open_id, id: open_id}
        self._group_mapping = {}  # {group_name: chat_id}
        # Log receiver for send_to_log messages
        self.log_receiver = None  # Set via /log_here command
        # Report receiver for send_message when receiver is None
        self.report_receiver = None  # Set via /report_here command

    def _open(self):
        if not LARK_AVAILABLE:
            logger.error('Lark SDK not installed. Run: pip install lark_oapi', action='start lark client', status='failed')
            return

        if not self.agent.config.chat_lark_app_id or not self.agent.config.chat_lark_app_secret:
            logger.error('Lark app_id and app_secret not configured', action='start lark client', status='failed')
            return

        try:
            # Initialize Lark client with app credentials
            self.client = lark.Client.builder() \
                .app_id(self.agent.config.chat_lark_app_id) \
                .app_secret(self.agent.config.chat_lark_app_secret) \
                .log_level(lark.LogLevel.INFO) \
                .build()

            logger.debug('Lark_Client initialized, verifying credentials',
                       action='start lark client', status='starting')

            # Verify credentials and convert org_manager identifier to open_id
            self._verify_and_get_open_ids()

            logger.debug('Lark_Client verified, starting WebSocket connection',
                       action='start lark client', status='starting')

            # Start WebSocket connection in separate thread
            from threading import Thread
            self._serving_thread = Thread(target=self._start_serving)
            self._serving_thread.start()

        except Exception as e:
            logger.exception(f'Lark_Client not started: {e}', action='start lark client', status='failed')
            self.client = None

    def _close(self):
        self._stop_serving = True
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception as e:
                logger.warning(f'Error stopping WebSocket client: {e}')
        if self._serving_thread is not None:
            self._serving_thread.join(timeout=5)

    def _verify_and_get_open_ids(self):
        """
        Verify credentials, get bot info, and convert org_manager identifier (email/phone) to open_id.
        """
        try:
            # Set bot name (bots don't have traditional open_ids in Lark)
            self.lark_name = f"Bot_{self.agent.config.chat_lark_app_id}"
            self.lark_open_id = None  # Bots are auto-added to chats they create
            logger.debug(f'Bot name set: {self.lark_name}')

            # Convert org_manager identifier to open_id if configured
            if not self.org_manager_open_id:
                logger.debug('No org_manager configured, skipping org_manager verification')
                return

            org_manager = self.org_manager_open_id
            emails = []
            mobiles = []

            # Simple heuristic: if contains @, it's email; if all digits (with optional +), it's phone
            if '@' in org_manager:
                emails = [org_manager]
            elif org_manager.replace('+', '').replace('-', '').replace(' ', '').isdigit():
                # Clean phone number (remove spaces, dashes)
                mobiles = [org_manager.replace('-', '').replace(' ', '')]
            else:
                # Assume it's already an open_id
                logger.debug(f'Org manager appears to be an open_id: {org_manager}')
                return

            # Build request to convert email/phone to open_id
            request = BatchGetIdUserRequest.builder() \
                .user_id_type("open_id") \
                .request_body(BatchGetIdUserRequestBody.builder()
                    .emails(emails if emails else None)
                    .mobiles(mobiles if mobiles else None)
                    .include_resigned(False)
                    .build()) \
                .build()

            # Send request
            response = self.client.contact.v3.user.batch_get_id(request)

            if not response.success():
                logger.error(
                    f"Failed to get open_id for org_manager: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                raise Exception(f'Failed to verify org_manager: {response.msg}')

            # Extract open_id from response
            if response.data and response.data.user_list:
                for user in response.data.user_list:
                    if user.user_id:
                        self.org_manager_open_id = user.user_id
                        logger.info(f'Converted org_manager to open_id: {self.org_manager_open_id}')
                        return

            logger.warning(f'No user found for org_manager: {org_manager}')

        except Exception as e:
            logger.exception(f'Error in verification: {e}')
            raise

    def _start_serving(self):
        """Start WebSocket long connection for receiving messages."""
        try:
            # Create async event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            # Create event handler
            event_handler = lark.EventDispatcherHandler.builder(
                "",  # encrypt_key (optional)
                "",  # verification_token (optional)
            ).register_p2_im_message_receive_v1(
                self._on_message_sync
            ).build()

            # Create WebSocket client
            self._ws_client = lark.ws.Client(
                self.agent.config.chat_lark_app_id,
                self.agent.config.chat_lark_app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO
            )

            logger.info('Lark WebSocket connection starting (no public IP required)')

            # Start WebSocket client (blocking call)
            self._ws_client.start()

        except Exception as e:
            logger.exception(f'Error in WebSocket serving loop: {e}')
        finally:
            if self._loop:
                self._loop.close()

    def _on_message_sync(self, data):
        """
        Sync handler for incoming messages (called from WebSocket thread).
        Schedules async handling in the event loop.
        """
        try:
            # Create task in the current event loop (WebSocket's loop)
            asyncio.create_task(self._on_message(data))
        except Exception as e:
            logger.exception(f'Error scheduling message handler: {e}')

    async def _on_message(self, data):
        """Handle incoming message from Lark/Feishu."""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # Deduplication check
            message_id = message.message_id
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None

            # Trim cache: keep most recent 500 when exceeds 1000
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)

            # Skip bot messages
            sender_type = sender.sender_type
            if sender_type == "bot":
                return

            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type  # "p2p" or "group"
            msg_type = message.message_type

            # Add reaction to indicate "seen"
            await self._add_reaction(message_id, "THUMBSUP")

            # Parse message content
            if msg_type == "text":
                try:
                    content = json.loads(message.content).get("text", "")
                except json.JSONDecodeError:
                    content = message.content or ""
            else:
                content = MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")

            if not content:
                return

            # Handle commands (only from org_manager)
            if content.startswith('/') and sender_id == self.org_manager_open_id:
                await self._handle_command(content.strip(), chat_id, message_id)
                return

            # Determine sender name for routing
            if chat_type == "p2p":
                sender_name = sender_id
            else:
                # Group message
                sender_name = f"group:{chat_id}"
                self._group_mapping[chat_id] = chat_id

            # Maintain user mapping
            self._user_mapping[sender_id] = sender_id

            # Create simple message object
            class SimpleMessage:
                def __init__(self, msg_id, sender, content, chat_id):
                    self.message_id = msg_id
                    self.sender = sender
                    self.content = content
                    self.chat_id = chat_id

            msg = SimpleMessage(message_id, sender_id, content, chat_id)

            # Get history messages
            history_messages = self.get_history_messages(msg)
            history_content = "\n".join([f'[{m[2]}] {m[0]}: {m[1]}' for m in history_messages])

            # Handle the message
            if hasattr(self.agent, 'handle_message'):
                self.agent.handle_message(
                    message=content,
                    history=history_content,
                    sender=sender_name,
                    channel='lark'
                )

        except Exception as e:
            logger.exception(f'Error processing Lark message: {e}')

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP"):
        """
        Add a reaction emoji to a message (non-blocking).

        Common emoji types: THUMBSUP, OK, EYES, DONE, OnIt, HEART
        """
        try:
            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                ).build()

            response = self.client.im.v1.message_reaction.create(request)

            if not response.success():
                logger.debug(f"Failed to add reaction: code={response.code}, msg={response.msg}")
            else:
                logger.debug(f"Added {emoji_type} reaction to message {message_id}")
        except Exception as e:
            logger.debug(f"Error adding reaction: {e}")

    async def _handle_command(self, command: str, chat_id: str, message_id: str):
        """
        Handle bot commands from org_manager.

        Args:
            command: The command string (e.g., "/log_here")
            chat_id: The chat ID where the command was sent
            message_id: The message ID to reply to
        """
        try:
            if command.endswith("/log_here"):
                self.log_receiver = chat_id
                # Set global log channel
                self.agent.chat.log_channel = 'lark'
                response_text = f"✅ Log receiver set to this chat. Logs will be sent here."
                logger.info(f"Log receiver set to chat_id: {chat_id}, global log channel set to lark")

            elif command.endswith("/stop_log_here"):
                self.log_receiver = None
                # Clear global log channel if it was lark
                if self.agent.chat.log_channel == 'lark':
                    self.agent.chat.log_channel = None
                response_text = f"✅ Log receiver cleared. Logs will no longer be sent."
                logger.info("Log receiver cleared")

            elif command.endswith("/report_here"):
                self.report_receiver = chat_id
                # Set global report channel
                self.agent.chat.report_channel = 'lark'
                response_text = f"✅ Report receiver set to this chat. Progress reports will be sent here."
                logger.info(f"Report receiver set to chat_id: {chat_id}, global report channel set to lark")

            elif command.endswith("/stop_report_here"):
                self.report_receiver = None
                # Clear global report channel if it was lark
                if self.agent.chat.report_channel == 'lark':
                    self.agent.chat.report_channel = None
                response_text = f"✅ Report receiver cleared. Reports will be sent to org_manager."
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
            await self._send_text_reply(response_text, message_id)

        except Exception as e:
            logger.exception(f"Error handling command: {e}")

    async def _send_text_reply(self, text: str, message_id: str):
        """Send a text reply to a message."""
        try:
            card = self._build_card(text)
            card_content = json.dumps(card, ensure_ascii=False)

            request = ReplyMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(ReplyMessageRequestBody.builder()
                    .content(card_content)
                    .msg_type("interactive")
                    .build()) \
                .build()

            response = self.client.im.v1.message.reply(request)

            if not response.success():
                logger.debug(f"Failed to send reply: {response.msg}")
        except Exception as e:
            logger.debug(f"Error sending text reply: {e}")

    def send_reply(self, content, previous_message):
        """Send a reply to a previous message."""
        try:
            # Build card with markdown support
            card = self._build_card(content)
            card_content = json.dumps(card, ensure_ascii=False)

            request = ReplyMessageRequest.builder() \
                .message_id(previous_message.message_id) \
                .request_body(ReplyMessageRequestBody.builder()
                    .content(card_content)
                    .msg_type("interactive")
                    .build()) \
                .build()

            response = self.client.im.v1.message.reply(request)

            if not response.success():
                raise Exception(f'send_reply failed: {response.msg}')
        except Exception as e:
            logger.exception(f'Error sending reply: {e}', action='send_reply', status='failed')
            raise

    # Regex to match markdown tables (header + separator + data rows)
    _TABLE_RE = re.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
        re.MULTILINE,
    )

    @staticmethod
    def _parse_md_table(table_text: str):
        """Parse a markdown table into a Feishu table element."""
        lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 3:
            return None
        split = lambda l: [c.strip() for c in l.strip("|").split("|")]
        headers = split(lines[0])
        rows = [split(l) for l in lines[2:]]
        columns = [{"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"}
                   for i, h in enumerate(headers)]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": columns,
            "rows": [{f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))} for r in rows],
        }

    def _build_card_elements(self, content: str):
        """Split content into markdown + table elements for Feishu card."""
        elements, last_end = [], 0
        for m in self._TABLE_RE.finditer(content):
            before = content[last_end:m.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            table = self._parse_md_table(m.group(1))
            elements.append(table or {"tag": "markdown", "content": m.group(1)})
            last_end = m.end()
        remaining = content[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})
        return elements or [{"tag": "markdown", "content": content}]

    def _build_card(self, content: str):
        """Build a Feishu card with markdown + table support."""
        elements = self._build_card_elements(content)
        return {
            "config": {"wide_screen_mode": True},
            "elements": elements,
        }
    
    def send_message(self, message, receiver=None, subject=None):
        """
        Send a message to receiver.

        Args:
            message: Can be a string, an image/file (represented as a path) or a list of them
            receiver: Name/id of the message receiver (can be a user or a group/chat)
                     Use "group:" prefix for group messages (e.g., "group:chat_id")
            subject: Subject/topic for group messages (optional)
        """
        try:
            if receiver is None:
                # Use report_receiver if set, otherwise default to org_manager
                if self.report_receiver:
                    receiver = f"group:{self.report_receiver}"
                else:
                    receiver = self.org_manager_open_id

            # Check if receiver has "group:" prefix
            if receiver.startswith("group:"):
                # Group message - remove the prefix
                chat_id = receiver[6:]  # Remove "group:" prefix
                receive_id_type = "chat_id"
                receive_id = chat_id
            else:
                # Private message to user
                # Get open_id if receiver is a name/id, otherwise use receiver as open_id
                receive_id = self._user_mapping.get(receiver, receiver)
                receive_id_type = "open_id"

            # Prepare message content with card format for rich formatting
            if isinstance(message, str):
                # Build card with markdown + table support
                card = self._build_card(message)
                msg_content = json.dumps(card, ensure_ascii=False)
                msg_type = "interactive"
            else:
                # For now, only support text messages
                card = self._build_card(str(message))
                msg_content = json.dumps(card, ensure_ascii=False)
                msg_type = "interactive"

            # Build and send request
            request = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(msg_content)
                    .build()) \
                .build()

            response = self.client.im.v1.message.create(request)

            if not response.success():
                err_msg = ''
                if 'Invalid' in response.msg:
                    err_msg = 'The `receiver` param should either be a user open_id or a chat_id with "group:" prefix'
                logger.error(
                    f"Failed to send Lark message: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}. {err_msg}"
                )
                raise Exception(f'send_message failed: {response.msg}. {err_msg}')
            else:
                logger.debug(f"Lark message sent to {receive_id}")

            return response

        except Exception as e:
            logger.exception(f'Error sending message: {e}', action='send_message', status='failed')
            raise

    def get_history_messages(self, msg, max_previous_messages=10):
        """
        Get history messages from a conversation.

        Args:
            msg: The current message object
            max_previous_messages: Maximum number of previous messages to retrieve

        Returns:
            List of tuples (sender_name, content, timestamp)
        """
        try:
            chat_id = msg.chat_id

            # Get message history
            request = ListMessageRequest.builder() \
                .container_id_type("chat") \
                .sort_type("ByCreateTimeDesc") \
                .container_id(chat_id) \
                .page_size(max_previous_messages) \
                .build()

            response = self.client.im.v1.message.list(request)

            messages_to_return = []
            if response.success():
                for message in response.data.items:
                    # Convert timestamp to human-readable format
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(int(message.create_time) / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    sender_name = message.sender.id # sender's openid
                    content = message.body.content
                    messages_to_return.append((sender_name, content, timestamp))
            else:
                raise Exception(f'{response.code}: {response.msg}')

            return messages_to_return

        except Exception as e:
            logger.exception(f'get_history_messages failed: {e}')
            return []

    def _check_whether_chat_exists(self, chat_id):
        """
        Check whether a Lark chat with the given ID exists.

        Args:
            chat_id: ID of the chat to check

        Returns:
            True if the chat exists, False otherwise
        """
        try:
            request = GetChatRequest.builder() \
                .chat_id(chat_id) \
                .build()

            response = self.client.im.v1.chat.get(request)

            if response.success():
                return True
            return False

        except Exception as e:
            logger.debug(f'Chat {chat_id} does not exist: {e}',
                        action='_check_whether_chat_exists', status='not_found')
            return False

    def _create_chat(self, chat_name, description=""):
        """
        Creates a Lark group chat with the given name.
        Adds the agent and the bound user as members.

        Args:
            chat_name: Name of the chat to create
            description: Optional description for the chat

        Returns:
            Chat ID of the created chat
        """
        try:
            # Get the user's open_id from org_manager
            org_manager_open_id = self.org_manager_open_id

            # Create user list (only real users, not bots)
            user_id_list = []
            if org_manager_open_id:
                user_id_list.append(org_manager_open_id)

            # Create bot list (bots use app_id with "cli_" prefix)
            bot_id_list = [f"{self.agent.config.chat_lark_app_id}"]

            # Create the chat
            request = CreateChatRequest.builder() \
                .user_id_type("open_id") \
                .set_bot_manager(False) \
                .request_body(CreateChatRequestBody.builder()
                    .name(chat_name)
                    .description(description)
                    .owner_id(org_manager_open_id)
                    .user_id_list(user_id_list)
                    .bot_id_list(bot_id_list)
                    .build()) \
                .build()

            response = self.client.im.v1.chat.create(request)

            if response.success():
                chat_id = response.data.chat_id
                logger.debug(f'Chat created: {chat_name}', action='create_chat', status='success')
                return chat_id
            else:
                raise Exception(f'Failed to create chat: {response.msg}')

        except Exception as e:
            logger.exception(f'Failed to create chat {chat_name}: {e}', action='create_chat', status='failed')
            raise

    def _send_to_chat(self, chat_name, message, subject=None, description=None):
        """
        Helper method to send a message to a chat, creating it if it doesn't exist.

        Args:
            chat_name: Name of the chat
            message: Message content to send
            subject: Subject/topic for the message (optional)
            description: Description for the chat if it needs to be created
        """
        # Check if we have a cached chat_id for this chat_name
        chat_id = self._group_mapping.get(chat_name)

        # If not cached or doesn't exist, create the chat
        if not chat_id or not self._check_whether_chat_exists(chat_id):
            logger.debug(f'Chat does not exist, creating: {chat_name}')
            try:
                chat_description = description or f"Chat for {chat_name}"
                chat_id = self._create_chat(chat_name, description=chat_description)
                self._group_mapping[chat_name] = chat_id
            except Exception as e:
                logger.exception(f'Failed to create chat: {e}')
                raise

        # Send the message
        try:
            self.send_message(message, receiver=f'group:{chat_id}', subject=subject)
            logger.debug(f'Message sent to chat: {chat_name}', action='_send_to_chat', status='success')
        except Exception as e:
            logger.exception(f'Failed to send message to chat {chat_name}: {e}')
            raise

    def send_to_org(self, message, subject=None):
        """
        Sends a message to the organization chat.
        Creates the chat if it doesn't exist.

        Args:
            message: Message content to send
            subject: Subject/topic for the message (optional)
        """
        chat_name = f'{self.agent.org_name}'
        description = f"Organization chat of {self.agent.org_name}"
        self._send_to_chat(chat_name, message, subject, description)

    def send_to_log(self, message, subject=None):
        """
        Sends a message to the log receiver chat.
        If log_receiver is not set, returns without sending.

        Args:
            message: Message content to send
            subject: Subject/topic for the message (optional)
        """
        if self.log_receiver is None:
            logger.debug('No log receiver set, skipping send_to_log')
            return

        try:
            # Send to the configured log receiver chat
            self.send_message(message, receiver=f"group:{self.log_receiver}", subject=subject)
        except Exception as e:
            logger.exception(f'Error sending to log receiver: {e}')

