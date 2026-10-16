# Cognitive Complexity

Cognitive Complexity flags a single method that has become too hard to read: deeply nested,
with many interacting branches, the kind of method a reviewer has to hold their breath to
follow. It is an absolute per-method readability limit, measured on the methods a change
touches.

## What it measures

Cognitive Complexity is G. Ann Campbell's 2018 refinement of cyclomatic complexity
(SonarSource). Cyclomatic complexity counts the number of linearly independent paths through
a method, which treats a flat `switch` with twenty cases the same as four nested `if`s inside
a loop. For a human reading the code those are not equal: nesting is what makes code hard to
follow, not the raw number of branches.

Cognitive Complexity scores the *effort to understand* a method rather than the number of its
paths:

- Each break in the linear flow (`if`, `for`, `while`, `catch`, a boolean operator sequence,
  a ternary) adds **one**.
- Each level of **nesting** adds an increasing penalty: a branch two levels deep costs more
  than the same branch at the top. Nesting is the term that dominates.
- Structures that do not add to the reading burden do not count. A flat `switch` counts once,
  not once per case; sequential statements are free; shorthand that reads naturally is not
  penalised.

The result is a number that tracks how hard the method is to hold in your head. A long but
flat method scores low. A short method with three loops nested inside two conditionals scores
high. ImpactGate computes it per function in `impact_gate/core/cognitive.py`.

## How ImpactGate applies it

The gate is **absolute** and **per method**: any single method whose Cognitive Complexity
exceeds the limit is flagged. This is independent of the change-impact score, which is a
whole-change composite; one deeply-nested method can trip the cognitive gate even when the
change's impact is small.

It is scoped to the change, not the whole file. For a new file, every method in it is
checked. For a modified file, only the functions whose lines the change added or edited are
checked, read from the after-version (the working tree). A pre-existing, untouched method
that was already complex is never re-flagged by a change that did not touch it. So the gate
asks one question: *did this change leave behind a method that is too hard to read?*

The default limit is **20**. SonarSource's standard line is 15; the gate is set a touch more
permissive so it flags only genuinely hard-to-read methods out of the box. When a method is
over the limit, the report names it and asks you to break it into smaller methods, reducing
nesting and decision depth (sequential code is fine).

## Running it

Cognitive Complexity runs on every `impact-gate score` and is **on by default in warn**: it
reports over-limit methods and never fails the build until you ask it to.

```yaml
# .impact-gate.yml
cognitive_max: 15             # tighten the limit (null = switch the gate off)
cognitive_enforcement: block  # fail the build on an over-limit method
```

On the command line, `--cognitive-max N` sets the limit, `--cognitive block` makes it fail
the build, and `--cognitive off` disables it for that run. For how the cognitive gate sits
alongside the change-impact and coupling-divergence measures, see [coverage.md](./coverage.md).
