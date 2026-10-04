import pytest

from grounded_agents.core.filters import filter_question


@pytest.mark.parametrize("question,reason", [
    ("", "empty"),
    ("   ", "empty"),
    ("What discount do you offer for a three-year contract?", "pricing"),
    ("What is the price per seat?", "pricing"),
    ("Will you indemnify us for losses caused by a breach?", "legal_commitment"),
    ("Confirm your liability cap for data incidents.", "legal_commitment"),
    ("Do you encrypt customer data at rest?", None),
])
def test_rules(question, reason):
    assert filter_question(question, set()) == reason


def test_duplicates_ignore_case_and_spacing():
    seen = set()
    assert filter_question("Do you encrypt data?", seen) is None
    assert filter_question("  do YOU   encrypt data? ", seen) == "duplicate"
