"""The Pydantic parsers must agree with core.schemas on every fixture: same accept/reject."""

import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("langgraph")

from grounded_agents.core import schemas  # noqa: E402
from grounded_agents.core.errors import InvalidOutput  # noqa: E402
from grounded_agents.engines.langgraph import models  # noqa: E402
from helpers import FAIL, GOOD, INSUFFICIENT, PASS  # noqa: E402

DRAFTS = [
    GOOD, INSUFFICIENT,
    {**GOOD, "claims": []},
    {**GOOD, "status": "maybe"},
    {**GOOD, "answer": 3},
    {**GOOD, "claims": [{"text": "x", "citations": [{"source": "a#b"}]}]},
    {**GOOD, "claims": [{"text": "   ", "citations": []}]},
    {**GOOD, "claims": [{"text": "x", "citations": [{"source": 1, "quote": "q"}]}]},
    {**GOOD, "claims": "nope"},
    ["not", "an", "object"],
]
VERDICTS = [
    PASS, FAIL,
    {"verdict": "ok", "objections": []},
    {"verdict": "fail", "objections": [{**FAIL["objections"][0], "claim": -2}]},
    {"verdict": "fail", "objections": [{**FAIL["objections"][0], "claim": True}]},
    {"verdict": "fail", "objections": [{**FAIL["objections"][0], "rule": ""}]},
    {"verdict": "fail"},
]


def outcome(fn, payload):
    try:
        return ("ok", fn(json.dumps(payload)))
    except InvalidOutput:
        return ("invalid", None)


@pytest.mark.parametrize("payload", DRAFTS)
def test_draft_parsers_agree(payload):
    assert outcome(schemas.parse_draft, payload) == outcome(models.parse_draft, payload)


@pytest.mark.parametrize("payload", VERDICTS)
def test_verdict_parsers_agree(payload):
    assert outcome(schemas.parse_verdict, payload) == outcome(models.parse_verdict, payload)


@pytest.mark.parametrize("text", ["not json", "```json\n" + json.dumps(GOOD) + "\n```"])
def test_text_handling_agrees(text):
    def run(fn):
        try:
            return fn(text)
        except InvalidOutput:
            return "invalid"
    assert run(schemas.parse_draft) == run(models.parse_draft)
