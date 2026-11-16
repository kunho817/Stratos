from stratos import config, verify


def write(tmp_path, body):
    (tmp_path / "test_x.py").write_text(body, encoding="utf-8")


def test_passes_when_every_run_passes(tmp_path):
    write(tmp_path, "def test_ok():\n    assert 1 + 1 == 2\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert ok and "passed" in out


def test_fails_when_a_later_run_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VERIFY_RUNS", 3)
    write(tmp_path, "import os\n\ndef test_seed():\n    assert os.environ['PYTHONHASHSEED'] != '2'\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert not ok
    assert "run 2 of 3" in out and "nondeterminism" in out


def test_fails_on_the_first_run(tmp_path):
    write(tmp_path, "def test_bad():\n    assert False\n")
    ok, out = verify.run_tests(tmp_path, ["test_x.py"])
    assert not ok and "run 1 of" in out
