# Change Impact

Change Impact scores the marginal cost of a change, weighted by what the change lands on, so
a class growing into a god class surfaces while it is still cheap to fix. It is the measure
ImpactGate's gate is built on.

## The pattern it catches

The decay is gradual. A class gains one more method, then another, then another. Each change
looks reasonable on its own. But over dozens of them the class ends up doing five different
jobs, and every edit gets riskier. That slow accretion is structural decay, also called
cohesive erosion. The gate scores each change against a base (`main` by default), so the
decay shows up while it is still cheap to fix.

## The formula

```
impact = files_changed · Σ max(WMC_other, 1) · CC · Δlines      (over changed functions)
```

`WMC_other` is the complexity that was already in the file or class you are editing, measured
before your change. Adding a brand new file is cheap. There was nothing there to make worse.
Adding a complex method to an already heavy class is expensive. The gate measures that
difference, not the raw size of the diff. `CC` is the cyclomatic complexity of the changed
function, `Δlines` the lines the change added or edited in it, and `files_changed` the spread
of the change across files.

For the reasoning behind the formula, see
[Measuring the Blast Radius of Change](https://blog.officefloor.net/2026/08/measuring-blast-radius-of-change.html)
on the OfficeFloor blog. For the design philosophy, why ImpactGate scores placement and
deliberately leaves duplication to review, see [REASONING.md](../REASONING.md).

## How this differs from SonarQube and other static analysis

SonarQube and linters score the state of the code. This file is too complex, this method too
long, this block duplicated.

Change Impact scores the marginal cost of a change, weighted by what it lands on. The
`WMC_other` term is the complexity already in the class before you touched it. A complex
method in a brand new file is cheap. The same method added to a class already carrying five
responsibilities is expensive. It is the increment that turns a heavy class into a god class
nobody can safely edit.

Duplication is one of those state findings, and ImpactGate does not score it. That is
deliberate, not an omission. Whether a given copy is harmful duplication or a legitimate
separate decision is a design judgment no deterministic signal can make without noise.
[REASONING.md](../REASONING.md) explains why, and where duplication belongs instead.

## Placement, not amount

Change Impact is a placement measure. Measured four ways, the total complexity of a codebase
is roughly conserved, which is Tesler's law. What differs between a maintainable system and a
decaying one is not the total but where the complexity is placed, and whether each change
piles more onto the places that are already heavy. Change Impact scores that placement for a
change: the harm is the concentration, not the amount.

## Running it

Change Impact runs on every `impact-gate score` and is **on by default in warn**: it reports
the number and the files to look at, and never fails the build until you ask it to. It gates
in absolute mode on `warn_at` / `block_at`, or on a percentile grade in curve mode.

```yaml
# .impact-gate.yml
block_at: 50000            # impact above which a change is over the line
change_impact_enforcement: block   # fail the build on it (omit to inherit the global default)
```

Switch it off for a run with `--change-impact off` (the number is still reported, it just
stops contributing to the verdict), or block on it with `--change-impact block`. For how
Change Impact sits alongside the cognitive-complexity and coupling-divergence measures, and
why all three run together, see [coverage.md](./coverage.md).
