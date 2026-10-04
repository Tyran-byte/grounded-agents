"""Deterministic intake filter: questions no model should answer, decided before any spend.

Pricing and legal commitments are routed out on purpose — they are business decisions, and a
grounded answer from a security document would still be the wrong owner answering.
"""

from __future__ import annotations

import re

RULES: dict[str, tuple[str, ...]] = {
    "pricing": (r"\bpric(e|es|ing)\b", r"\bdiscounts?\b", r"\bper[- ]seat\b"),
    "legal_commitment": (r"\bindemnif", r"\bliabilit(y|ies)\b", r"\bwarrant(y|ies)\b",
                         r"\bpenalt(y|ies)\b"),
}
_COMPILED = {name: [re.compile(p, re.IGNORECASE) for p in pats] for name, pats in RULES.items()}


def _key(question: str) -> str:
    return " ".join(question.lower().split())


def filter_question(question: str, seen: set[str]) -> str | None:
    """Return the reason to drop ``question``, or None to keep it (and remember it in ``seen``)."""
    key = _key(question)
    if not key:
        return "empty"
    for name, patterns in _COMPILED.items():
        if any(p.search(question) for p in patterns):
            return name
    if key in seen:
        return "duplicate"
    seen.add(key)
    return None
