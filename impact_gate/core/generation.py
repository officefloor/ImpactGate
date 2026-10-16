"""Coupling-generation ("god math"), vendored from the coupling-divergence project.

Language-independent on top of lizard, the same substrate the rest of impact-gate uses.
For each function, over its calls to OUR OWN code (a callee whose name is a function
defined somewhere in the tree), count the arguments it pushes (out_gen), the arguments
pushed into it by callers (in_gen), and gain = max(out_gen - in_gen, 0): the coupling flow
the function MANUFACTURES. A god is a placement outlier in gain, the node everything flows
out of. This is a snapshot (placement) property: it needs no history. Calls that leave the
tree (library, SQL) do not count, which excludes converters and mappers with no type test.
"""
from __future__ import annotations

import os
import re

import lizard

SOURCE_EXTS = {
    ".java", ".kt", ".scala", ".groovy", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp",
    ".m", ".mm", ".cs", ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rb", ".php",
    ".swift", ".rs", ".lua",
}
NOT_CALL = {
    "if", "while", "for", "switch", "catch", "return", "synchronized", "with", "elif",
    "foreach", "lock", "using", "when", "match", "do", "else", "case", "and", "or", "not",
    "in", "is", "assert", "throw", "throws", "yield", "await", "func", "def", "function",
    "sub", "super", "this", "self",
}
_STRIP = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`'
    r'|//[^\n]*|#[^\n]*|/\*.*?\*/', re.S)
_TEST_DIR = re.compile(r"(?:^|/)(?:test|tests|testing|spec|__tests__)(?:/|$)")
OUTLIER_Z = 3.5
WMC_GOD = 47
# Dependency/build/vendored/generated trees are not the project's own code (a single
# vendored tree-sitter parser.c can be ~100 MB), and a file over this size is a
# generated/minified blob, not a hand-maintained unit. Both are skipped, which also keeps
# the lexical scan from stalling on a giant generated file.
_SKIP_DIRS = {".git", "node_modules", "build", "target", "dist", ".venv", "venv",
              "vendor", "vendored", "third_party", "thirdparty", "third-party",
              "generated", "externals", "external", "deps", ".gradle", "out"}
MAX_FILE_BYTES = 1_000_000


def source_files(root: str, include_tests: bool = False) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in SOURCE_EXTS:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            if not include_tests and _TEST_DIR.search("/" + rel.replace(os.sep, "/")):
                continue
            try:
                if os.path.getsize(os.path.join(dirpath, fn)) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            out.append(rel)
    return out


def call_sites(body: str):
    """Yield (callee name, argument count) for every call expression in `body`."""
    i, n = 0, len(body)
    while i < n:
        if body[i] == "(":
            j = i - 1
            while j >= 0 and body[j].isspace():
                j -= 1
            if j >= 0 and (body[j].isalnum() or body[j] in "_$"):
                k = j
                while k >= 0 and (body[k].isalnum() or body[k] in "_$"):
                    k -= 1
                word = body[k + 1:j + 1]
                depth, p, args, content = 0, i, 0, False
                while p < n:
                    c = body[p]
                    if c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    elif c == "," and depth == 1:
                        args += 1
                    elif depth == 1 and not c.isspace():
                        content = True
                    p += 1
                yield word, (args + 1 if content else 0)
                i = p + 1
                continue
        i += 1


def _short(name: str) -> str:
    return name.split("::")[-1].split(".")[-1]


def analyze_tree(root: str, include_tests: bool = False) -> dict:
    """{"funcs": {(file, short): {out_gen, in_gen, gain, cc, file, name}}, "wmc": {file: cc}}."""
    cache: dict = {}
    raw: list = []
    for rel in source_files(root, include_tests):
        path = os.path.join(root, rel)
        try:
            analysis = lizard.analyze_file(path)
        except Exception:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                cache[rel] = fh.read().splitlines()
        except OSError:
            continue
        for fn in analysis.function_list:
            raw.append((rel, _short(fn.name), int(fn.cyclomatic_complexity),
                        int(fn.start_line), int(fn.end_line)))
    if not raw:
        return {"funcs": {}, "wmc": {}}
    names = {r[1] for r in raw}
    out_gen: dict = {}
    in_by_name: dict = {}
    cc_of: dict = {}
    for rel, short, cc, start, end in raw:
        fid = (rel, short)
        cc_of[fid] = max(cc_of.get(fid, 0), cc)
        body = "\n".join(cache.get(rel, [])[max(start - 1, 0):end])
        body = _STRIP.sub(lambda m: " " * len(m.group(0)), body)
        og = 0
        for callee, nargs in call_sites(body):
            if callee in NOT_CALL or nargs == 0 or callee not in names:
                continue
            og += nargs
            in_by_name[callee] = in_by_name.get(callee, 0) + nargs
        out_gen[fid] = out_gen.get(fid, 0) + og
    wmc: dict = {}
    for rel, short, cc, _s, _e in raw:
        wmc[rel] = wmc.get(rel, 0) + cc
    funcs: dict = {}
    for fid in set(out_gen) | set(cc_of):
        og = out_gen.get(fid, 0)
        ig = in_by_name.get(fid[1], 0)
        funcs[fid] = {"file": fid[0], "name": fid[1], "cc": cc_of.get(fid, 0),
                      "out_gen": og, "in_gen": ig, "gain": max(og - ig, 0)}
    return {"funcs": funcs, "wmc": wmc}


def modified_z(values: list[float]):
    xs = sorted(v for v in values if v > 0)
    n = len(xs)
    if n == 0:
        return lambda x: 0.0
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    dev = sorted(abs(x - med) for x in xs)
    mad = dev[n // 2] if n % 2 else (dev[n // 2 - 1] + dev[n // 2]) / 2
    if mad > 0:
        return lambda x: 0.6745 * (x - med) / mad
    mad2 = sum(abs(x - med) for x in xs) / n
    return (lambda x: (x - med) / (1.2533 * mad2)) if mad2 > 0 else (lambda x: 0.0)


def outliers(funcs: dict) -> set:
    gains = {fid: r["gain"] for fid, r in funcs.items() if r["gain"] > 0}
    if not gains:
        return set()
    z = modified_z(list(gains.values()))
    return {fid for fid, g in gains.items() if z(g) >= OUTLIER_Z}


def class_gain(funcs: dict) -> dict:
    cg: dict = {}
    for fid, r in funcs.items():
        cg[fid[0]] = cg.get(fid[0], 0) + r["gain"]
    return cg


def class_outliers(cg: dict) -> set:
    xs = [v for v in cg.values() if v > 0]
    if not xs:
        return set()
    z = modified_z(xs)
    return {f for f, v in cg.items() if v > 0 and z(v) >= OUTLIER_Z}
