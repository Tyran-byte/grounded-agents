"""Pydantic mirrors of the core schemas, used by the LangGraph engine to validate model output.

They must accept and reject exactly what ``core.schemas`` does — a conformance test feeds both
the same fixtures — and they convert to the core dataclasses so every downstream control
(grounding, verification, states) is shared code, not a second implementation.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, model_validator

from ...core import schemas
from ...core.errors import InvalidOutput

_FENCE_PREFIXES = ("```json", "```")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CitationModel(_Strict):
    source: StrictStr
    quote: StrictStr


class ClaimModel(_Strict):
    text: StrictStr = Field(min_length=1)
    citations: list[CitationModel]

    @model_validator(mode="after")
    def _text_not_blank(self):
        if not self.text.strip():
            raise ValueError("text must be non-empty")
        return self


class DraftModel(_Strict):
    status: Literal["answered", "insufficient_evidence"]
    answer: StrictStr
    claims: list[ClaimModel]

    @model_validator(mode="after")
    def _answered_needs_claims(self):
        if self.status == "answered" and not self.claims:
            raise ValueError("an answered draft needs at least one claim")
        return self

    def to_core(self) -> schemas.Draft:
        return schemas.Draft(self.status, self.answer, [
            schemas.Claim(c.text, [schemas.Citation(x.source, x.quote) for x in c.citations])
            for c in self.claims])


class ObjectionModel(_Strict):
    claim: StrictInt = Field(ge=-1)
    rule: StrictStr = Field(min_length=1)
    source_quote: StrictStr
    explanation: StrictStr


class VerdictModel(_Strict):
    verdict: Literal["pass", "fail"]
    objections: list[ObjectionModel]

    def to_core(self) -> schemas.Verdict:
        return schemas.Verdict(self.verdict, [
            schemas.Objection(o.claim, o.rule, o.source_quote, o.explanation)
            for o in self.objections])


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        body = stripped[3:-3]
        return body[4:] if body.startswith("json") else body
    return text


def _paths(err: ValidationError) -> list[str]:
    out = []
    for e in err.errors():
        path = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e["loc"])
        out.append(f"{path}: {e['msg']}")
    return out


def _validate(model: type[BaseModel], text: str):
    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        raise InvalidOutput(["$: not valid JSON"]) from None
    try:
        return model.model_validate(data)
    except ValidationError as err:
        raise InvalidOutput(_paths(err)) from None


def parse_draft(text: str) -> schemas.Draft:
    return _validate(DraftModel, text).to_core()


def parse_verdict(text: str) -> schemas.Verdict:
    return _validate(VerdictModel, text).to_core()
