import json

import pytest

from grounded_agents.core.errors import InvalidOutput
from grounded_agents.core.schemas import (Citation, Claim, Draft, Objection, Verdict, parse_draft,
                                          parse_verdict, to_jsonable)

GOOD_DRAFT = {
    "status": "answered",
    "answer": "Yes.",
    "claims": [{"text": "Data at rest uses AES-256.",
                "citations": [{"source": "encryption#at-rest",
                               "quote": "encrypted with AES-256"}]}],
}


def errors_of(fn, payload):
    with pytest.raises(InvalidOutput) as exc:
        fn(payload if isinstance(payload, str) else json.dumps(payload))
    return exc.value.errors


def test_parses_valid_draft():
    draft = parse_draft(json.dumps(GOOD_DRAFT))
    assert draft == Draft("answered", "Yes.", [Claim("Data at rest uses AES-256.", [
        Citation("encryption#at-rest", "encrypted with AES-256")])])


def test_accepts_fenced_json():
    assert parse_draft("```json\n" + json.dumps(GOOD_DRAFT) + "\n```").status == "answered"


def test_not_json():
    assert errors_of(parse_draft, "Sure! Here is the answer") == ["$: not valid JSON"]


def test_answered_needs_claims():
    assert "$.claims: an answered draft needs at least one claim" in errors_of(
        parse_draft, {**GOOD_DRAFT, "claims": []})


def test_bad_status():
    assert "$.status: must be one of answered, insufficient_evidence" in errors_of(
        parse_draft, {**GOOD_DRAFT, "status": "maybe"})


def test_citation_paths():
    bad = {**GOOD_DRAFT, "claims": [{"text": "x", "citations": [{"source": "a#b"}]}]}
    assert errors_of(parse_draft, bad) == ["$.claims[0].citations[0].quote: must be a string"]


def test_insufficient_evidence_without_claims_is_valid():
    draft = parse_draft(json.dumps({"status": "insufficient_evidence", "answer": "Not stated.",
                                    "claims": []}))
    assert draft.status == "insufficient_evidence"


def test_parses_verdict():
    verdict = parse_verdict(json.dumps({"verdict": "fail", "objections": [
        {"claim": 0, "rule": "overreach", "source_quote": "q", "explanation": "e"}]}))
    assert verdict == Verdict("fail", [Objection(0, "overreach", "q", "e")])


def test_verdict_enum_and_claim_index():
    errs = errors_of(parse_verdict, {"verdict": "ok", "objections": [
        {"claim": -2, "rule": "r", "source_quote": "q", "explanation": "e"}]})
    assert "$.verdict: must be one of pass, fail" in errs
    assert "$.objections[0].claim: must be an integer >= -1" in errs


def test_bool_is_not_an_integer():
    errs = errors_of(parse_verdict, {"verdict": "fail", "objections": [
        {"claim": True, "rule": "r", "source_quote": "q", "explanation": "e"}]})
    assert errs == ["$.objections[0].claim: must be an integer >= -1"]


def test_to_jsonable_roundtrip():
    draft = parse_draft(json.dumps(GOOD_DRAFT))
    assert to_jsonable(draft) == GOOD_DRAFT
