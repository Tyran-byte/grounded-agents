import re
from datetime import date, datetime, timezone

from grounded_agents.runtime import ledger
from grounded_agents.runtime.alerts import update_alert


class Recorder:
    def __init__(self):
        self.sent = []

    def send(self, title, body):
        self.sent.append(title)


def test_trace_id_format():
    trace = ledger.new_trace_id("answer", datetime(2026, 10, 4, 7, 0, 5, tzinfo=timezone.utc))
    assert re.fullmatch(r"answer-20261004T070005-[0-9a-f]{4}", trace)


def test_append_read_and_torn_line(tmp_path):
    path = tmp_path / "runs.jsonl"
    ledger.append(path, {"worker": "a", "cost_usd": 0.1, "started_at": "2026-10-04T07:00:00"})
    with path.open("a") as fh:
        fh.write('{"worker": "a", "cost')
    assert len(ledger.read(path)) == 1


def test_spent_today_filters_worker_and_day(tmp_path):
    path = tmp_path / "runs.jsonl"
    for worker, day, cost in [("a", "2026-10-04", 0.1), ("a", "2026-10-04", 0.2),
                              ("a", "2026-10-03", 5.0), ("b", "2026-10-04", 7.0)]:
        ledger.append(path, {"worker": worker, "started_at": f"{day}T07:00:00", "cost_usd": cost})
    assert abs(ledger.spent_today(path, "a", date(2026, 10, 4)) - 0.3) < 1e-9


def test_alerts_fire_only_on_change(tmp_path):
    state = tmp_path / "alert-state.json"
    rec = Recorder()
    sequence = [True, True, False, False, False, True, True]
    sent = [update_alert(state, "w", ok, "msg", rec) for ok in sequence]
    assert sent == [False, False, True, False, False, True, False]
    assert rec.sent == ["w: failing", "w: recovered"]


def test_first_run_failing_alerts(tmp_path):
    rec = Recorder()
    assert update_alert(tmp_path / "s.json", "w", False, "boom", rec) is True
