"""Literal backing: every claim must quote its source verbatim.

Deterministic and cheap, so it runs before any verifier model. Normalisation is deliberately
narrow — whitespace runs and typographic quotes/dashes — because anything looser (case folding,
stemming, fuzzy matching) starts accepting paraphrases, and a paraphrase is exactly how a draft
smuggles in a claim the source does not make.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .corpus import Corpus
from .schemas import Draft, Objection

MIN_QUOTE_CHARS = 12  # shorter quotes ("AES-256", "yes") match almost anything

_TYPOGRAPHY = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-",
                             " ": " "})
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _SPACES.sub(" ", text.translate(_TYPOGRAPHY)).strip()


def check_quote(corpus: Corpus, source: str, quote: str) -> str | None:
    """Return None if ``quote`` appears verbatim in ``source``, else the reason it does not."""
    section = corpus.get(source)
    if section is None:
        return "unknown_source"
    needle = normalize(quote)
    if len(needle) < MIN_QUOTE_CHARS:
        return "quote_too_short"
    if needle not in normalize(section.text):
        return "quote_not_found"
    return None


def check_draft(draft: Draft, corpus: Corpus) -> list[Objection]:
    """Objections for every claim that is not literally backed. Empty list means grounded."""
    objections = []
    for i, claim in enumerate(draft.claims):
        if not claim.citations:
            objections.append(Objection(i, "grounding:no_citation", "",
                                        "Every claim needs at least one citation.", True))
        for citation in claim.citations:
            reason = check_quote(corpus, citation.source, citation.quote)
            if reason:
                objections.append(Objection(
                    i, f"grounding:{reason}", "",
                    f"Quote {citation.quote!r} is not backed by {citation.source}.", True))
    return objections


def verify_objections(objections: list[Objection], corpus: Corpus) -> list[Objection]:
    """Mark whether each verifier objection quotes something that exists in the corpus.

    An unverified objection is kept — and still blocks. Doubt routes to a human, not to ship.
    """
    needles = [normalize(s.text) for s in (corpus.get(src) for src in corpus.sources()) if s]
    out = []
    for objection in objections:
        quote = normalize(objection.source_quote)
        ok = len(quote) >= MIN_QUOTE_CHARS and any(quote in hay for hay in needles)
        out.append(replace(objection, verified=ok))
    return out
