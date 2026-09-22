"""Cognitive Complexity (Campbell 2018): the estimator, the plugin field, the gate, output.

The estimator is ImpactGate's own; these assertions are the calibration. The Java values match
PMD's CognitiveComplexity rule on the same snippets (hand-verified), which is what lets the
metric be trusted as a gate without shipping PMD.
"""
import json

from gitutil import commit, score, stage, write

from impact_gate import report
from impact_gate.config import GateConfig
from impact_gate.core.cognitive import cognitive_complexity as cc
from impact_gate.core.units import get_plugin


# --- the estimator ------------------------------------------------------------

def test_flat_sequential_costs_nothing():
    # The whole point: long, flat, sequential code is easy to read -> 0.
    assert cc("void f(){ a(); b(); c(); int x=1; x=x+1; log(x); d(); e(); }", "java") == 0


def test_nesting_matches_pmd_java():
    # if>if>if>if>while>if : 1+2+3+4+5+6 = 21 (== PMD CognitiveComplexity on this snippet).
    src = "void f(){ if(a){ if(b){ if(c){ if(d){ while(e){ if(g){ h(); } } } } } } }"
    assert cc(src, "java") == 21


def test_boolean_operator_runs():
    assert cc("boolean f(){ return a && b && c; }", "java") == 1     # one run of &&
    assert cc("boolean f(){ return a && b || c && d; }", "java") == 3  # && , || , &&


def test_else_if_is_flat_increment():
    # if (+1) + else-if (+1) + else (+1) = 3; the else chain adds no nesting.
    assert cc("void f(){ if(a){x();} else if(b){y();} else {z();} }", "java") == 3


def test_switch_counts_once_not_per_case():
    assert cc('String w(int n){ switch(n){ case 1: return "a"; default: return "b"; } }',
              "java") == 1


def test_python_indentation_model():
    src = ("def f(x):\n"
           "    if x:\n"
           "        for i in y:\n"
           "            if i and j:\n"
           "                do(i)\n"
           "    elif z:\n"
           "        pass\n")
    # if(1) + for(2) + if(3) + and(1) + elif(1) = 8
    assert cc(src, "py") == 8


def test_strings_and_comments_do_not_count():
    src = 'void f(){ String s = "if(a){for(;;){}}"; /* if while for */ log(s); }'
    assert cc(src, "java") == 0


def test_ternary_counts():
    assert cc("int f(){ return a ? b : c; }", "java") == 1
    # ternary inside a loop is charged the nesting depth too: for(1) + ternary(1+1) = 3
    assert cc("void f(){ for(x : xs){ y = a == null ? 1 : 2; } }", "java") == 3


def test_ts_optional_syntax_is_not_a_ternary():
    # These all contain '?' but are NOT ternaries; they must not count.
    assert cc("function f(){ return a?.b?.c; }", "ts") == 0          # optional chaining
    assert cc("function f(x?: number){ return x; }", "ts") == 0      # optional parameter
    assert cc("function f(){ return a ?? b; }", "ts") == 0           # nullish coalescing


def test_lambda_body_adds_nesting():
    # A control structure inside a lambda/callback is charged for its depth (Java -> and JS =>).
    assert cc("void f(){ xs.forEach(x -> { if(a){ y(); } }); }", "java") == 2
    assert cc("function f(){ xs.forEach(x => { if(a){ y(); } }); }", "ts") == 2
    # An expression lambda with no block and no control flow costs nothing.
    assert cc("const f = () => xs.map(x => x.id);", "ts") == 0


# --- the plugin field ---------------------------------------------------------

def test_plugin_sets_unit_cognitive():
    src = b"class D { void f(boolean a,boolean b,boolean c){ if(a){ if(b){ if(c){ x(); } } } } }"
    units = get_plugin("java").parse(src, "D.java")
    f = next(u for u in units if u.name.endswith("f"))
    assert f.cognitive == 6            # 1 + 2 + 3
    assert f.cc >= 1                    # existing metric still populated


# --- score_change carries it --------------------------------------------------

_NESTED4 = ("class D { void f(boolean a,boolean b,boolean c,boolean d){ "
            "if(a){ if(b){ if(c){ if(d){ x(); } } } } } }")   # cognitive 1+2+3+4 = 10


def test_score_change_reports_cognitive(repo):
    write(repo, "base.txt", "x")
    commit(repo, "init")
    stage(repo, "D.java", _NESTED4)
    s = score(repo, "worktree")
    assert s.cognitive_max == 10
    assert any(u.cognitive == 10 for u in s.cognitive_units)


def test_cognitive_scoped_to_changed_methods_only(repo):
    # A file with an already-complex, ACCEPTED method `old` (cognitive 15) plus a trivial one.
    v1 = ("class D {\n"
          "  void old(boolean a,boolean b,boolean c,boolean d,boolean e){\n"
          "    if(a){ if(b){ if(c){ if(d){ while(e){ x(); } } } } }\n"
          "  }\n"
          "  void small(){ y(); }\n"
          "}\n")
    write(repo, "D.java", v1)
    commit(repo, "v1")
    # Edit ONLY `small`; leave the complex `old` untouched.
    v2 = v1.replace("void small(){ y(); }", "void small(){ y(); z(); w(); }")
    stage(repo, "D.java", v2)
    s = score(repo, "worktree")
    names = [u.name for u in s.cognitive_units]
    assert not any("old" in n for n in names)   # untouched accepted complexity is NOT re-flagged
    assert s.cognitive_max < 15                  # the god-method's 15 does not surface


# --- the gate -----------------------------------------------------------------

def test_gate_off_by_default():
    assert GateConfig().cognitive_enabled() is False


def test_gate_blocks_strictly_over_threshold():
    cfg = GateConfig(enforcement="block", cognitive_max=8)
    assert cfg.cognitive_enabled()
    assert cfg.cognitive_level(10) == "block"
    assert cfg.cognitive_level(8) == "ok"          # strictly greater blocks
    assert cfg.blocks_cognitive(10) is True
    assert cfg.blocks_cognitive(8) is False


def test_gate_warn_mode_does_not_fail():
    cfg = GateConfig(enforcement="warn", cognitive_max=5)
    assert cfg.blocks_cognitive(99) is False       # only 'block' enforcement fails the gate


def test_validate_rejects_nonpositive():
    import pytest
    with pytest.raises(ValueError):
        GateConfig(cognitive_max=0).validate()


# --- output -------------------------------------------------------------------

def test_json_output_has_cognitive_section(repo):
    write(repo, "base.txt", "x")
    commit(repo, "init")
    stage(repo, "D.java", _NESTED4)
    s = score(repo, "worktree")
    cfg = GateConfig(enforcement="block", cognitive_max=5)
    out = json.loads(report.render_json(s, cfg, "block", "worktree", "main", True))
    assert out["cognitive"]["max"] == 10
    assert out["cognitive"]["threshold"] == 5
    assert out["cognitive"]["blocked"] is True
    assert out["cognitive"]["offenders"]


def test_json_omits_cognitive_when_off(repo):
    write(repo, "base.txt", "x")
    commit(repo, "init")
    stage(repo, "D.java", _NESTED4)
    s = score(repo, "worktree")
    out = json.loads(report.render_json(s, GateConfig(), "ok", "worktree", "main", False))
    assert "cognitive" not in out
