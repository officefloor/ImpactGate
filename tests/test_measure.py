"""Layer 1: the measure, with exact hand-verified numbers.

Fixtures are module-level functions with cyclomatic complexity 1. lizard reports them
at file scope (container ""), with the line ranges asserted in the probe. So every
cost = max(WMC_other, 1) * CC(1) * dlines is computable by hand. ChangedFile is passed
directly, so the diff ranges are controlled and no git is involved.
"""
from impact_gate.engine import ChangedFile, score_change

ONE = b"def f():\n    return 1\n"                    # f: lines 1-2, cc 1

THREE = (b"def f():\n    return 1\n\n"               # f: 1-2
         b"def g():\n    return 2\n\n"               # g: 4-5
         b"def h():\n    return 3\n")                # h: 7-8


def test_isolated_new_file_floors_wmc_to_one():
    # New file, one new function. No prior container, so WMC_other floors to 1.
    # cost = 1 * 1 * 2  (dlines = the 2 added lines of f).
    cf = ChangedFile("m.py", "A", None, ONE, added=[(1, 2)], removed=[])
    s = score_change([cf])
    assert s.mutation == 0
    assert s.godclass == 2
    assert s.files_changed == 1
    assert s.impact == 2


def test_before_vs_after_context_on_new_file():
    # Three new functions in a new file. This is the import case.
    cf = ChangedFile("m.py", "A", None, THREE, added=[(1, 8)], removed=[])
    # before: each new func has no prior siblings -> WMC 1 -> cost 1*1*2 = 2; total 6.
    assert score_change([cf], wmc_context="before").impact == 6
    # after: each func sees the other two as siblings -> WMC 3-1 = 2 -> cost 4; total 12.
    assert score_change([cf], wmc_context="after").impact == 12


def test_accretion_charged_for_prior_siblings():
    # Append a new function to a file that already has f, g, h (total CC 3).
    after = THREE + b"\ndef nu():\n    return 4\n"       # nu: lines 10-11
    cf = ChangedFile("m.py", "M", THREE, after, added=[(10, 2)], removed=[])
    s = score_change([cf])
    # nu is new, but its container already held CC 3 -> WMC_other = 3.
    # cost = 3 * 1 * 2 = 6.  (Contrast: the same nu as its own new file costs 2.)
    assert s.mutation == 0
    assert s.godclass == 6
    assert s.impact == 6

    isolated = ChangedFile("nu.py", "A", None, b"def nu():\n    return 4\n",
                           added=[(1, 2)], removed=[])
    assert score_change([isolated]).impact == 2      # 3x cheaper than accretion


def test_modify_existing_function_is_mutation():
    before = b"def f():\n    return 1\n\ndef g():\n    return 2\n"   # f 1-2, g 4-5
    after = b"def f():\n    return 99\n\ndef g():\n    return 2\n"   # line 2 changed
    cf = ChangedFile("m.py", "M", before, after, added=[(2, 1)], removed=[(2, 1)])
    s = score_change([cf])
    # f is modified. WMC_other = (f+g = 2) - f.cc(1) = 1. dlines = 1 added + 1 removed = 2.
    # cost = 1 * 1 * 2 = 2, counted as mutation.
    assert s.godclass == 0
    assert s.mutation == 2
    assert s.impact == 2


def test_non_source_file_is_ignored():
    cf = ChangedFile("README.md", "M", b"# a\n", b"# a\n\nmore\n",
                     added=[(2, 2)], removed=[])
    s = score_change([cf])
    assert s.empty
    assert s.impact == 0
