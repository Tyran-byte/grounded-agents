import json
import shutil
from datetime import datetime, timezone

import pytest

from grounded_agents.evals.seal import freeze, write_seal
from grounded_agents.runtime import ledger
from grounded_agents.runtime.context import fake_models, models_fingerprint
from grounded_agents.runtime.manifest import load_manifest
from grounded_agents.runtime.runner import run_worker
from helpers import FAIL, GOOD, PASS, ROOT

NOW = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)
FP = models_fingerprint(fake_models())


class Recorder:
    def __init__(self):
        self.sent = []

    def send(self, title, body):
        self.sent.append(title)


@pytest.fixture
def project(tmp_path):
    shutil.copytree(ROOT / "data" / "quillmere" / "controls", tmp_path / "data/quillmere/controls")
    shutil.copytree(ROOT / "prompts", tmp_path / "prompts")
    qdir = tmp_path / "data/quillmere/questionnaires"
    qdir.mkdir(parents=True)
    (qdir / "buyer.jsonl").write_text(
        '{"id": "q1", "question": "Do you encrypt customer data at rest?"}\n'
        '{"id": "q2", "question": "Is encryption at rest optional?"}\n'
        '{"id": "q3", "question": "What is the price per seat?"}\n')
    (tmp_path / "script.json").write_text(json.dumps({"items": {
        "q1": {"drafter": [GOOD], "verifier": [PASS]},
        "q2": {"drafter": [GOOD, GOOD], "verifier": [FAIL, FAIL]}}}))
    evals = tmp_path / "evals"
    (evals / "cases").mkdir(parents=True)
    (evals / "set.toml").write_text("version = 1\naccuracy_min = 1.0\n")
    (evals / "cases" / "a.jsonl").write_text('{"id": "e1", "question": "x", "expected": "approved"}\n')
    freeze(evals)
    shutil.copy(ROOT / "workers" / "answer-plain.toml", tmp_path / "w.toml")
    return tmp_path


def run(project, **kw):
    kw.setdefault("provider", "fake")
    kw.setdefault("script", project / "script.json")
    kw.setdefault("notifier", Recorder())
    return run_worker(load_manifest(project / "w.toml"), root=project, now=NOW, **kw)


def test_dry_run_writes_only_the_ledger(project):
    result = run(project)
    assert result.exit_code == 0 and result.mode == "dry"
    assert {i.id: i.state.value for i in result.items} == {
        "q1": "approved", "q2": "needs_human", "q3": "filtered_out"}
    assert sorted(p for p, _ in result.planned) == [
        f"out/answers/{result.trace_id}.jsonl", f"out/review-queue/{result.trace_id}.jsonl"]
    assert not (project / "out").exists()
    row = ledger.read(project / "ledger/runs.jsonl")[-1]
    assert row["items"] == {"approved": 1, "needs_human": 1, "filtered_out": 1}
    assert row["mode"] == "dry" and row["calls"] == 6 and row["cost_usd"] > 0


def test_apply_without_seal_refuses(project):
    result = run(project, apply=True)
    assert result.exit_code == 2 and "SealError" in result.error
    assert not (project / "out").exists()


def test_apply_with_green_seal_writes_stamped_outputs(project):
    write_seal(project, "plain", FP, "fake", True, {})
    rec = Recorder()
    result = run(project, apply=True, notifier=rec)
    assert result.exit_code == 0
    answers = (project / f"out/answers/{result.trace_id}.jsonl").read_text().splitlines()
    review = json.loads((project / f"out/review-queue/{result.trace_id}.jsonl").read_text())
    assert json.loads(answers[0])["trace_id"] == result.trace_id
    assert review["id"] == "q2" and len(review["drafts"]) == 2
    assert rec.sent == []  # first green run is silent


def test_red_seal_blocks_apply(project):
    write_seal(project, "plain", FP, "fake", False, {})
    assert "the seal is red" in run(project, apply=True).error


def test_t3_needs_approver(project):
    text = (project / "w.toml").read_text().replace('tier = "T1"', 'tier = "T3"')
    (project / "w.toml").write_text(text)
    write_seal(project, "plain", FP, "fake", True, {})
    assert "approved-by" in run(project, apply=True).error
    result = run(project, apply=True, approved_by="security-lead")
    assert result.exit_code == 0
    assert ledger.read(project / "ledger/runs.jsonl")[-1]["approved_by"] == "security-lead"


def test_budget_stop_exits_2_and_alerts_once(project):
    text = (project / "w.toml").read_text().replace("per_run_usd = 0.50", "per_run_usd = 0.055")
    (project / "w.toml").write_text(text)
    write_seal(project, "plain", FP, "fake", True, {})
    rec = Recorder()
    first = run(project, apply=True, notifier=rec)
    second = run(project, apply=True, notifier=rec)
    assert first.exit_code == second.exit_code == 2
    assert "BudgetExhausted" in first.error
    assert rec.sent == ["answer-plain: failing"]


def test_day_cap_uses_earlier_runs(project):
    ledger.append(project / "ledger/runs.jsonl", {"worker": "answer-plain", "cost_usd": 1.99,
                                                  "started_at": "2026-10-04T05:00:00Z"})
    result = run(project)
    assert result.exit_code == 2 and "day budget exhausted" in result.error
    assert result.calls == 0


def test_real_provider_without_models_fails_before_any_call(project):
    result = run(project, provider=None, script=None, env={})
    assert result.exit_code == 2 and "GA_DRAFTER_" in result.error
