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
- Every value must have exactly the value shape given for its fact (for a list, the same order of elements).

The answer is exactly one ```python block containing the program.
"""


def value_shape(v):
    """Map a value to its shape string."""
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if v is None:
        return "null"
    if isinstance(v, list):
        if len(v) == 0:
            return "list"
        shapes = [value_shape(x) for x in v]
        if all(s == shapes[0] for s in shapes):
            return "list of " + shapes[0]
        return "list [" + ", ".join(shapes) + "]"
    if isinstance(v, dict):
        parts = [f"{k}: {value_shape(v[k])}" for k in sorted(v.keys())]
        return "object {" + ", ".join(parts) + "}"
    return "null"


def fact_shapes(obj):
    """For each fact name in obj, return the sorted list of distinct value shapes of its values."""
    result = {}
    for name in obj:
        shapes = set()
        for key in obj[name]:
            shapes.add(value_shape(obj[name][key]))
        result[name] = sorted(shapes)
    return result


def run_program_full(code, timeout=20):
    """Run code in a temp folder via sys.executable -I, parse stdout as one JSON object.

    Returns (obj, error): obj is the parsed dict on success, None on failure.
    error is None on success, otherwise a short text describing the failure.
    """
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
            stderr = r.stderr.decode("utf-8", errors="replace")
            return (None, f"exit code {r.returncode}: {stderr[-2000:]}")
        stdout = r.stdout.decode("utf-8", errors="replace").strip()
        if not stdout:
            return (None, "no output")
        try:
            obj = json.loads(stdout)
        except json.JSONDecodeError:
            return (None, f"output is not JSON: {stdout[:200]}")
        if not isinstance(obj, dict):
            return (None, "output is not a JSON object")
        return (obj, None)
    except subprocess.TimeoutExpired:
        return (None, f"timed out after {timeout} s")
    except Exception as e:
        return (None, f"could not run: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_program(code, timeout=20):
    """Run code in a temp folder via sys.executable -I, parse stdout as one JSON object."""
    return run_program_full(code, timeout)[0]


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


def derive(gw, rules, log=print, keep=None):
    """Ask two independent models to compute the facts and compare their outputs.

    Returns {"facts": dict|None, "reason": str}.
    When keep is a dict, sets keep["a"], keep["b"] to the objects the two programs
    printed (None for a program that did not run or failed), and also sets
    keep["a_program"], keep["b_program"] (code text or None) and
    keep["a_error"], keep["b_error"] (error text or None).
    """
    # Step 1: ask REF_WRITER with SYSTEM_A as system, rules as user
    answer_a = _chat(gw, config.REF_WRITER, SYSTEM_A, rules)
    stripped = answer_a.strip()
    if stripped == "NONE":
        if keep is not None:
            keep["a"] = None
            keep["b"] = None
            keep["a_program"] = None
            keep["b_program"] = None
            keep["a_error"] = None
            keep["b_error"] = None
        return {"facts": None, "reason": "none"}

    code_a = _extract_code(answer_a)
    if code_a is None:
        if keep is not None:
            keep["a"] = None
            keep["b"] = None
            keep["a_program"] = None
            keep["b_program"] = None
            keep["a_error"] = "no program in the answer"
            keep["b_error"] = None
        return {"facts": None, "reason": "program A failed"}

    obj_a, err_a = run_program_full(code_a)
    if obj_a is None:
        if keep is not None:
            keep["a"] = None
            keep["b"] = None
            keep["a_program"] = code_a
            keep["b_program"] = None
            keep["a_error"] = err_a
            keep["b_error"] = None
        return {"facts": None, "reason": "program A failed"}

    # Validate: every fact value must be a dict
    a_fact_valid = True
    for name in obj_a:
        if not isinstance(obj_a[name], dict):
            a_fact_valid = False
            break
    if not a_fact_valid:
        if keep is not None:
            keep["a"] = None
            keep["b"] = None
            keep["a_program"] = code_a
            keep["b_program"] = None
            keep["a_error"] = "a fact is not a JSON object"
            keep["b_error"] = None
        return {"facts": None, "reason": "program A failed"}

    # Step 2: ask B with SYSTEM_B + A's fact names, keys, and value shapes
    shapes = fact_shapes(obj_a)
    blocks = []
    for name in sorted(obj_a.keys()):
        keys_str = json.dumps(sorted(obj_a[name].keys()))
        shapes_str = " or ".join(shapes[name])
        blocks.append(f"{name}: {keys_str}\n  value shape: {shapes_str}")
    keys_text = "\n".join(blocks)
    user_b = rules + "\n\nFact names, input keys and value shapes:\n" + keys_text
    answer_b = _chat(gw, config.ROLES[config.FACTS_B_ROLE], SYSTEM_B, user_b)

    code_b = _extract_code(answer_b)
    if code_b is None:
        if keep is not None:
            keep["a"] = obj_a
            keep["b"] = None
            keep["a_program"] = code_a
            keep["b_program"] = None
            keep["a_error"] = None
            keep["b_error"] = "no program in the answer"
        return {"facts": None, "reason": "program B failed"}

    obj_b, err_b = run_program_full(code_b)
    if obj_b is None:
        if keep is not None:
            keep["a"] = obj_a
            keep["b"] = None
            keep["a_program"] = code_a
            keep["b_program"] = code_b
            keep["a_error"] = None
            keep["b_error"] = err_b
        return {"facts": None, "reason": "program B failed"}

    # Validate: every fact value must be a dict
    b_fact_valid = True
    for name in obj_b:
        if not isinstance(obj_b[name], dict):
            b_fact_valid = False
            break
    if not b_fact_valid:
        if keep is not None:
            keep["a"] = obj_a
            keep["b"] = None
            keep["a_program"] = code_a
            keep["b_program"] = code_b
            keep["a_error"] = None
            keep["b_error"] = "a fact is not a JSON object"
        return {"facts": None, "reason": "program B failed"}

    # Set keep values
    if keep is not None:
        keep["a"] = obj_a
        keep["b"] = obj_b
        keep["a_program"] = code_a
        keep["b_program"] = code_b
        keep["a_error"] = None
        keep["b_error"] = None

    # Step 3: compare
    if obj_a == obj_b:
        return {"facts": obj_a, "reason": "agree"}

    # Step 4: disagree - collect up to 5 lines
    diffs = []
    all_names = sorted(set(list(obj_a.keys()) + list(obj_b.keys())))
    for name in all_names:
        if len(diffs) >= 5:
            break
        if name in obj_a and name not in obj_b:
            diffs.append(f"{name}: only in A")
            continue
        if name in obj_b and name not in obj_a:
            diffs.append(f"{name}: only in B")
            continue
        # both have this fact name
        a_keys = obj_a[name]
        b_keys = obj_b[name]
        all_keys = sorted(set(list(a_keys.keys()) + list(b_keys.keys())))
        for key in all_keys:
            if len(diffs) >= 5:
                break
            in_a = key in a_keys
            in_b = key in b_keys
            if in_a and in_b:
                if a_keys[key] == b_keys[key]:
                    continue  # equal values never listed
                diffs.append(f"{name} {key}: {json.dumps(a_keys[key])} vs {json.dumps(b_keys[key])}")
            elif in_a:
                diffs.append(f"{name} {key}: {json.dumps(a_keys[key])} vs null")
            else:
                diffs.append(f"{name} {key}: null vs {json.dumps(b_keys[key])}")
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
