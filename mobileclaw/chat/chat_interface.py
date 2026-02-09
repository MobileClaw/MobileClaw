"""
The interfaces to chat with users or other agents.
"""
from mobileclaw.utils.interface import UniInterface

class Chat_Interface(UniInterface):
    def __init__(self, agent):
        super().__init__(agent)
        from mobileclaw.agent import AutoAgent
        assert isinstance(agent, AutoAgent)
        self._tag = 'chat'
        self.chat_channels = agent.config.chat_channels
        self.chat_clients = {}
        self.default_chat_channel = agent.config.default_chat_channel

    def __str__(self) -> str:
        return "Chat interface"

    def _open(self):
        if 'zulip' in self.chat_channels:
            from .zulip_client import Zulip_Client
            self.zulip_client = Zulip_Client(self.agent)
            self.zulip_client._open()
            self.chat_clients['zulip'] = self.zulip_client

    def _close(self):
        for client in self.chat_clients.values():
            if client is not None:
                client._close()

    def _get_client(self, channel=None):
        """
        Get the chat client for the specified channel.
        If no channel is specified, use the default channel.

        Args:
            channel: Channel name (e.g., 'zulip'). If None, uses default_chat_channel.

        Returns:
            The chat client for the specified channel, or None if not available.
        """
        if channel is None:
            channel = self.default_chat_channel
        return self.chat_clients.get(channel)

    def send_reply(self, message, previous_message, channel=None):
        """
        Send a reply to a previous message.

        Args:
            message: Reply message content
            previous_message: The previous message to reply to
            channel: Channel to use (optional, defaults to default_chat_channel)
        """
        client = self._get_client(channel)
        if client is not None and hasattr(client, 'send_reply'):
            client.send_reply(message, previous_message)

    def send_to_org(self, message, subject="General", channel=None):
        """
        Send a message to the organization.

        Args:
            message: Message content to send
            subject: Subject/topic for the message
            channel: Channel to use (optional, defaults to default_chat_channel)
        """
        client = self._get_client(channel)
        if client is not None and hasattr(client, 'send_to_org'):
            client.send_to_org(message, subject)

    def send_to_log(self, message, subject="Log", channel=None):
        """
        Send a message to the agent's self-reporting stream.

        Args:
            message: Message content to send
            subject: Subject/topic for the message
            channel: Channel to use (optional, defaults to default_chat_channel)
        """
        client = self._get_client(channel)
        if client is not None and hasattr(client, 'send_to_log'):
            client.send_to_log(message, subject)

    def send_message(self, message, receiver=None, channel=None):
        """
        Send a message to the receiver.

        Args:
            message: Can be a string, an image/file (represented as a path) or a list of them
            receiver: Name/id of the message receiver (can be a user or a group)
            channel: Channel to use (optional, defaults to default_chat_channel)
        """
        client = self._get_client(channel)
        if client is not None and hasattr(client, 'send_message'):
            client.send_message(message, receiver)
