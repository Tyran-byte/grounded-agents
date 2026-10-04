import pytest

from grounded_agents.core.corpus import Corpus, Section
from grounded_agents.core.grounding import check_draft, check_quote, normalize, verify_objections
from grounded_agents.core.schemas import Citation, Claim, Draft, Objection

CORPUS = Corpus({
    "enc#at-rest": Section("enc#at-rest", "At rest",
                           "All customer data at rest is encrypted with AES-256.\nBackups too."),
    "enc#transit": Section("enc#transit", "Transit", "Traffic uses TLS 1.2 or higher — always."),
})


def test_normalize_collapses_whitespace_and_typography():
    assert normalize("  a\n\t b “c” ‘d’ e–f g—h i ") == "a b \"c\" 'd' e-f g-h i"


@pytest.mark.parametrize("quote", [
    "encrypted with AES-256",
    "encrypted   with\nAES-256",
    "AES-256. Backups too.",          # spans a line break in the source
])
def test_verbatim_quotes_pass(quote):
    assert check_quote(CORPUS, "enc#at-rest", quote) is None


def test_typographic_dash_in_source_matches_plain_dash():
    assert check_quote(CORPUS, "enc#transit", "TLS 1.2 or higher - always") is None


@pytest.mark.parametrize("source,quote,reason", [
    ("enc#at-rest", "Encrypted with AES-256", "quote_not_found"),       # case matters
    ("enc#at-rest", "encrypted using AES-256", "quote_not_found"),      # paraphrase
    ("enc#at-rest", "TLS 1.2 or higher", "quote_not_found"),            # wrong section
    ("enc#nowhere", "encrypted with AES-256", "unknown_source"),
    ("enc#at-rest", "AES-256", "quote_too_short"),
])
def test_failures(source, quote, reason):
    assert check_quote(CORPUS, source, quote) == reason


def test_check_draft_reports_each_problem():
    draft = Draft("answered", "a", [
        Claim("ok", [Citation("enc#at-rest", "encrypted with AES-256")]),
        Claim("uncited", []),
        Claim("bad", [Citation("enc#transit", "TLS 1.3 everywhere always")]),
    ])
    objections = check_draft(draft, CORPUS)
    assert [(o.claim, o.rule) for o in objections] == [
        (1, "grounding:no_citation"), (2, "grounding:quote_not_found")]
    assert all(o.verified is True for o in objections)


def test_clean_draft_has_no_objections():
    draft = Draft("answered", "a", [Claim("ok", [Citation("enc#at-rest", "encrypted with AES-256")])])
    assert check_draft(draft, CORPUS) == []


def test_verify_objections_marks_unverifiable_quotes():
    objections = [Objection(0, "overreach", "Traffic uses TLS 1.2 or higher", "e"),
                  Objection(0, "overreach", "Traffic uses TLS 1.0", "e"),
                  Objection(0, "overreach", "", "e")]
    verified = verify_objections(objections, CORPUS)
    assert [o.verified for o in verified] == [True, False, False]


def test_numbers_in_the_answer_must_appear_in_a_quote():
    draft = Draft("answered", "Yes, AES-256, rotated every 12 months, with 24/7 monitoring.", [
        Claim("AES-256 at rest", [Citation("enc#at-rest", "encrypted with AES-256")])])
    objections = check_draft(draft, CORPUS)
    assert [(o.claim, o.rule) for o in objections] == [
        (-1, "grounding:unbacked_number"), (-1, "grounding:unbacked_number")]
    assert "'12'" in objections[0].explanation and "'24/7'" in objections[1].explanation


def test_numbers_in_a_claim_must_appear_in_its_own_quotes():
    draft = Draft("answered", "TLS.", [
        Claim("TLS 1.3 is used", [Citation("enc#transit", "Traffic uses TLS 1.2 or higher")])])
    assert [(o.claim, o.rule) for o in check_draft(draft, CORPUS)] == [
        (0, "grounding:unbacked_number")]


def test_backed_numbers_pass():
    draft = Draft("answered", "TLS 1.2 or higher.", [
        Claim("TLS 1.2+", [Citation("enc#transit", "Traffic uses TLS 1.2 or higher")])])
    assert check_draft(draft, CORPUS) == []
