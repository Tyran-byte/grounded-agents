"""Provider factory. Real providers are imported lazily so the core needs no SDK installed."""

from __future__ import annotations

from .base import ModelConfig, Provider

FAKE_MODEL = ModelConfig("fake", "fake", price_in_per_mtok=1.0, price_out_per_mtok=5.0)


def build_provider(config: ModelConfig, fake: Provider | None = None) -> Provider:
    if config.provider == "fake":
        if fake is None:
            raise ValueError("the fake provider needs a script (--script)")
        return fake
    if config.provider == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(config)
    if config.provider == "openai_compat":
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(config)
    raise ValueError(f"unknown provider {config.provider!r}")
