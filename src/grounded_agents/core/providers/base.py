"""Provider-neutral request/response types. No model is named anywhere in code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelConfig:
    provider: str                 # "fake" | "anthropic" | "openai_compat"
    model: str                    # whatever id the provider expects
    price_in_per_mtok: float      # USD per million input tokens
    price_out_per_mtok: float     # USD per million output tokens
    base_url: str | None = None   # openai_compat only
    api_key_env: str | None = None  # name of the env var holding the key, never the key


@dataclass(frozen=True)
class CompletionRequest:
    role: str                     # "drafter" | "verifier"
    model: str
    system: str
    user: str
    max_output_tokens: int = 2048
    item_id: str = ""
    attempt: int = 0


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    def complete(self, req: CompletionRequest) -> Completion: ...
