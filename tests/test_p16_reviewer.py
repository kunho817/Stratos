"""Tests for task reviewer_tiel (P16, 2026-11-21): model switches took 15,155 s over 712 switches, and 7,972 s of it
(53%) were going to the reviewer (Qwen3.6 Q3) and back. On the 10 review cases with a known verdict (scratchpad
review_eval.py --context, 2 runs each): Tiel 9/10 and 9/10, Qwen3.6 9/10 and 9/10, Swift 8/10 and 7/10 - so the
reviewer is now Tiel, the model that writes most tasks: a review after Tiel's writing needs no switch.

config.ROLES["reviewer"] = {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "low", "max_tokens": 4000}.
The learner stays on Qwen3.6 (it runs rarely, after a run)."""
from pathlib import Path

from stratos import config


def test_reviewer_is_tiel():
    text = Path(config.__file__).read_text(encoding="utf-8")
    assert '"reviewer": {"model": "tiel-coder-35b-a3b-ud-q4_k_xl", "effort": "low", "max_tokens": 4000}' in text
    assert config.ROLES["reviewer"]["model"] == config.ROLES["coder"]["model"]
    assert config.LEARNER["model"] == "qwen3.6-35b-a3b-ud-q3_k_m"
