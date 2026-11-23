"""Facts: ask two independent models to compute facts from rules, run their programs, compare results."""
import json
import subprocess
import sys
import tempfile
import shutil

from . import config


SYSTEM_A = """You must write a Python 3 program that computes facts from the rules and prints exactly ONE JSON object.

The JSON object has the form { "<fact name>": { "<input as a string>": <value>, ... }, ... }
- Each fact name is a short string describing what is computed.
- Each key is a string representing one small, finite combination of rule inputs.
- Each value is computed by code from the rules, never typed in by hand.
- A value that is a set is printed as a sorted list.
- At most 400 input keys in all across all facts.

The answer is exactly one ```python block containing the program, or the single word NONE when the rules give nothing small and finite.
"""

SYSTEM_B = """You must write a Python 3 program that computes the facts for the given fact names and input keys from the rules.
The program prints exactly ONE JSON object in the form { "<fact name>": { "<input key>": <value>, ... }, ... }
- You are given the fact names and the input keys. Compute values from the rules; never use the values directly.
- A value that is a set is printed as a sorted list.

The answer is exactly one ```python block containing the program.
"""


def run_program(code, timeout=20):
    """Run code in a temp folder via sys.executable -I, parse stdout as one JSON object."""
    tmp = tempfile.mkdtemp()
    code_file = tmp + "/prog.py"
    with open(code_file, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        r = subprocess.run(
            [sys.executable, "-I", code_file],
            timeout=timeout,
            capture_output=True,
            cwd=tmp,
        )
        if r.returncode != 0:
            return None
        stdout = r.stdout.decode("utf-8", errors="replace").strip()
        if not stdout:
            return None
        obj = json.loads(stdout)
        if not isinstance(obj, dict):
            return None
        return obj
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _extract_code(text):
    """Take the program from the first ```python block (or the only fenced block)."""
    if "```python\n" in text:
        start = text.index("```python\n") + len("```python\n")
        end = text.index("```", start)
        return text[start:end]
    # fallback: the only fenced block
    if "```" in text:
        start = text.index("```")
        # skip the language tag line
        nl = text.index("\n", start) + 1
        end = text.index("```", nl)
        return text[nl:end]
    return None


def _chat(gw, cfg, prompt, extra):
    """Call gw.chat with the cfg model settings."""
    gw.ensure_model(cfg["model"])
    messages = [{"role": "system", "content": prompt},
                {"role": "user", "content": extra}]
    kwargs = {
        "task": "facts",
        "role": "facts",
        "attempt": 1,
        "model": cfg["model"],
        "effort": cfg["effort"],
        "max_tokens": cfg["max_tokens"],
    }
    if "reasoning_budget" in cfg:
        kwargs["reasoning_budget"] = cfg["reasoning_budget"]
    _, answer = gw.chat(messages, **kwargs)
    return answer


def derive(gw, rules, log=print):
    """Ask two independent models to compute the facts and compare their outputs.

    Returns {"facts": dict|None, "reason": str}.
    """
    # Step 1: ask REF_WRITER with SYSTEM_A as system, rules as user
    answer_a = _chat(gw, config.REF_WRITER, SYSTEM_A, rules)
    stripped = answer_a.strip()
    if stripped == "NONE":
        return {"facts": None, "reason": "none"}

    code_a = _extract_code(answer_a)
    if code_a is None:
        return {"facts": None, "reason": "program A failed"}
    obj_a = run_program(code_a)
    if obj_a is None:
        return {"facts": None, "reason": "program A failed"}

    # Validate: every fact value must be a dict
    for name in obj_a:
        if not isinstance(obj_a[name], dict):
            return {"facts": None, "reason": "program A failed"}

    # Step 2: ask coder with SYSTEM_B + A's fact names and keys
    keys_text = "\n".join(f"{name}: {json.dumps(sorted(obj_a[name].keys()))}"
                          for name in sorted(obj_a.keys()))
    user_b = rules + "\n\nFact names and input keys:\n" + keys_text
    answer_b = _chat(gw, config.ROLES["coder"], SYSTEM_B, user_b)

    code_b = _extract_code(answer_b)
    if code_b is None:
        return {"facts": None, "reason": "program B failed"}
    obj_b = run_program(code_b)
    if obj_b is None:
        return {"facts": None, "reason": "program B failed"}

    # Validate: every fact value must be a dict
    for name in obj_b:
        if not isinstance(obj_b[name], dict):
            return {"facts": None, "reason": "program B failed"}

    # Step 3: compare
    if obj_a == obj_b:
        return {"facts": obj_a, "reason": "agree"}

    # Step 4: disagree - collect up to 5 lines
    diffs = []
    all_names = sorted(set(list(obj_a.keys()) + list(obj_b.keys())))
    for name in all_names:
        a_keys = obj_a.get(name, {})
        b_keys = obj_b.get(name, {})
        all_keys = sorted(set(list(a_keys.keys()) + list(b_keys.keys())))
        for key in all_keys:
            a_val = a_keys.get(key)
            b_val = b_keys.get(key)
            diffs.append(f"{name} {key}: {json.dumps(a_val)} vs {json.dumps(b_val)}")
            if len(diffs) >= 5:
                break
        if len(diffs) >= 5:
            break
    reason = "disagree: " + "\n".join(diffs[:5])
    return {"facts": None, "reason": reason}


def render(facts):
    """Render facts as text: sorted names, each 'name:' then '  key -> value_as_json' per key sorted."""
    lines = []
    for name in sorted(facts.keys()):
        lines.append(name + ":")
        for key in sorted(facts[name].keys()):
            lines.append("  " + key + " -> " + json.dumps(facts[name][key]))
    return "\n".join(lines)

