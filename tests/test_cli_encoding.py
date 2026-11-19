"""A character the console's code page cannot show must not break a command (Orbit T009, 2026-11-19).

run-all's output was redirected to a file, so Python wrote stdout in the Windows code page (cp949); a triage reason
with an em dash raised UnicodeEncodeError inside log(), and the run reported it as the triage result. main() makes
stdout and stderr replace what they cannot encode instead of failing."""
import io
import sys

from stratos import __main__ as cli
from stratos import config
from stratos.state import Store


def test_status_with_a_character_cp949_lacks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    Store(tmp_path / "state").add_task("levels — harder", "g", [], [], ["tests/x.py"])
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp949")
    monkeypatch.setattr(sys, "stdout", out)
    assert cli.main(["status"]) == 0
    out.flush()
    assert "levels ? harder" in raw.getvalue().decode("cp949")
