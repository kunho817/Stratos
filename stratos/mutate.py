import re


def _code_flags(line):
    """Return a list of booleans for each character in `line` indicating if it is code (outside strings and comments)."""
    flags = [True] * len(line)
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '#':
            for j in range(i, len(line)):
                flags[j] = False
            break
        if line[i:i+2] == '//':
            for j in range(i, len(line)):
                flags[j] = False
            break
        if ch in ("'", '"'):
            quote = ch
            j = i + 1
            flags[i] = False
            while j < len(line):
                flags[j] = False
                if line[j] == '\\':
                    j += 2
                    continue
                if line[j] == quote:
                    j += 1
                    break
                j += 1
            i = j
            continue
        i += 1
    return flags


OPS = [
    (" <= ", " < "),
    (" >= ", " > "),
    (" < ", " <= "),
    (" > ", " >= "),
    (" == ", " != "),
    (" != ", " == "),
    (" + ", " - "),
    (" - ", " + "),
    (" and ", " or "),
    (" or ", " and "),
    (" && ", " || "),
    (" || ", " && "),
]


def _line_mutants(line):
    """Return list of (position, operator_index, start, end, replacement) for one line."""
    flags = _code_flags(line)
    results = []
    for op_idx, (old, new) in enumerate(OPS):
        start = 0
        while True:
            pos = line.find(old, start)
            if pos == -1:
                break
            if all(flags[pos:pos + len(old)]):
                results.append((pos, op_idx, pos, pos + len(old), new))
            start = pos + 1

    # True/False/true/false
    for m in re.finditer(r'\bTrue\b', line):
        s, e = m.start(), m.end()
        if all(flags[s:e]):
            results.append((s, 12, s, e, "False"))
    for m in re.finditer(r'\bFalse\b', line):
        s, e = m.start(), m.end()
        if all(flags[s:e]):
            results.append((s, 13, s, e, "True"))
    for m in re.finditer(r'\btrue\b', line):
        s, e = m.start(), m.end()
        if all(flags[s:e]):
            results.append((s, 14, s, e, "false"))
    for m in re.finditer(r'\bfalse\b', line):
        s, e = m.start(), m.end()
        if all(flags[s:e]):
            results.append((s, 15, s, e, "true"))

    # integers
    for m in re.finditer(r'(?<![\w.])\d+(?![\w.])', line):
        s, e = m.start(), m.end()
        if all(flags[s:e]):
            results.append((s, 16, s, e, str(int(m.group()) + 1)))

    results.sort(key=lambda t: (t[0], t[1]))
    return results


def _is_blank_or_comment(stripped):
    return not stripped or stripped.startswith(("#", "//", "/*", "*"))


def mutants(source, limit=12):
    lines = source.splitlines(keepends=True)
    n_lines = len(lines)

    # Determine which lines to skip (triple-quoted blocks)
    skip = [False] * n_lines
    in_block = False
    for idx, raw in enumerate(lines):
        count = raw.count('"""') + raw.count("'''")
        if count == 0:
            if in_block:
                skip[idx] = True
            continue
        if in_block:
            skip[idx] = True
            if count % 2 == 1:   # (Claude) only an odd count closes the block, as the spec says
                in_block = False
        else:
            if count % 2 == 0:
                skip[idx] = True
            else:
                skip[idx] = True
                in_block = True

    all_mutants = []
    for idx, raw in enumerate(lines):
        if skip[idx]:
            continue
        stripped = raw.lstrip()
        if _is_blank_or_comment(stripped):
            continue

        # Separate line ending
        if raw.endswith('\r\n'):
            line_content = raw[:-2]
            ending = '\r\n'
        elif raw.endswith('\n'):
            line_content = raw[:-1]
            ending = '\n'
        elif raw.endswith('\r'):
            line_content = raw[:-1]
            ending = '\r'
        else:
            line_content = raw
            ending = ''

        lm = _line_mutants(line_content)
        for (pos, op_idx, start, end, repl) in lm:
            new_content = line_content[:start] + repl + line_content[end:]
            new_line = new_content + ending
            # Build source: all lines unchanged except this one
            source_parts = []
            for j in range(n_lines):
                if j == idx:
                    source_parts.append(new_line)
                else:
                    source_parts.append(lines[j])
            new_source = ''.join(source_parts)
            all_mutants.append({
                "line": idx + 1,
                "old": raw,
                "new": new_line,
                "source": new_source,
            })

    # Apply limit
    if limit <= 0:
        return []
    n = len(all_mutants)
    if n <= limit:
        return all_mutants

    # Spread evenly
    result = []
    for i in range(limit):
        if limit == 1:
            idx = 0
        else:
            idx = round(i * (n - 1) / (limit - 1))
        result.append(all_mutants[idx])
    return result
