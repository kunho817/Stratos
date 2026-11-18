"""Tests for the STRATOS_REPO environment variable and config.PROJECT in stratos/config.py (plan P008, config_env_var).

config is read once at import, so each case imports it in a fresh Python process with its own environment:
- STRATOS_REPO set: REPO = Path(that folder), STATE_DIR = REPO / ".stratos", WORKTREES = REPO.parent / (REPO.name +
  "-wt"), PROJECT = project.load_settings(REPO), WRITABLE_SUFFIXES = set(PROJECT["writable_suffixes"]).
- STRATOS_REPO not set: REPO is Stratos's own folder and WORKTREES is its sibling "Stratos-wt", as before; PROJECT
  holds Stratos's defaults and WRITABLE_SUFFIXES is {".py", ".md", ".toml", ".txt", ".json"}.
(The case written by the planner model reloaded config in-process with a fake project module left behind; that
would have changed config for every later test.)"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ("import json; from stratos import config; print(json.dumps({'repo': str(config.REPO), 'state': "
         "str(config.STATE_DIR), 'wt': str(config.WORKTREES), 'project': config.PROJECT, "
         "'suffixes': sorted(config.WRITABLE_SUFFIXES), 'is_set': isinstance(config.WRITABLE_SUFFIXES, set)}))")


def probe(repo=None):
    env = {k: v for k, v in os.environ.items() if k != "STRATOS_REPO"}
    if repo is not None:
        env["STRATOS_REPO"] = str(repo)
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_default_is_stratos_itself():
    got = probe()
    assert Path(got["repo"]) == ROOT
    assert Path(got["state"]) == ROOT / ".stratos"
    assert Path(got["wt"]) == ROOT.parent / "Stratos-wt"
    assert got["suffixes"] == [".json", ".md", ".py", ".toml", ".txt"] and got["is_set"]
    assert got["project"]["language"] == "python" and got["project"]["source_dirs"] == ["stratos"]


def test_another_project(tmp_path):
    repo = tmp_path / "TowerGame"
    repo.mkdir()
    (repo / "stratos.toml").write_text('language = "javascript"\nsource_dirs = ["src"]\n'
                                       'writable_suffixes = [".js", ".html", ".css", ".md"]\n'
                                       'test_command = ["node", "--test"]\n', encoding="utf-8")
    got = probe(repo)
    assert Path(got["repo"]) == repo
    assert Path(got["state"]) == repo / ".stratos"
    assert Path(got["wt"]) == tmp_path / "TowerGame-wt"
    assert got["suffixes"] == [".css", ".html", ".js", ".md"] and got["is_set"]
    assert got["project"]["language"] == "javascript" and got["project"]["test_command"] == ["node", "--test"]
    assert got["project"]["test_dir"] == "tests"            # a default still fills what the file leaves out


def test_a_project_without_settings_gets_the_defaults(tmp_path):
    got = probe(tmp_path)
    assert Path(got["repo"]) == tmp_path
    assert got["project"]["test_runner"] == "pytest"
