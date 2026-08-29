# impact-gate

Measure and gate the structural decay a change introduces. Run it as a standalone CLI,
a git pre-commit hook, or a plugin in GitHub, GitLab, and Jenkins CI.

Structural decay is complexity accreting into existing structures. A god-method grows
another branch. A god-class gains another method. The gate scores a change against a
base (`main` by default) with the change-impact measure:

```
impact = files_changed * Σ max(WMC_other, 1) * CC * Δlines      (over changed functions)
```

`WMC_other` is the complexity already in the container you are editing. It is measured
on the pre-change state. So importing a brand-new file or class is cheap. Nothing was
there before. Piling onto an already-heavy class is expensive. That is the decay signal.

When impact is too high, the gate asks you to simplify the change or refactor the code
it touches. It can warn (report only) or block (fail the build).

This tool is the instrument for an experiment. The experiment studies how to control
structural decay under AI-augmented development. The gate sits in front of every change,
human or AI, so complexity cannot silently concentrate.

> Fully standalone. The measure is vendored in `impact_gate/core/`. Only `lizard` is
> required at runtime.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .                # installs the `impact-gate` command
```

## Use

```bash
# The commit you are about to make (pre-commit): staged vs HEAD. This is the default.
impact-gate score

# Uncommitted local edits: working tree vs HEAD.
impact-gate score --mode worktree

# CI or PR review: the committed branch vs main (merge-base..HEAD).
impact-gate score --mode range --base origin/main --format json

# Set thresholds and enforcement. You can also put these in .impact-gate.yml.
impact-gate score --warn-at 50000 --block-at 200000 --enforcement block
```

Exit codes. `0` means ok or warn (the change is allowed). `2` means blocked (impact too
high under `--enforcement block`). `1` means a usage or environment error.

Every report also lists the **files to consider for refactoring**, ranked by their share
of the impact. The change-level number gates; the per-file ranking points at where the
decay is concentrating, so a file quietly growing into a god-class surfaces as a
candidate before it blocks anything.

## Grade against a distribution (the curve)

A raw threshold is hard to set: a typical change's impact varies by orders of magnitude
across languages and projects. Instead of guessing a number, grade a change by its
**percentile** against a distribution, and gate on the percentile.

```bash
# Build (or refresh) the project's own impact distribution from the merged history.
# Writes .impact-gate-baseline.json. Re-run it as the branch moves.
impact-gate baseline --base-ref main

# Gate on the grade instead of an absolute number.
impact-gate score --curve --warn-percentile 90 --block-percentile 98
```

The grade blends two distributions:

- a **seed prior** shipped with the tool — per-language percentile tables built from a
  20-repo open-source corpus, with a pooled fallback for languages not in the table;
- the **project baseline** — the repo's own per-change distribution, walked from the
  merged mainline (only landed work; in-flight branches are never reached).

The blend weights the project by `w = n / (n + K)`, where `n` is the number of landed
changes behind the baseline and `K` (`curve_prior_weight`, default 200) is how much
history it takes to trust the project over the seed. A fresh repo with no baseline file
grades on the seed alone; a deep history leans on itself. The grade shows in every
format next to the raw number.

## Configure with `.impact-gate.yml` (repo root)

```yaml
warn_at: 50000          # impact above which to warn
block_at: 200000        # impact above which to block
enforcement: warn       # off, warn, or block. Start on warn. Flip to block when ready.
tolerance: 1.0          # CI-adjustable multiplier on both thresholds. Above 1 is more lenient.
# measure_config: .impact-measure.yml   # optional: ignore globs and language overrides

# Grading curve (percentile gate). When enabled, warn_at/block_at are ignored and the
# gate uses the percentiles below instead.
curve_enabled: false           # gate on the percentile grade instead of absolute numbers
warn_percentile: 90            # grade at or above this warns
block_percentile: 98           # grade at or above this blocks
curve_prior_weight: 200        # K in w = n/(n+K): history needed to trust the project over the seed
baseline_file: .impact-gate-baseline.json   # where `impact-gate baseline` caches the distribution
```

CLI flags override the file. A CI job can pass `--tolerance` or `--warn-at`. So a team
can dial tolerance without editing the repo. The curve knobs have flags too: `--curve`,
`--warn-percentile`, `--block-percentile`, `--baseline-file`.

## Use in GitHub Actions

Add a workflow to your repo. The action scores the PR branch against its base and writes
a summary. `fetch-depth: 0` is required so the base branch and merge-base are present.

```yaml
name: Change impact
on: pull_request
permissions:
  contents: read
  pull-requests: write         # so the action can post the score as a PR comment
jobs:
  impact:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: officefloor/ImpactGate@v1
        with:
          enforcement: warn        # switch to block when ready
          # warn-at: 50000
          # block-at: 200000
          # tolerance: 1.0
```

The score appears in the job summary and as a sticky comment on the PR (one comment,
updated each run). In `block` mode the job fails when impact exceeds the block threshold.
Make the check required in branch protection to gate merges. The comment needs
`pull-requests: write`. Without it the run still passes and just skips the comment.

## Roadmap

- Core CLI. Score staged, worktree, or range. Warn or block. Text, JSON, markdown. Done.
- GitHub Action. Composite action, job-summary report, and a sticky PR comment. Done.
- Baseline and grading curve. `impact-gate baseline` profiles the project history; the
  gate blends a seed-corpus prior with the project's own distribution and grades a change
  by its percentile (`score --curve`). Done.
- Distribution. A Dockerfile so it runs on any CI with Docker. A `pip` package.
- More CI plugins. A GitLab CI template and a Jenkins shared library.
- Hooks and IDE. An `impact-gate install-hook` for pre-commit. Editor integration over LSP.
