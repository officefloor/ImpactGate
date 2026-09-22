"""Language-agnostic Cognitive Complexity (Campbell, 2018).

ImpactGate's own estimator, computed over one function's source text. It is NOT the
certified SonarSource implementation; it is a deliberately simple, faithful approximation
whose numbers are calibrated against PMD (Java) and eslint-plugin-sonarjs (TypeScript) in
the test suite. It powers an ABSOLUTE per-method gate, and for a gate cross-checkpoint /
cross-PR CONSISTENCY matters more than matching a third party's exact value.

Method (the parts of Campbell's rules that a parser-free scan can carry faithfully):

  * +1 (plus the current NESTING level) for each control-flow structure that nests:
    ``if``, ``for``/``foreach``, ``while``, ``do``, ``switch``, ``catch``.
  * +1 (with NO nesting increment) for a continuation: ``else`` and ``else if`` / ``elif``.
  * +1 for each run of like boolean operators (a run of ``&&`` is one, a run of ``||`` is
    one; switching operator starts a new run).
  * NESTING increases inside every one of those blocks.

Nesting is tracked by braces for the C family and by indentation for Python-like languages.
Two documented simplifications keep it parser-free and cross-language robust: the ternary
``?:`` is not counted (its token is ambiguous with TS optional/nullable syntax), and nested
lambdas/functions do not add a nesting level. Both under-count slightly and uniformly, which
a gate threshold absorbs; the calibration tests pin the residual.
"""
from __future__ import annotations

import re

# Languages whose nesting is indentation-based rather than brace-based.
_PY_EXTS = {"py", "pyw", "pyi"}

_STRIP = re.compile(
    r'"""(?:\\.|[^\\])*?"""|\'\'\'(?:\\.|[^\\])*?\'\'\''      # python triple strings
    r'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''                # normal strings/chars
    r'|`(?:\\.|[^`\\])*`'                                     # JS/TS template strings
    r'|//[^\n]*|/\*.*?\*/'                                    # C-family comments
    r'|#[^\n]*',                                              # python/shell comments
    re.S)

# Control-flow keywords shared across the C family (and most curly-brace languages).
_NEST_KW = {"if", "for", "foreach", "while", "switch", "catch"}   # +1 + nesting, opens a block
_C_TOKEN = re.compile(r"&&|\|\||[{}();]|[A-Za-z_$][A-Za-z0-9_$]*")


def _cognitive_c(source: str) -> int:
    """Brace-nested cognitive complexity for the C family (Java, JS/TS, C/C++, C#, Go, …)."""
    text = _STRIP.sub(" ", source)
    toks = _C_TOKEN.findall(text)
    score = 0
    nesting = 0
    brace_nest: list[int] = []   # per '{': how much nesting it contributed (0 or 1)
    pending = 0                  # nesting to attach to the next '{'
    last_bool: str | None = None
    prev: str | None = None      # previous significant token (for do-while tails)
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t in ("&&", "||"):
            if t != last_bool:
                score += 1
            last_bool = t
            prev = t
            i += 1
            continue
        # A boolean run only breaks at a statement/expression boundary or a keyword — NOT at
        # the operands between the operators, so `a && b && c` is one run, not three.
        if t in (";", "{", "}") or t in _NEST_KW or t in ("do", "else"):
            last_bool = None
        if t == "{":
            brace_nest.append(pending)
            nesting += pending
            pending = 0
        elif t == "}":
            if brace_nest:
                nesting -= brace_nest.pop()
        elif t in _NEST_KW:
            if t == "while" and prev == "}":
                pass                         # do { } while(...) tail — already counted at `do`
            else:
                score += 1 + nesting
                pending = 1
        elif t == "do":
            score += 1 + nesting
            pending = 1
        elif t == "else":
            score += 1                       # else / else-if: +1, no nesting increment
            if i + 1 < n and toks[i + 1] == "if":
                i += 1                        # consume the `if` of `else if`
            pending = 1
        prev = t
        i += 1
    return max(score, 0)


_PY_NEST_KW = {"if", "for", "while", "with", "try"}       # +1 + nesting, opens a block
_PY_CONT_KW = {"elif", "else", "except", "finally"}       # +1, no nesting increment
_PY_LEAD = re.compile(r"^(\s*)(\w+)")
_PY_BOOL = re.compile(r"\b(and|or)\b")


def _cognitive_py(source: str) -> int:
    """Indentation-nested cognitive complexity for Python-like languages."""
    text = _STRIP.sub(" ", source)
    score = 0
    # stack of (indent_of_block_body, contributes_nesting) for open control blocks
    stack: list[tuple[int, int]] = []
    body_indent: int | None = None      # indent of the def body (nesting 0 baseline)
    for raw in text.split("\n"):
        if not raw.strip():
            continue
        m = _PY_LEAD.match(raw)
        if not m:
            continue
        indent = len(m.group(1).expandtabs())
        kw = m.group(2)
        if body_indent is None and kw != "def":
            body_indent = indent
        # pop blocks we have dedented out of
        while stack and indent < stack[-1][0]:
            stack.pop()
        nesting = sum(c for _, c in stack)
        if kw in _PY_NEST_KW:
            score += 1 + nesting
            stack.append((indent + 1, 1))
        elif kw in _PY_CONT_KW:
            score += 1
            stack.append((indent + 1, 1))
        # boolean-operator runs on the line (a run of `and` = 1, of `or` = 1)
        last = None
        for bm in _PY_BOOL.finditer(raw):
            op = bm.group(1)
            if op != last:
                score += 1
            last = op
    return max(score, 0)


def cognitive_complexity(source: str, ext: str = "") -> int:
    """Estimate the Cognitive Complexity of one function's source text. `ext` is the file
    extension (no dot) used only to pick the nesting model; unknown extensions use the
    brace-based C-family scanner, which is the right default for curly-brace languages."""
    if not source or not source.strip():
        return 0
    if ext.lower() in _PY_EXTS:
        return _cognitive_py(source)
    return _cognitive_c(source)
