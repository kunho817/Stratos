"""Client for Jev, TypeSafe AI's decision model (System One).

API (docs.typesafe.ai/api): POST https://api.typesafe.ai/v1/systemone, header "Authorization: Bearer <key>",
body {"model", "state", "questions": {name: question}}; a "choice" question has "criteria" {option: description} and
its answer is {"type": "choice", "choice", "confidence", "probabilities"}; a "noul" question is a yes/no and its answer
is {"type": "noul", "noul": probability of yes}. The response also carries "model" and "usage": {"input_tokens", ...}.

URL, MODEL ("jev-1.14.0", pinned so the probabilities stay comparable)

api_key() -> str | None
    TYPESAFE_API_KEY from the environment; on Windows, when it is not there, the user's stored variable
    (HKEY_CURRENT_USER\\Environment), because a session started before the key was set does not see it. None if absent.

ask(state, questions, key=None, post=None, timeout=10, retries=2, sleep=time.sleep) -> dict
    Never raises. post(url, body: bytes, headers: dict, timeout) -> (status: int, body: bytes); the default uses
    urllib. key defaults to api_key(). Returns {"ok": True, "answers", "model", "input_tokens", "seconds"} on HTTP 200,
    else {"ok": False, "error": str, "seconds"}. A missing key gives ok False without calling post. Status 429 and
    529 and exceptions raised by post are retried up to `retries` more times, sleeping 1 s, 2 s, ... between tries;
    other statuses (400, 401, 422, ...) are not retried. The error text carries the status code (or the exception).

role_request(task) -> (state, questions)
    Only a summary of the task goes out: state is {"goal": task goal, "files": task files, "file_count": n}; nothing
    read from disk. One question "role", type "choice", with exactly the criteria keys "coder" and "coder_hard".

choose_role(task, **ask_kwargs) -> decision | None
    {"choice": the answer's choice, "confidence": the answer's confidence, "reason": text naming Jev and the
    probabilities} like decide.choose_role, plus "input_tokens"; None when ask fails or the answer is malformed.

escalate_request(task, history) -> (state, questions)
    history: [(result, detail), ...] of the current role's attempts, oldest first. Only a summary goes out: state is
    {"goal": task goal, "files": task files, "attempts": [one dict per attempt: {"result": result,
    "failed_tests": decide.failure_signature(result, detail)}]}, except that a signature starting with "E " (an error
    line, which may quote code or data) is sent as "". One question "switch", type "noul".

should_escalate(task, history, **ask_kwargs) -> decision | None
    {"choice": p >= 0.5, "confidence": max(p, 1 - p), "reason": text naming Jev and p, "input_tokens"}; None when ask
    fails or the answer has no number "noul".
"""
import json
import os
import time
import urllib.error
import urllib.request

from . import decide

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"


def api_key():
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                value, _type = winreg.QueryValueEx(handle, "TYPESAFE_API_KEY")
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return value
        except (OSError, ImportError):
            return None
    return None


def _default_post(url, body, headers, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        return (error.code, error.read())
    try:
        return (response.status, response.read())
    finally:
        response.close()


def ask(state, questions, key=None, post=None, timeout=10, retries=2, sleep=time.sleep):
    start = time.monotonic()
    if not key:
        key = api_key()
    if not key:
        return {"ok": False, "error": "missing api key", "seconds": time.monotonic() - start}
    if post is None:
        post = _default_post
    headers = {
        "Authorization": "Bearer " + str(key),
        "Content-Type": "application/json",
        "User-Agent": "stratos",
    }
    data = json.dumps({"model": MODEL, "state": state, "questions": questions}).encode("utf-8")
    total = 1 + retries
    for attempt in range(1, total + 1):
        failure = None
        status = None
        body = b""
        try:
            status, body = post(URL, data, headers, timeout)
        except Exception as error:  # noqa: BLE001 - ask must never raise
            failure = error
        seconds = time.monotonic() - start
        if failure is None and status == 200:
            payload = None
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception:
                payload = None
            if isinstance(payload, dict):
                usage = payload.get("usage") or {}
                input_tokens = usage.get("input_tokens") or 0
                return {
                    "ok": True,
                    "answers": payload.get("answers"),
                    "model": payload.get("model"),
                    "input_tokens": input_tokens,
                    "seconds": seconds,
                }
            return {"ok": False, "error": "invalid json response", "seconds": seconds}
        error_text = "http " + str(status) if failure is None else str(failure)
        retryable = failure is not None or status in (429, 529)
        if not retryable or attempt >= total:
            return {"ok": False, "error": error_text, "seconds": seconds}
        sleep(attempt)
    return {"ok": False, "error": "retries exhausted", "seconds": time.monotonic() - start}


def role_request(task):
    goal = task.get("goal")
    files = task.get("files") or []
    state = {"goal": goal, "files": files, "file_count": len(files)}
    questions = {
        "role": {
            "type": "choice",
            "instructions": (
                "Which local coding model should take this task? coder is the fast model, strong at new "
                "functions and small additions in one file; coder_hard is the slow, careful model, for changes "
                "to existing control flow or work across several files."
            ),
            "criteria": {
                "coder": "Fast model; strong at new functions and small additions in one file.",
                "coder_hard": "Slow, careful model; for changes to existing control flow or work across several files.",
            },
        }
    }
    return state, questions


def choose_role(task, **ask_kwargs):
    state, questions = role_request(task)
    result = ask(state, questions, **ask_kwargs)
    if not result.get("ok"):
        return None
    answers = result.get("answers")
    answer = answers.get("role") if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        return None
    choice = answer.get("choice")
    confidence = answer.get("confidence")
    if choice not in ("coder", "coder_hard"):
        return None
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return None
    probabilities = answer.get("probabilities") or {}
    reason = "jev: coder {}, coder_hard {}".format(
        probabilities.get("coder", 0.0), probabilities.get("coder_hard", 0.0)
    )
    return {
        "choice": choice,
        "confidence": confidence,
        "reason": reason,
        "input_tokens": result.get("input_tokens"),
    }


def escalate_request(task, history):
    goal = task.get("goal")
    files = task.get("files") or []
    attempts = []
    for result, detail in history:
        signature = decide.failure_signature(result, detail)
        if isinstance(signature, str) and signature.startswith("E "):
            signature = ""
        attempts.append({"result": result, "failed_tests": signature})
    state = {"goal": goal, "files": files, "attempts": attempts}
    questions = {
        "switch": {
            "type": "noul",
            "instructions": (
                "A local coding model is failing this task. Given its attempts so far, should the task go to the "
                "other, slower and more careful model now, instead of another try with the same model?"
            ),
            "criteria": {
                "true": "yes: the attempts repeat the same failure or show the model cannot do this task",
                "false": "no: another try with the same model is likely to pass",
            },
        }
    }
    return state, questions


def should_escalate(task, history, **ask_kwargs):
    state, questions = escalate_request(task, history)
    result = ask(state, questions, **ask_kwargs)
    if not result.get("ok"):
        return None
    answers = result.get("answers")
    answer = answers.get("switch") if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        return None
    p = answer.get("noul")
    if not isinstance(p, (int, float)) or isinstance(p, bool):
        return None
    return {
        "choice": p >= 0.5,
        "confidence": max(p, 1 - p),
        "reason": "jev: switch probability {}".format(p),
        "input_tokens": result.get("input_tokens"),
    }
