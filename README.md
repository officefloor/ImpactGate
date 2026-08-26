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

## Configure with `.impact-gate.yml` (repo root)

```yaml
warn_at: 50000          # impact above which to warn
block_at: 200000        # impact above which to block
enforcement: warn       # off, warn, or block. Start on warn. Flip to block when ready.
tolerance: 1.0          # CI-adjustable multiplier on both thresholds. Above 1 is more lenient.
wmc_context: before     # measure definition. Uses the pre-change container. This is canonical.
# measure_config: .impact-measure.yml   # optional: ignore globs and language overrides
```

CLI flags override the file. A CI job can pass `--tolerance` or `--warn-at`. So a team
can dial tolerance without editing the repo.

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
- Baseline and grading curve. Profile the project history to set thresholds
  automatically. Blend a seed-corpus prior with the project's own impact distribution.
  Grade a change by its percentile. This is next.
- Distribution. A Dockerfile so it runs on any CI with Docker. A `pip` package.
- More CI plugins. A GitLab CI template and a Jenkins shared library.
- Hooks and IDE. An `impact-gate install-hook` for pre-commit. Editor integration over LSP.
