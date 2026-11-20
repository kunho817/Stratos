"""Tests for task cli_cases (P11, 2026-11-20): `stratos cases <file> --out <test path>` writes a test file from a case
file with stratos/cases.py, no model. Claude uses it instead of writing test code by hand for plain calls.

stratos cases CASES --out OUT: reads CASES (UTF-8); when OUT (relative to config.REPO) already exists it prints
f"{OUT} already exists, not overwritten" and returns 1. Otherwise it writes cases.render(cases.parse(text)) there
(folders made), prints f"wrote {OUT}: {n} tests from cases" (n = number of plain cases) and, for each line in
"other", f"  not a plain call (write it by hand or give it to the test writer): {line}"; returns 0. With no plain
case it writes nothing, prints "no plain cases" and returns 1."""
from stratos import __main__ as cli
from stratos import config


def test_cases_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "REPO", tmp_path)
    src = tmp_path / "c.txt"
    src.write_text("m.f(1) == 2\nm.f(2) raises ValueError\nneeds a fixture\n", encoding="utf-8")
    assert cli.main(["cases", str(src), "--out", "tests/test_m.py"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "wrote tests/test_m.py: 2 tests from cases"
    assert out[1] == "  not a plain call (write it by hand or give it to the test writer): needs a fixture"
    text = (tmp_path / "tests" / "test_m.py").read_text(encoding="utf-8")
    assert "def test_f_1():\n    assert f(1) == 2" in text
    assert cli.main(["cases", str(src), "--out", "tests/test_m.py"]) == 1
    assert capsys.readouterr().out.strip() == "tests/test_m.py already exists, not overwritten"


def test_no_plain_cases(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "REPO", tmp_path)
    src = tmp_path / "c.txt"
    src.write_text("only words here\n", encoding="utf-8")
    assert cli.main(["cases", str(src), "--out", "tests/test_x.py"]) == 1
    assert "no plain cases" in capsys.readouterr().out
    assert not (tmp_path / "tests" / "test_x.py").exists()
