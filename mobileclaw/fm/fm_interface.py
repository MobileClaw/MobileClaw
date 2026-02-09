"""
The interfaces to get answers from foundation models.
"""
from ..utils.interface import UniInterface
from ..agent import AutoAgent
from typing import cast


class FM_Interface(UniInterface):
    def __init__(self, agent: AutoAgent):
        super().__init__(agent)
        self._tag = 'fm'
        # Predefined functions
        from .function_hub_local import FunctionHubLocal
        self.function_hub = FunctionHubLocal(agent)

    def __str__(self) -> str:
        return "FM_Interface"

    def _open(self):
        pass

    def _close(self):
        pass

    def call_func(self, func, params, **kwargs):
        """
        call a predefined function with given params and _api_config
        """
        return self.function_hub.call_func(func, params, **kwargs)

    def call_chat_completion(self, messages, **kwargs):
        """
        call the OpenAI-style chat completion api with messages and _api_config
        """
        return self.call_func('chat_completion', params=messages, **kwargs)

    def get_available_models(self):
        """
        Get a list of available models with descriptions that can be used during task execution.

        Returns:
            list: List of (name, description) tuples for each available model
        """
        models = []
        models.append(('default', 'default vision language model that takes text and/or images as input and generates text'))
        return models

    def embedding(self, text: str | list[str], model: str = None):
        """
        Generate embeddings for the given text(s).

        Parameters
        ----------
        text : str | list[str]
            Text or list of texts to generate embeddings for
        model : str, optional
            Embedding model name. If not specified, uses a default embedding model.

        Returns
        -------
        list[float] | list[list[float]]
            Embedding vector(s). Returns a single vector for single text input,
            or a list of vectors for list input.
        """
        raise NotImplementedError()
