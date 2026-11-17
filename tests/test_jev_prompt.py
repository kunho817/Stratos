"""Tests for task T033: the role question asks about the LOCAL coding models (T032's said "Choose the Jev model",
which is not what is being chosen), and role_request reads the task plainly."""
from stratos import jev


def test_the_question_is_about_the_local_coding_models():
    _, questions = jev.role_request({"goal": "g", "files": ["stratos/a.py"]})
    text = questions["role"]["instructions"]
    assert "local coding model" in text.lower()
    assert "jev" not in text.lower()


def test_a_task_without_files():
    state, _ = jev.role_request({"goal": "g"})
    assert state == {"goal": "g", "files": [], "file_count": 0}
