import json

from stratos.state import Store
from stratos.telemetry import Telemetry


def test_tasks_round_trip(tmp_path):
    s = Store(tmp_path)
    t = s.add_task("title", "goal", ["a.py"], ["tests/t.py"], ["tests/t.py"])
    assert t["id"] == "T001" and t["status"] == "todo"
    assert s.add_task("second", "g", [], [], ["x"])["id"] == "T002"
    s.update("T001", status="done", commit="abc")
    assert s.get("T001")["status"] == "done"
    assert Store(tmp_path).get("T001")["commit"] == "abc"


def test_decisions_are_appended(tmp_path):
    s = Store(tmp_path)
    s.decide(task="T001", result="failed")
    s.decide(task="T001", result="passed")
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["result"] for x in lines] == ["failed", "passed"]


def test_telemetry_records_and_loads(tmp_path):
    tel = Telemetry(tmp_path / "t.jsonl")
    tel.record("call", model="m", seconds=1.5)
    tel.record("switch", model="m2", seconds=9)
    ev = tel.load()
    assert [e["kind"] for e in ev] == ["call", "switch"] and ev[0]["seconds"] == 1.5
