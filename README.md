# impact-gate

A merge gate that flags changes piling complexity onto code that is already complex,
before a class quietly grows into a god-class nobody can safely touch. Run it as a
standalone CLI, a git pre-commit hook, or a plugin in GitHub, GitLab, and Jenkins CI.

Website: https://impactgate.officefloor.net

The pattern it catches is gradual. A class gains one more method, then another, then
another. Each change looks reasonable on its own. But over dozens of them the class ends
up doing five different jobs, and every edit gets riskier. That slow accretion is what we
call structural decay. The gate scores each change against a base (`main` by default), so
it shows up while it is still cheap to fix:

```
impact = files_changed * Σ max(WMC_other, 1) * CC * Δlines      (over changed functions)
```

`WMC_other` is the complexity that was already in the file or class you are editing,
measured before your change. Adding a brand-new file is cheap. There was nothing there to
make worse. Adding a complex method to an already-heavy class is expensive. The gate
measures that difference, not the raw size of the diff.

For the reasoning behind the formula, see [Measuring the Blast Radius of
Change](https://blog.officefloor.net/2026/08/measuring-blast-radius-of-change.html) on
the OfficeFloor blog.

When impact is too high, the gate asks you to simplify the change or refactor the code
it touches. It can warn (report only) or block (fail the build).

## Install

```bash
pip install impact-gate         # installs the `impact-gate` command
```

Or run it without installing anything, via the published image (git is bundled;
mount the repo to score at `/repo`):

```bash
docker run --rm -v "$PWD:/repo" ghcr.io/officefloor/impact-gate \
  score --mode range --base origin/main
```

To hack on it locally, install from a checkout instead:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'         # editable install plus the test deps
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

A source file whose diff is larger than `max_diff_lines` (200,000 by default, in the
measure config) is almost always a generated dump or a vendored blob. The gate skips it
so it neither distorts the number nor slows scoring, and lists it under **skipped** so
the result is never silently wrong.

## Use as a git pre-commit hook

Gate every commit locally, before CI:

```bash
# Installs .git/hooks/pre-commit. It scores the staged change on each commit.
impact-gate install-hook
```

With `enforcement: block` in `.impact-gate.yml`, a commit whose impact is too high is
blocked; on `warn` (or off) the report prints and the commit proceeds. Re-run with
`--force` to overwrite an existing pre-commit hook.

Prefer the [pre-commit](https://pre-commit.com) framework? This repo ships a hook
definition — add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/officefloor/ImpactGate
    rev: v0.3.0
    hooks:
      - id: impact-gate
```

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
      - uses: officefloor/ImpactGate@v0
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

## Use in GitLab CI

A ready-made job is in [`ci/gitlab-ci.yml`](ci/gitlab-ci.yml). Copy it into your
`.gitlab-ci.yml`, or include it remotely:

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/officefloor/ImpactGate/v0/ci/gitlab-ci.yml'
```

It runs on merge-request pipelines, scores the MR against its base
(`$CI_MERGE_REQUEST_DIFF_BASE_SHA`) with the published Docker image, and — when a CI/CD
variable `GITLAB_TOKEN` with the `api` scope is set — posts a sticky note to the MR (one
note, updated each run). Without the token it still scores and gates; it just skips the
note. In `block` enforcement the job fails when impact is too high; make it required in
the merge request settings to gate merges.

## Use in Jenkins

A pipeline snippet is in [`ci/Jenkinsfile`](ci/Jenkinsfile). It runs the Docker image on
an agent with Docker, scoring the change against its target branch
(`origin/${CHANGE_TARGET:-main}`) and archiving the report. In `block` enforcement the
stage fails when impact is too high. Posting the score back to the PR/MR is left to your
SCM integration; to post it with the tool itself, run `impact-gate comment` in the
container with the provider's token and env set.
