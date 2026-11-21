"""Tests for T241 (P21, 2026-11-21): refcheck measures how many small bugs the drafted tests catch.

config: MUTATION (True; tests/conftest.py turns it off), MUTANTS = 12, MUTATION_WEAK = 0.6, MUTANT_TIMEOUT_S = 30.

refcheck.mutation(copy, files, tests, limit=None) -> {"total": n, "killed": k, "survivors": [...]}:
  files are the reference's (path, content) pairs, already written in the copy. limit None -> config.MUTANTS.
  Each file gets mutate.mutants(content, per_file) with per_file = max(1, ceil(limit / len(files))); the lists
  are joined in files order and cut to `limit`. For each mutant: its "source" is written to the file; a .py or .js
  file with verify.syntax_errors(copy, [path]) is skipped (not counted); the tests run as in check()
  (verify.test_cmd(tests) inside verify.dotnet_scope(copy, tests), cwd=copy, env=langs.child_env(), timeout
  config.MUTANT_TIMEOUT_S). A timeout counts as killed (the tests did not pass). Otherwise (total, failing) =
  count_tests(output): total == 0 means nothing ran (a C# mutant that does not build) - skipped, not counted;
  killed when failing is not empty or the return code is not 0; else a survivor, written
  f"{path}:{line}: {old.strip()} -> {new.strip()}". The original content is written back after each mutant
  (also when the run raises).
refcheck.check: when the status is "agree" and config.MUTATION is true, the result also has
  "mutation": mutation(copy, files, tests) (computed before the copy is removed). No "mutation" key otherwise.
plantests.mutation_lines(key, mutation) -> [] when mutation is None or its total is 0; else
  [f"{key}: the tests caught {killed} of {total} small bugs put into the reference"], plus, when killed / total <
  config.MUTATION_WEAK, f"{key}: weak tests - these bugs went unnoticed: " + "; ".join(survivors[:5]).
plantests.draft_tests logs those lines after "reference implementation passes all N tests", and its
  "ref_check" telemetry event gets mutation_total and mutation_killed (None when there is no mutation)."""
import inspect

from stratos import config, plantests, refcheck

REF = "FILE: pkg/b.py\n```python\ndef two():\n    return 1 + 1\n```\n"


class GW:
    def __init__(self, answers):
        self.answers = list(answers)

    def ensure_model(self, model):
        return 0.0

    def chat(self, messages, **kw):
        return "c", self.answers.pop(0)


def project(tmp_path, monkeypatch, test_body):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_b.py").write_text("from pkg.b import two\n\n\ndef test_two():\n" + test_body,
                                              encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT", {**config.PROJECT, "source_dirs": ["pkg"], "test_runner": "pytest",
                                            "test_command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]})
    monkeypatch.setattr(config, "REF_WRITER", {"model": "m", "effort": "low", "max_tokens": 9})
    monkeypatch.setattr(config, "MUTATION", True)
    monkeypatch.setattr(config, "MUTANTS", 12)
    monkeypatch.setattr(config, "MUTANT_TIMEOUT_S", 30)
    return root


TASK = {"key": "b", "goal": "two() is 2", "files": ["pkg/b.py"], "tests": ["tests/test_b.py"]}


def test_strong_tests_kill_every_mutant(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch, "    assert two() == 2\n")
    r = refcheck.check(GW([REF]), "P1", TASK, root, ["tests/test_b.py"])
    assert r["status"] == "agree"
    assert r["mutation"] == {"total": 3, "killed": 3, "survivors": []}


def test_weak_tests_let_them_through(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch, "    assert two() is not None\n")
    r = refcheck.check(GW([REF]), "P1", TASK, root, ["tests/test_b.py"])
    assert r["status"] == "agree"
    assert r["mutation"] == {"total": 3, "killed": 0, "survivors": [
        "pkg/b.py:2: return 1 + 1 -> return 2 + 1",
        "pkg/b.py:2: return 1 + 1 -> return 1 - 1",
        "pkg/b.py:2: return 1 + 1 -> return 1 + 2"]}


def test_no_mutation_when_off_or_not_agreeing(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch, "    assert two() == 2\n")
    monkeypatch.setattr(config, "MUTATION", False)
    assert "mutation" not in refcheck.check(GW([REF]), "P1", TASK, root, ["tests/test_b.py"])
    monkeypatch.setattr(config, "MUTATION", True)
    wrong = REF.replace("1 + 1", "3")
    r = refcheck.check(GW([wrong]), "P1", TASK, root, ["tests/test_b.py"])
    assert r["status"] != "agree" and "mutation" not in r


def test_mutation_skips_broken_mutants_and_limits(tmp_path, monkeypatch):
    root = project(tmp_path, monkeypatch, "    assert two() == 2\n")
    copy = tmp_path / "copy"
    (copy / "pkg").mkdir(parents=True)
    (copy / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (copy / "tests").mkdir()
    (copy / "tests" / "test_b.py").write_text((root / "tests" / "test_b.py").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    src = "def two():\n    return 1 + 1\n"
    (copy / "pkg" / "b.py").write_text(src, encoding="utf-8")
    r = refcheck.mutation(copy, [("pkg/b.py", src)], ["tests/test_b.py"], limit=2)
    assert r["total"] == 2 and r["killed"] == 2
    assert (copy / "pkg" / "b.py").read_text(encoding="utf-8") == src   # written back
    monkeypatch.setattr(refcheck.verify, "syntax_errors", lambda root, paths: ["pkg/b.py:2: bad"])
    assert refcheck.mutation(copy, [("pkg/b.py", src)], ["tests/test_b.py"]) == {"total": 0, "killed": 0,
                                                                              "survivors": []}


def test_mutation_lines(monkeypatch):
    monkeypatch.setattr(config, "MUTATION_WEAK", 0.6)
    assert plantests.mutation_lines("k", None) == []
    assert plantests.mutation_lines("k", {"total": 0, "killed": 0, "survivors": []}) == []
    assert plantests.mutation_lines("k", {"total": 5, "killed": 4, "survivors": ["a"]}) == [
        "k: the tests caught 4 of 5 small bugs put into the reference"]
    weak = {"total": 10, "killed": 5, "survivors": [f"s{i}" for i in range(7)]}
    assert plantests.mutation_lines("k", weak) == [
        "k: the tests caught 5 of 10 small bugs put into the reference",
        "k: weak tests - these bugs went unnoticed: s0; s1; s2; s3; s4"]


def test_draft_tests_logs_the_mutation_lines():
    src = inspect.getsource(plantests.draft_tests)
    assert "mutation_lines(" in src and "mutation_total" in src and "mutation_killed" in src


def test_config_defaults():
    text = inspect.getsource(config)
    assert "MUTATION = True" in text and "MUTANTS = 12" in text and "MUTATION_WEAK = 0.6" in text
    assert "MUTANT_TIMEOUT_S = 30" in text
