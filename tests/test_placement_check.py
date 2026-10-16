"""Per-change placement check: a change that wires more flow through a handler is flagged
as touching a coupling vortex; a change that only edits a small self-contained unit is not.

The tree has a dozen small generators (each pushes two arguments to shared helpers, gain 2)
plus a handler that pushes many. That distribution is what the handler must stand out from;
a lone generator is correctly not an outlier."""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from impact_gate import placement_check


def _git(root, *a):
    subprocess.run(["git", "-C", root, *a], check=True, capture_output=True)


def _util():
    return ("public class Util {\n"
            "    public static int help1(int a) { return a * 2; }\n"
            "    public static int help2(int b) { return b + 1; }\n}\n")


def _gen(i):
    # a small generator: two single-arg pushes to our helpers -> gain 2
    return (f"public class Gen{i} {{\n    public int gen{i}(int x) {{\n"
            f"        int p = Util.help1(x);\n        int q = Util.help2(x);\n"
            f"        return p + q;\n    }}\n}}\n")


def _controller(k):
    # the handler pushes k single-arg calls -> gain k; big k makes it the outlier
    calls = "\n".join("        Util.help1(a);" for _ in range(k))
    return ("public class Controller {\n    public int handle(int a) {\n"
            f"{calls}\n        return a;\n    }}\n}}\n")


def _repo():
    root = tempfile.mkdtemp(prefix="ig_placement_")
    _git(root, "init", "-q"); _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t"); _git(root, "checkout", "-q", "-b", "main")
    open(os.path.join(root, "Util.java"), "w").write(_util())
    for i in range(12):
        open(os.path.join(root, f"Gen{i}.java"), "w").write(_gen(i))
    open(os.path.join(root, "Controller.java"), "w").write(_controller(4))
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "base")
    return root


def test_wiring_change_flags_the_handler_vortex():
    root = _repo()
    open(os.path.join(root, "Controller.java"), "w").write(_controller(20))
    _git(root, "commit", "-qam", "wire much more through handle")
    res = placement_check.check(root, mode="range", base="HEAD~1")
    assert "handle" in {f.name for f in res["method_vortex_flags"]}, res


def test_small_unit_change_is_not_flagged():
    root = _repo()
    open(os.path.join(root, "Gen0.java"), "w").write(_gen(0).replace("p + q", "p * q + 1"))
    _git(root, "commit", "-qam", "tweak Gen0 arithmetic")
    res = placement_check.check(root, mode="range", base="HEAD~1")
    assert res["method_vortex_flags"] == [], res


if __name__ == "__main__":
    ok = True
    for fn in (test_wiring_change_flags_the_handler_vortex, test_small_unit_change_is_not_flagged):
        try:
            fn(); print(f"  [PASS] {fn.__name__}")
        except AssertionError as e:
            ok = False; print(f"  [FAIL] {fn.__name__}: {e}")
    root = _repo()
    open(os.path.join(root, "Controller.java"), "w").write(_controller(20))
    subprocess.run(["git", "-C", root, "commit", "-qam", "x"], check=True, capture_output=True)
    print("\n--- render on the wiring change ---")
    print(placement_check.render(placement_check.check(root, mode="range", base="HEAD~1")))
    print("\nOVERALL:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
