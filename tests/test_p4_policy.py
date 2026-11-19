"""Tests for task p4_policy (P4, 2026-11-20): two decisions from the measurements.

1. The diagnosis A/B is over: with a diagnosis 9 of 36 retries passed, without 2 of 32 (stratos report, all
   history). config.DIAGNOSE_ALWAYS (True by default; tests/conftest.py turns it off so the old A/B tests keep
   their meaning): diagnose.use_hint(task_id, attempt) returns True when it is on, else the old hash parity.
2. Tiel's third try: of 56 tasks that reached Tiel's third attempt, 10 passed there (18%; 83 of 174 pass on the
   first, 17 on the second). config.ATTEMPT_PLANS["coder"] becomes [("coder", 2), ("coder_hard", 2)]: two Tiel
   attempts, then two Swift attempts (the same 4 attempts in all). coder_hard's plan stays [("coder_hard", 2),
   ("coder", 1)]."""
import hashlib

from stratos import config, diagnose


def config_source():
    import importlib.util
    return open(importlib.util.find_spec("stratos.config").origin, encoding="utf-8").read()


def test_default_policy():
    # conftest pins ATTEMPT_PLANS for the loop tests, so the policy is read from config.py's source
    text = config_source()
    assert '"coder": [("coder", 2), ("coder_hard", 2)]' in text
    assert '"coder_hard": [("coder_hard", 2), ("coder", 1)]' in text


def test_always_diagnose(monkeypatch):
    monkeypatch.setattr(config, "DIAGNOSE_ALWAYS", True)
    assert all(diagnose.use_hint(f"T{i:03d}", a) for i in range(50) for a in (2, 3))


def test_off_keeps_the_hash_parity(monkeypatch):
    monkeypatch.setattr(config, "DIAGNOSE_ALWAYS", False)
    for tid, attempt in [("T001", 2), ("T002", 3), ("T050", 2)]:
        want = int(hashlib.sha256(f"{tid}:{attempt}".encode("utf-8")).hexdigest(), 16) % 2 == 0
        assert diagnose.use_hint(tid, attempt) is want


def test_on_by_default_outside_the_tests():
    text = config_source()
    assert 'DIAGNOSE_ALWAYS = os.environ.get("STRATOS_DIAGNOSE_ALWAYS", "1") != "0"' in text
