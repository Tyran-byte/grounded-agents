"""Anthropic Messages API provider (optional extra: ``pip install grounded-agents[anthropic]``)."""

from __future__ import annotations

from ..errors import ProviderUnavailable
from .base import Completion, CompletionRequest, ModelConfig


class AnthropicProvider:
    def __init__(self, config: ModelConfig, client=None):
        self.config = config
        if client is None:
            try:
                import anthropic
            except ImportError:
                raise ProviderUnavailable(
                    "the anthropic package is not installed: "
                    "pip install 'grounded-agents[anthropic]'") from None
            # Credentials resolve from the environment (ANTHROPIC_API_KEY or a CLI profile),
            # or from the variable the manifest names in api_key_env.
            import os
            key = os.environ.get(config.api_key_env) if config.api_key_env else None
            client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        self.client = client

    def complete(self, req: CompletionRequest) -> Completion:
        try:
            import anthropic
            errors: tuple[type[BaseException], ...] = (anthropic.APIError, OSError)
        except ImportError:  # a test double client without the SDK installed
            errors = (OSError,)
        try:
            response = self.client.messages.create(
                model=req.model, max_tokens=req.max_output_tokens, system=req.system,
                messages=[{"role": "user", "content": req.user}])
        except errors as err:
            raise ProviderUnavailable(f"anthropic: {type(err).__name__}: {err}") from None
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(text, response.usage.input_tokens, response.usage.output_tokens)
