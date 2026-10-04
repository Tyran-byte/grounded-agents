import json
import shutil

import pytest

from grounded_agents.core.errors import SealError
from grounded_agents.evals import gate, seal
from grounded_agents.runtime.context import fake_models, models_fingerprint
from helpers import FAIL, GOOD, INSUFFICIENT, PASS, ROOT, make_ctx

FP = models_fingerprint(fake_models())


@pytest.fixture
def evals_root(tmp_path):
    shutil.copytree(ROOT / "prompts", tmp_path / "prompts")
    cases = tmp_path / "evals" / "cases"
    cases.mkdir(parents=True)
    (tmp_path / "evals" / "set.toml").write_text("version = 1\naccuracy_min = 0.5\n")
    (cases / "a.jsonl").write_text(json.dumps({"id": "e1", "question": "q", "expected": "approved"}) + "\n")
    return tmp_path


def test_freeze_is_idempotent_and_detects_edits(evals_root):
    evals = evals_root / "evals"
    assert seal.freeze(evals)["version"] == 1
    assert seal.freeze(evals)["version"] == 1
    (evals / "cases" / "a.jsonl").write_text('{"id": "e1", "question": "edited", "expected": "approved"}\n')
    with pytest.raises(SealError, match="--new-version"):
        seal.freeze(evals)
    with pytest.raises(SealError, match="differs"):
        seal.check_frozen(evals)
    assert seal.freeze(evals, new_version=True)["version"] == 2


def test_seal_requires_freeze(evals_root):
    with pytest.raises(SealError, match="not frozen"):
        seal.write_seal(evals_root, "plain", FP, "fake", True, {})


def test_seal_roundtrip_and_invalidation(evals_root, monkeypatch):
    seal.freeze(evals_root / "evals")
    seal.write_seal(evals_root, "plain", FP, "fake", True, {"accuracy": 1})
    seal.verify_seal(evals_root, "plain", FP, "fake")
    with pytest.raises(SealError, match="no seal for engine 'langgraph'"):
        seal.verify_seal(evals_root, "langgraph", FP, "fake")
    with pytest.raises(SealError, match="different eval set|differs"):
        (evals_root / "evals" / "set.toml").write_text("version = 1\naccuracy_min = 0.1\n")
        seal.verify_seal(evals_root, "plain", FP, "fake")


def test_prompt_change_invalidates_seal(evals_root):
    seal.freeze(evals_root / "evals")
    seal.write_seal(evals_root, "plain", FP, "fake", True, {})
    (evals_root / "prompts" / "verifier.md").write_text("be lenient")
    with pytest.raises(SealError, match="code, prompts or control documents changed"):
        seal.verify_seal(evals_root, "plain", FP, "fake")


def test_other_models_invalidate_seal(evals_root):
    seal.freeze(evals_root / "evals")
    seal.write_seal(evals_root, "plain", FP, "fake", True, {})
    with pytest.raises(SealError, match="sealed with models"):
        seal.verify_seal(evals_root, "plain", "drafter=fake:x,verifier=fake:y", "fake")


def test_red_stays_red(evals_root):
    seal.freeze(evals_root / "evals")
    seal.write_seal(evals_root, "plain", FP, "fake", False, {})
    with pytest.raises(SealError, match="red"):
        seal.verify_seal(evals_root, "plain", FP, "fake")


def test_logic_hash_depends_on_engine(evals_root):
    assert seal.logic_hash(evals_root, "plain") != seal.logic_hash(evals_root, "langgraph")


CASES = [gate.Case("ok", "Do you encrypt customer data at rest?", "approved",
                   must_cite=("encryption#at-rest",)),
         gate.Case("human", "Do you have a 24/7 SOC?", "needs_human"),
         gate.Case("price", "What is the price per seat?", "filtered_out")]


def test_gate_green():
    ctx, _ = make_ctx({"items": {"ok": {"drafter": [GOOD], "verifier": [PASS]},
                                 "human": {"drafter": [INSUFFICIENT]}}})
    report = gate.run_gate(CASES, {"accuracy_min": 1.0}, "plain", ctx)
    assert report.green and report.metrics()["accuracy"] == 1.0


def test_gate_counts_wrong_outcomes_and_missing_citations():
    cases = [gate.Case("ok", CASES[0].question, "approved", must_cite=("encryption#in-transit",))]
    ctx, _ = make_ctx({"items": {"ok": {"drafter": [GOOD], "verifier": [PASS]}}})
    report = gate.run_gate(cases, {"accuracy_min": 1.0}, "plain", ctx)
    assert not report.green and "did not cite encryption#in-transit" in report.failures[0]


def test_gate_forbidden_text_is_hard_fail():
    cases = [gate.Case("ok", CASES[0].question, "approved", must_not_contain=("aes-256",))]
    ctx, _ = make_ctx({"items": {"ok": {"drafter": [GOOD], "verifier": [PASS]}}})
    report = gate.run_gate(cases, {"accuracy_min": 0.0}, "plain", ctx)
    assert report.forbidden_hits == 1 and not report.green


def test_gate_stopped_run_is_not_a_verdict():
    ctx, _ = make_ctx({"items": {"ok": {"drafter": [{"_error": "down"}]}}})
    report = gate.run_gate(CASES[:1], {"accuracy_min": 0.0}, "plain", ctx)
    assert report.stopped is not None and not report.green


def test_sample_is_deterministic():
    ctx, _ = make_ctx({"items": {"ok": {"drafter": [GOOD], "verifier": [PASS]},
                                 "human": {"drafter": [GOOD, GOOD], "verifier": [FAIL, FAIL]}}})
    report = gate.run_gate(CASES, {"accuracy_min": 0}, "plain", ctx)
    assert [i.id for i in gate.sample(report, 5, seed=1)] == ["ok"]


def test_cli_verify_reports_stale_seal(evals_root, capsys):
    from grounded_agents.cli import main
    seal.freeze(evals_root / "evals")
    seal.write_seal(evals_root, "plain", FP, "fake", True, {})
    assert main(["--root", str(evals_root), "evals", "verify", "--engine", "plain"]) == 0
    (evals_root / "prompts" / "drafter.md").write_text("changed")
    assert main(["--root", str(evals_root), "evals", "verify", "--engine", "plain"]) == 2
    assert "code, prompts or control documents changed" in capsys.readouterr().err


def test_control_document_change_invalidates_seal(evals_root):
    docs = evals_root / "data" / "quillmere" / "controls"
    docs.mkdir(parents=True)
    (docs / "enc.md").write_text("# Enc\n## a — A\nAll data is encrypted.\n")
    seal.freeze(evals_root / "evals")
    seal.write_seal(evals_root, "plain", FP, "fake", True, {})
    (docs / "enc.md").write_text("# Enc\n## a — A\nSome data is encrypted.\n")
    with pytest.raises(SealError, match="code, prompts or control documents changed"):
        seal.verify_seal(evals_root, "plain", FP, "fake")
