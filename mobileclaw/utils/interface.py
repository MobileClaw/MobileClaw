"""
The common base for all interfaces
"""
from ..agent import AutoAgent

class UniInterface:
    def __init__(self, agent: AutoAgent):
        self.agent = agent
        self.config = agent.config
        self._tag = None

    def _open(self):
        pass

    def _close(self):
        pass

