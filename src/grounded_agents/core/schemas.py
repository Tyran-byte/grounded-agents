"""Shapes of what the drafter and the verifier must return, and strict parsers for them.

Parsers collect every problem as a JSON path (``$.claims[0].citations[0].quote``) so a failure
can be logged and fed back without echoing model text.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .errors import InvalidOutput

DRAFT_STATUSES = ("answered", "insufficient_evidence")
VERDICTS = ("pass", "fail")


@dataclass
class Citation:
    source: str
    quote: str


@dataclass
class Claim:
    text: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Draft:
    status: str
    answer: str
    claims: list[Claim] = field(default_factory=list)


@dataclass
class Objection:
    claim: int  # index into draft.claims; -1 means the answer as a whole
    rule: str
    source_quote: str
    explanation: str
    verified: bool | None = None  # set by grounding.verify_objections


@dataclass
class Verdict:
    verdict: str
    objections: list[Objection] = field(default_factory=list)


def to_jsonable(obj: Any) -> Any:
    data = dataclasses.asdict(obj)
    return _drop_none(data)


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value


_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(?P<body>.*)\n\s*```\s*$", re.DOTALL)


def _load(text: str) -> Any:
    match = _FENCE.match(text)
    try:
        return json.loads(match["body"] if match else text)
    except json.JSONDecodeError:
        raise InvalidOutput(["$: not valid JSON"]) from None


def _expect_str(obj: dict, key: str, path: str, errors: list[str], nonempty: bool = False) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or (nonempty and not value.strip()):
        errors.append(f"{path}.{key}: must be a {'non-empty ' if nonempty else ''}string")
        return ""
    return value


def _expect_list(obj: dict, key: str, path: str, errors: list[str]) -> list:
    value = obj.get(key)
    if not isinstance(value, list):
        errors.append(f"{path}.{key}: must be a list")
        return []
    return value


def parse_draft(text: str) -> Draft:
    data = _load(text)
    if not isinstance(data, dict):
        raise InvalidOutput(["$: must be an object"])
    errors: list[str] = []
    status = data.get("status")
    if status not in DRAFT_STATUSES:
        errors.append(f"$.status: must be one of {', '.join(DRAFT_STATUSES)}")
    answer = _expect_str(data, "answer", "$", errors)
    claims: list[Claim] = []
    for i, raw in enumerate(_expect_list(data, "claims", "$", errors)):
        path = f"$.claims[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{path}: must be an object")
            continue
        claim_text = _expect_str(raw, "text", path, errors, nonempty=True)
        citations = []
        for j, cit in enumerate(_expect_list(raw, "citations", path, errors)):
            cpath = f"{path}.citations[{j}]"
            if not isinstance(cit, dict):
                errors.append(f"{cpath}: must be an object")
                continue
            citations.append(Citation(_expect_str(cit, "source", cpath, errors),
                                      _expect_str(cit, "quote", cpath, errors)))
        claims.append(Claim(claim_text, citations))
    if status == "answered" and isinstance(data.get("claims"), list) and not claims:
        errors.append("$.claims: an answered draft needs at least one claim")
    if errors:
        raise InvalidOutput(errors)
    return Draft(status, answer, claims)


def parse_verdict(text: str) -> Verdict:
    data = _load(text)
    if not isinstance(data, dict):
        raise InvalidOutput(["$: must be an object"])
    errors: list[str] = []
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"$.verdict: must be one of {', '.join(VERDICTS)}")
    objections = []
    for i, raw in enumerate(_expect_list(data, "objections", "$", errors)):
        path = f"$.objections[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{path}: must be an object")
            continue
        claim = raw.get("claim")
        if not isinstance(claim, int) or isinstance(claim, bool) or claim < -1:
            errors.append(f"{path}.claim: must be an integer >= -1")
            claim = -1
        objections.append(Objection(claim, _expect_str(raw, "rule", path, errors, nonempty=True),
                                    _expect_str(raw, "source_quote", path, errors),
                                    _expect_str(raw, "explanation", path, errors)))
    if errors:
        raise InvalidOutput(errors)
    return Verdict(verdict, objections)
