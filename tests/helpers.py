"""Shared builders for scripted runs."""

from pathlib import Path

from grounded_agents.core.budget import Budget
from grounded_agents.core.corpus import Corpus
from grounded_agents.core.llm import LLM
from grounded_agents.core.prompts import Prompts
from grounded_agents.core.providers.base import ModelConfig
from grounded_agents.core.providers.fake import FakeProvider
from grounded_agents.core.steps import Context

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Corpus.load(ROOT / "data" / "quillmere" / "controls")
PROMPTS = Prompts.load(ROOT / "prompts")
FAKE_MODEL = ModelConfig("fake", "fake-model", price_in_per_mtok=1.0, price_out_per_mtok=5.0)

GOOD = {"status": "answered", "answer": "Yes, with AES-256.", "claims": [{
    "text": "Customer data at rest is encrypted with AES-256.",
    "citations": [{"source": "encryption#at-rest",
                   "quote": "All customer data at rest is encrypted with AES-256."}]}]}
UNCITED = {"status": "answered", "answer": "Yes, and keys rotate monthly.", "claims": [{
    "text": "Keys rotate monthly.",
    "citations": [{"source": "encryption#key-management", "quote": "rotated every month"}]}]}
INSUFFICIENT = {"status": "insufficient_evidence", "answer": "Not covered.", "claims": []}
PASS = {"verdict": "pass", "objections": []}
FAIL = {"verdict": "fail", "objections": [{
    "claim": 0, "rule": "overreach",
    "source_quote": "Encryption at rest is enabled by default",
    "explanation": "The draft adds a commitment the source does not make."}]}


def make_ctx(script, budget=None):
    fake = FakeProvider(script)
    budget = budget or Budget(per_call_usd=1, per_run_usd=10, per_day_usd=10)
    llm = LLM({"drafter": fake, "verifier": fake},
              {"drafter": FAKE_MODEL, "verifier": FAKE_MODEL}, budget)
    return Context(CORPUS, llm, PROMPTS), fake
