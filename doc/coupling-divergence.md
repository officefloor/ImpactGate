# Coupling Divergence

Coupling Divergence is a placement measure that flags the one method or class that
*manufactures* coupling, the orchestrator that everything flows out of, rather than code
that is merely large or complex. It scores where information flow is created and
concentrated in the code itself.

## Two flows, and one that is not conserved

A program has two graphs, not one. There is the control flow, which method calls which.
And there is the information flow, the data carried along those calls. The parameters
passed on a call are the information going along that control edge. The more information
rides an edge, the stronger the sinew tying control to data at that point. A call that
passes five arguments is a far heavier sinew than a call that passes one.

Think of it as fluid in pipes. The calls are the pipes, the arguments are the fluid. In a
real pipe network the fluid is conserved. What enters a junction leaves it, divided among
the downstream pipes. The total flowing through is constant.

An information system does not obey that conservation. A method can create flow that was
never handed to it. It constructs new objects, derives new values, and spawns new
parameterised calls of its own. The information leaving it can exceed the information that
arrived. When that happens the method is a source. It is adding what was not there before,
creating in the way creation means. That is the behaviour this measure is built to find.

## Divergence: the net creation at a point

The word comes from vector calculus, and it fits exactly. The divergence of a flow field
is the net outflow from a point, its source strength. In a conservative flow, an
incompressible fluid, divergence is zero everywhere. A positive divergence marks a source,
a place where the field is created.

For each method `v`, count the information over its edges, counting only calls to **our own
code** (a callee defined somewhere in the tree). Calls leaving into a library or the
database are flow leaving the system, so they do not count.

```
out(v) = Σ over v's internal call sites of (number of arguments passed)   # flow it sends on
in(v)  = Σ of arguments passed INTO v by its callers                      # flow it receives
δ(v)   = out(v) − in(v)                                                    # coupling divergence
```

A method with `δ(v) ≤ 0` splits or absorbs flow. It is a pipe junction, a sink, a mapper
that gathers many values into one object, or a leaf that computes and returns. A method
with `δ(v) > 0` manufactures flow. It is a source. Coupling Divergence is that `δ`.

## Placement, not amount

This is a placement measure, the same stance as Change Impact. The claim is not that a
system carries too much coupling. Totals are roughly conserved, which is Tesler's law of
complexity. The claim is about where the coupling concentrates.

If divergence were spread evenly across methods, no single one would stand out and there
would be no god. A god is a spike. One method whose divergence towers over all the others.
That spike is the place of creation, and it is where every purpose routed through the
system piles on. So the measure does not ask how much flow exists. It asks whether the
creation of flow is even or spiked, and it flags the spike.

## Detecting the god method and god class

A god is a divergence outlier, not a value past a fixed line. The test is the
Iglewicz-Hoaglin modified z-score, the textbook robust outlier test, taken over the
methods that actually create flow (`δ > 0`):

```
z(v) = 0.6745 · (δ(v) − median(δ)) / MAD(δ)          MAD = median absolute deviation

god method   ⟺   z(v) ≥ 3.5
```

For a god class, cumulate divergence over the class's own methods and take the outlier
over classes:

```
Δ(C) = Σ over methods v in class C of δ(v)

god class    ⟺   modified-z of Δ(C) over all classes ≥ 3.5
```

The sum is deliberate. A god class accretes manufactured flow across several methods, and
`WMC`, the size reference it is judged against, is also a per-class sum, so the two are
matched. The cutoff of 3.5 is the standard modified-z line, not a tuned domain constant.
The distribution supplies the scale, so the test is threshold-free and relative. The
internal-only rule is what excludes the converter and the row mapper with no type analysis
at all. They push their columns onto a SQL call that leaves the system, so their `out` is
near zero and their divergence is not positive.

## How it is used

- **Detection (a snapshot).** Run it on a tree and flag the divergence outliers. No history
  is needed, because a spike is visible the instant the method exists.
- **Per change (in ImpactGate).** Flag the added or mutated methods that are divergence
  outliers in the resulting tree. See `impact_gate/placement_check.py`.
- **Live monitor.** Re-run it per commit. A unit crossing into outlier status is a vortex
  forming under the current edits, which is the signal to watch in an AI-augmented pipeline.

## Running it

Coupling Divergence runs on every `impact-gate score` and is **on by default in warn**: when
the change adds or mutates a method that is a generation outlier in the resulting tree, it is
reported beside the score as a second signal, and never fails the build until you ask it to.

```yaml
# .impact-gate.yml
coupling_enforcement: block   # fail the build when a change touches a coupling vortex
```

Switch it off for a run with `--coupling off`, or block on it with `--coupling block`. It is
designed as a signal to look, not a number to blend into the impact score; see
[coverage.md](./coverage.md) for how it complements the other two measures and what it does
and does not catch.

## What is established, and what is not

Detection is validated. Across 25 open source repositories in 11 languages, the class
divergence outlier is 1.5 to 6.6 times more likely to sit in a textbook god class
(`WMC ≥ 47`) than chance, mostly 3 to 6 times. Against the full Lanza-Marinescu God Class
detector on Java (PMD's `GodClass`) it runs 2.9 to 3.8 times, and it excludes about three
quarters of the self-contained complex algorithms that `WMC` alone misfires on, making the
same "coupled, not merely complex" distinction the textbook needs its ATFD and TCC terms to
make.

It is complementary, not total. Divergence catches the out-flow orchestrator gods, with
recall between 0.3 and 0.9. It does not catch the gods that reach into foreign data without
pushing much out (the ATFD axis), so it is a second lens, not a replacement for the textbook
detector.

Predicting a god strictly *before* it crosses the textbook threshold is a separate and
harder claim, and it is **not** established on organic history. Measured fairly, with rename
following and restricted to gods that form within view, the divergence outlier coincides
with or lags the size threshold more often than it leads. The lead appears only in
concentrated single-locus accretion, which is the regime an AI pipeline creates, so it
remains an open hypothesis to study there, not a shipped capability. Detection and live
monitoring are what Coupling Divergence claims.

## Novelty and relation to prior work

The name and the formulation appear to be novel. The ingredients are not, and the honest
contribution is the synthesis.

- **Henry & Kafura (1981), information flow complexity**, `length · (fan-in · fan-out)²`, is
  the classic fan-in/fan-out measure. It is a symmetric product, so it cannot see a source.
  A method with fan-in 0, such as a handler the framework calls, scores zero. Coupling
  Divergence is a directional difference built precisely to find that source.
- **Lanza & Marinescu God Class** is a conjunction of thresholded metrics
  (`WMC ≥ 47 and ATFD > 5 and TCC < 1/3`). Its cohesion term is defeated by dependency
  injection, where a shared injected service inflates TCC and a 160-WMC handler never
  trips. Coupling Divergence is a single mechanistic quantity, threshold-free, and immune to
  that blind spot.
- **Vaucher et al. (2009)** track a class's "godliness" over versions, a symptom trajectory.
  Divergence measures the mechanism on a single snapshot.
- **Program dependence graphs** (Ferrante et al.) combine control and data dependence, and
  some representations merge them into a composite edge, which is close to the sinew idea,
  but they are program-analysis representations, not a placement metric.

No prior measure defines a god by net flow divergence, by creation. That is the new idea
here.
