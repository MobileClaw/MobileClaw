"""
The interfaces to chat with users or other agents.
"""
from mobileclaw.utils.interface import UniInterface
from mobileclaw.utils import debug


class Chat_Message:
    def __init__(self, content=None, timestamp=None, sender=None, recipient=None, **kwargs):
        self.content = content
        self.timestamp = timestamp
        self.sender = sender
        self.recipient = recipient


class Chat_Handler(UniInterface):
    def __init__(self, agent):
        super().__init__(agent)
    
    def _handle_message(self, message_in):
        debug.print_method_name_with_message('not implemented')


class Chat_Client(UniInterface):
    """
    Each chat client should implement:
    - `_send` method, which sends a message
    """
    def __init__(self, agent):
        super().__init__(agent)
        self._tag = 'chat.client'
        pass

