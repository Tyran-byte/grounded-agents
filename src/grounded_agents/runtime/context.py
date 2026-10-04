"""Assemble a pipeline Context from a project root, models and a budget."""

from __future__ import annotations

import time
from pathlib import Path

from ..core.budget import Budget
from ..core.corpus import Corpus
from ..core.llm import LLM
from ..core.prompts import Prompts
from ..core.providers import FAKE_MODEL, build_provider
from ..core.providers.base import ModelConfig
from ..core.providers.fake import FakeProvider
from ..core.steps import Context

CORPUS_DIR = "data/quillmere/controls"
PROMPTS_DIR = "prompts"
ROLES = ("drafter", "verifier")


def fake_models() -> dict[str, ModelConfig]:
    return {role: FAKE_MODEL for role in ROLES}


def models_fingerprint(models: dict[str, ModelConfig]) -> str:
    """What a seal is bound to: provider kind and model ids per role (never keys or prices)."""
    return ",".join(f"{role}={models[role].provider}:{models[role].model}" for role in ROLES)


def provider_kind(models: dict[str, ModelConfig]) -> str:
    return "fake" if all(m.provider == "fake" for m in models.values()) else "real"


def build_context(root: Path, models: dict[str, ModelConfig], budget: Budget,
                  script: Path | None = None, timeout_s: float | None = None) -> Context:
    fake = FakeProvider.from_file(script) if script else None
    providers = {role: build_provider(models[role], fake) for role in ROLES}
    ctx = Context(Corpus.load(root / CORPUS_DIR), LLM(providers, models, budget),
                  Prompts.load(root / PROMPTS_DIR))
    if timeout_s:
        ctx.deadline = time.monotonic() + timeout_s
    return ctx
