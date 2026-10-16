# Coverage: the three measures together

ImpactGate runs three structural measures on every change. Each is a different lens on a
different way a change can quietly make a codebase worse, and no one of them sees what the
other two see. Run together they cover the space; that is the point of running all three.

- **[Change Impact](./change-impact.md)** — the blast radius of a change. Does this change
  pile complexity onto code that is already complex?
- **[Cognitive Complexity](./cognitive-complexity.md)** — per-method readability. Does this
  change leave behind a single method too deeply nested to follow?
- **[Coupling Divergence](./coupling-divergence.md)** — the placement of coupling. Does this
  change touch the orchestrator that *manufactures* information flow, the god everything is
  routed through?

Each page stands on its own. This page is about what they catch *between* them.

## Why three, and not one

They are built on one shared conviction: in a codebase the total complexity is roughly
conserved (Tesler's law), so the harm is never the amount, it is the **concentration** —
where complexity and coupling pile up, and whether each change piles more onto the places
already carrying too much. The three measures locate three different concentrations, and
each is blind to the other two.

| Measure | Catches | Is blind to |
|---|---|---|
| Change Impact | A change that makes an already-heavy class heavier — complexity piled on complexity, weighted by what it lands on. | A small change that leaves one unreadable method; a low-complexity dispatcher that wires everything together. |
| Cognitive Complexity | A single method that is too deeply nested to read, even in a tiny change. | How the method is coupled to the rest of the system; whether the class as a whole is becoming a god. |
| Coupling Divergence | The orchestrator that manufactures outward flow even when its own cyclomatic complexity is low — the god the size signals miss. | Gods that reach into foreign data without pushing much out (the ATFD axis); it is a second lens, not a complete god detector. |

The overlaps are deliberate, and so are the gaps each one covers:

- **A low-complexity orchestrator.** A dispatcher that is cyclomatic complexity 4 but wires
  every subsystem together is cheap on Change Impact and fine on Cognitive Complexity. Only
  Coupling Divergence flags it, because it manufactures flow.
- **A self-contained complex algorithm.** A parser or a date routine that is cyclomatic
  complexity 30 but has coupling divergence 0 is essential complexity, not accidental
  coupling. Coupling Divergence correctly stays silent; Cognitive Complexity may flag it if
  it is also deeply nested, and Change Impact will weigh it on size. Three readings let you
  tell "hard because it must be" from "hard because it is badly placed".
- **A heavy class getting heavier.** A change that adds a fifth responsibility to a class
  already doing four is exactly what Change Impact is built to catch, while a single method
  in isolation might look fine to the other two.

Because they measure different things, the measures are reported as **separate signals, not
blended into one score**. Blending would average away the very distinction that makes three
lenses useful: a change can be cheap on impact, readable per method, and still route
everything through a new vortex, and you want to see that, not have it diluted.

## Running them together

All three measures run on every `impact-gate score` (CLI, the GitHub Action, and the
pre-commit hook), and all three are **on in `warn` by default**. On a fresh install nothing
fails a build or aborts a commit: the gate reports what each measure found and lets the
change through. That is deliberate — a team can adopt ImpactGate without it interrupting
anyone, see the signals on real changes first, and turn on blocking when ready.

Enforcement has three levels per measure: `off` (do not run or report it), `warn` (report
only, the default), and `block` (fail the build when it fires). The top-level `enforcement`
sets the default for all three; a per-measure setting overrides it. So you can turn blocking
on everywhere at once, or on one signal at a time, and switch any measure off.

```yaml
# .impact-gate.yml

# Default for every measure. warn (the default) reports without failing; block fails the
# build; off runs nothing.
enforcement: warn

# Thresholds the change-impact gate blocks on (when it is in block).
block_at: 50000

# The cognitive-complexity limit (default 20; null switches the gate off).
cognitive_max: 20

# Per-measure overrides. Each is off | warn | block, or omitted to inherit `enforcement`.
change_impact_enforcement: null   # inherit (warn)
cognitive_enforcement: block      # fail the build on an unreadable method...
coupling_enforcement: warn        # ...while coupling stays advisory
```

Common setups:

- **Turn blocking on for everything:** set `enforcement: block` (plus `block_at` for the
  change-impact gate to have a line to block on).
- **Block on just one measure:** leave `enforcement: warn` and set that measure's
  `*_enforcement: block`.
- **Switch a measure off:** set its `*_enforcement: off` (or `cognitive_max: null` for the
  cognitive gate).

The same choices are available per run on the command line — `--enforcement`, and
`--change-impact`, `--cognitive`, `--coupling`, each taking `off|warn|block` — and as inputs
on the GitHub Action (`enforcement`, `change-impact`, `cognitive`, `coupling`). CLI flags win
over the config file, which wins over the built-in defaults.
