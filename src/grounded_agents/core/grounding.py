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
# Figures are where answers go wrong most expensively ("24/7", "99.9%", "within 4 hours"), and
# they are cheap to check exactly: any figure the draft states must appear in a cited quote.
_NUMBER = re.compile(r"\d+(?:[.,/:]\d+)*")


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


def _numbers(text: str) -> list[str]:
    return list(dict.fromkeys(_NUMBER.findall(normalize(text))))


def _unbacked_numbers(text: str, quotes: list[str]) -> list[str]:
    backed = set(_numbers(" ".join(quotes)))
    return [n for n in _numbers(text) if n not in backed]


def check_draft(draft: Draft, corpus: Corpus) -> list[Objection]:
    """Objections for every claim that is not literally backed. Empty list means grounded."""
    objections = []
    all_quotes = [c.quote for claim in draft.claims for c in claim.citations]
    for number in _unbacked_numbers(draft.answer, all_quotes):
        objections.append(Objection(-1, "grounding:unbacked_number", "",
                                    f"The answer states {number!r}, which no cited quote contains.",
                                    True))
    for i, claim in enumerate(draft.claims):
        for number in _unbacked_numbers(claim.text, [c.quote for c in claim.citations]):
            objections.append(Objection(i, "grounding:unbacked_number", "",
                                        f"The claim states {number!r}, which its quotes do not.",
                                        True))
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
