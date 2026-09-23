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
Ternaries (``a ? b : c``) count as +1 plus nesting; the tokenizer separates TS optional
chaining (``?.``), nullish (``??``) and optional-member (``?:``) so they do not false-fire.
A lambda body (after ``->`` in Java or ``=>`` in JS/TS) adds a nesting level, so control flow
inside a stream/callback is charged for its depth. The calibration tests pin the numbers
against PMD (Java) and hand-verified values.
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
# Order matters: the multi-char '?' forms come before the bare '?' so TS optional chaining (?.),
# nullish (??) and optional-member (?:) are tokenised out and do NOT count as ternaries. Lambda
# arrows (-> for Java, => for JS/TS) are tokens too, so a lambda body adds a nesting level.
_C_TOKEN = re.compile(r"\?\?|\?\.|\?:|->|=>|&&|\|\||[?{}();]|[A-Za-z_$][A-Za-z0-9_$]*")


class _CScan:
    """Mutable state for the C-family cognitive walk. Each step is a one-liner so the walk
    loop stays flat (and this scanner stays under its own gate)."""

    def __init__(self) -> None:
        self.score = 0
        self.nesting = 0
        self._brace: list[int] = []      # per '{': the nesting it added (0 or 1)
        self._pending = 0                # nesting to attach to the next '{'
        self._last_bool: str | None = None
        self.prev: str | None = None     # previous token (for do-while tails)
        self._arrow = False              # previous token was a lambda arrow (-> / =>)

    def boolean(self, op: str) -> None:
        if op != self._last_bool:        # a run of like operators counts once
            self.score += 1
        self._last_bool = op

    def end_bool_run(self) -> None:
        self._last_bool = None

    def ternary(self) -> None:           # a ? b : c — +1 + depth, no block
        self.score += 1 + self.nesting

    def open_brace(self, lambda_block: bool = False) -> None:
        add = 1 if (self._pending or lambda_block) else 0   # control block or lambda body nests
        self._brace.append(add)
        self.nesting += add
        self._pending = 0

    def close_brace(self) -> None:
        if self._brace:
            self.nesting -= self._brace.pop()

    def nest(self) -> None:              # if/for/while/switch/catch/do: +1 + depth, block nests
        self.score += 1 + self.nesting
        self._pending = 1

    def cont(self) -> None:              # else / else-if: +1, no depth, block nests
        self.score += 1
        self._pending = 1


def _cognitive_c(source: str) -> int:
    """Brace-nested cognitive complexity for the C family (Java, JS/TS, C/C++, C#, Go, …)."""
    toks = _C_TOKEN.findall(_STRIP.sub(" ", source))
    s = _CScan()
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        arrow = s._arrow                 # did a lambda arrow immediately precede this token?
        s._arrow = False
        if t in ("&&", "||"):            # boolean run — operands between operators don't break it
            s.boolean(t)
        elif t == "?":                   # ternary (bare '?'; ?. ?? ?: are separate tokens, ignored)
            s.end_bool_run(); s.ternary()
        elif t in ("->", "=>"):          # lambda arrow: the block it opens adds a nesting level
            s._arrow = True
        elif t == "{":
            s.end_bool_run(); s.open_brace(lambda_block=arrow)
        elif t == "}":
            s.end_bool_run(); s.close_brace()
        elif t == "do":
            s.end_bool_run(); s.nest()
        elif t == "else":
            s.end_bool_run(); s.cont()
            if i + 1 < n and toks[i + 1] == "if":
                i += 1                    # consume the `if` of `else if`
        elif t in _NEST_KW and not (t == "while" and s.prev == "}"):   # skip do{}while tail
            s.end_bool_run(); s.nest()
        elif t == ";":
            s.end_bool_run()
        s.prev = t
        i += 1
    return max(s.score, 0)


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
