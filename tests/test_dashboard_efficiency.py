"""Tests for task dashboard_efficiency: the dashboard shows where the tokens and the time go."""
from stratos import dashboard

from test_dashboard import make_project


def test_project_has_its_efficiency(tmp_path, monkeypatch):
    """(task dashboard_efficiency) project(repo)["efficiency"] is report.efficiency(<all its telemetry events>)
    (called through the report module), for the page's efficiency panel."""
    from stratos import report
    repo, tel = make_project(tmp_path)
    tel.record("call", call_id="c1", task="T001", role="coder", attempt=1, model="m", seconds=3, completion_tokens=9)
    seen = []
    monkeypatch.setattr(report, "efficiency", lambda events: seen.append(len(events)) or {"E": 1})
    assert dashboard.project(repo)["efficiency"] == {"E": 1} and seen == [1]
