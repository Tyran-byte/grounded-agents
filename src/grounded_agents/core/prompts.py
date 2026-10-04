"""Prompt assembly. System prompts live in ``prompts/*.md``; this module only fills them in."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .corpus import Corpus
from .schemas import Draft, Objection, to_jsonable


@dataclass(frozen=True)
class Prompts:
    drafter: str
    verifier: str

    @classmethod
    def load(cls, directory: Path | str) -> "Prompts":
        d = Path(directory)
        return cls((d / "drafter.md").read_text(encoding="utf-8"),
                   (d / "verifier.md").read_text(encoding="utf-8"))


def build_drafter(prompts: Prompts, question: str, corpus: Corpus, previous: Draft | None = None,
                  objections: list[Objection] | None = None) -> tuple[str, str]:
    parts = [f"Control documents:\n\n{corpus.render()}", f"Question:\n{question}"]
    if previous is not None:
        parts.append("Your previous draft:\n" + json.dumps(to_jsonable(previous), indent=1))
    if objections:
        lines = [f"- claim {o.claim}: [{o.rule}] {o.explanation}"
                 + (f' Source says: "{o.source_quote}"' if o.source_quote else "")
                 for o in objections]
        parts.append("Objections to fix:\n" + "\n".join(lines))
    return prompts.drafter, "\n\n".join(parts)


def build_verifier(prompts: Prompts, question: str, draft: Draft, corpus: Corpus) -> tuple[str, str]:
    cited = sorted({c.source for claim in draft.claims for c in claim.citations})
    sections = [s for s in (corpus.get(src) for src in cited) if s is not None]
    rendered = "\n\n".join(f"[{s.source}] {s.title}\n{s.text}" for s in sections) or "(none)"
    user = (f"Question:\n{question}\n\nDraft:\n{json.dumps(to_jsonable(draft), indent=1)}\n\n"
            f"Cited sections:\n\n{rendered}")
    return prompts.verifier, user
