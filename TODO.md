# impact-gate TODO

Remaining work, roughly in priority order. Short notes, not tickets.

## Done so far

- Core CLI. `impact-gate score` for staged, worktree, and range modes. Warn and block enforcement with exit codes. Text, JSON, and markdown output.
- Standalone. The measure is vendored in `impact_gate/core/` (before-context WMC). No dependency on Surveyor. Only `lizard` is required at runtime.
- GitHub Action. Composite action, job-summary report, and a sticky PR comment. Tests workflow across Python 3.10 to 3.13.
- Ignore fix. Top-level `vendor/`, `node_modules/`, and generated dirs are now excluded at any depth. Test added.
- Tests. 52 passing.

## Next up: grading curve

The design is set. Grade a change by its percentile against a distribution. Seed with the corpus, blend toward the project's own history.

- [x] Regenerate the clean corpus first. DONE. Before-context scan of 20 OSS repos landed in `~/scan` (2026-08-29), corrected ignores. 349,165 non-merge per-commit observations.
- [x] Seed prior. DONE. `impact_gate/data/seed_percentiles.json` now carries real clean-corpus composite percentiles: pooled + 8 well-sampled languages (python, java, typescript, csharp, javascript, c, scala, go, all n>=2000). Under-sampled languages (ruby/rust/cpp/kotlin/... n<2000) are dropped so they fall back to pooled. `_meta.provisional` is now false. Loader validates the shape on load. Real numbers are ~1000x the old placeholders and heavy-tailed; see notes below.
- [x] `baseline.py`. DONE. Walks the merged mainline of the base branch into the project's per-observation distribution. Unit = one atomic landed change: main non-merge commits, leaf MRs (net branch-start..tip), and a parent MR's direct commits netted per run between merges (child MRs recurse, syncs skipped); merges are never scored, so roll-ups can't inflate. Percentile rank + empirical-Bayes blend `w = n/(n+K)`. Persistence (save/load). Policy knobs in `data/defaults.json` (`base_ref`, `exclude_subject_pattern`, `max_commits`). 6 tests over a temp-repo DAG.
- [x] `impact-gate baseline` command. DONE. Walks the merged mainline and caches the distribution to `baseline_file` (default `.impact-gate-baseline.json`), wired to `baseline.build_baseline` + `save_baseline`. Flags: `--base-ref`, `--max-commits`, `--exclude-subject-pattern`, `--baseline-file`, `--measure-config`. Fails cleanly (exit 1, no traceback) on empty/absent history.
- [x] Config knobs. `warn_percentile` (90), `block_percentile` (98), `curve_prior_weight` (K=200), `baseline_file`, and `curve_enabled` (percentile vs absolute) — all in `GateConfig`, defaulted from `data/defaults.json`, overridable via `.impact-gate.yml`, validated. `score` CLI flags: `--curve`, `--warn-percentile`, `--block-percentile`, `--baseline-file`.
- [x] Report the grade. DONE. The percentile grade shows in text (a `grade:` line with the curve thresholds and blend weight), markdown (a `grade` row), and JSON (a `grade` object + `curve` flag), alongside the raw composite number.
- [x] Gate on percentile when the curve is enabled. DONE. `score --curve` loads the baseline, grades via `grade_change`, and gates on `level_for_grade`/`blocks_grade`. Absolute thresholds remain the default when the curve is off. Cold start (no baseline file) grades on the seed alone.
- [x] Metric decided: two outputs, not a choice. Composite (change-level) is the only gated metric — it catches erosion early. Per-file cost (mutation + godclass, i.e. composite without the files multiplier) is a ranking signal only: sum cost per changed file, order descending, surface as "files to consider for refactoring". The old `metric: composite | mutation` knob and the mutation-only baseline distribution are removed; report now shows the ranked file list (text/markdown/JSON) instead of a mutation-only headline. Seed remains composite-only. Note: additions count toward per-file cost, so a file growing into a god class via new functions ranks as a refactor candidate.
- [x] Tests. DONE: loader schema validation, seed-table pooled fallback, percentile-rank math (seed table and project), config-knob defaults/override/validation, the blend (cold start uses seed, warm blends by n/(n+K)), and the baseline walk over a temp-repo DAG (atomic-change counting, subject exclusion, persistence).

## Distribution

- [x] Dockerfile. DONE. `python:3.12-slim` + git (needed to read diffs) + the pip
  install; runs unprivileged, repo mounted at `/repo`, `impact-gate` as entrypoint.
  `.dockerignore` keeps the context lean; built image is ~256MB. Published to
  `ghcr.io/officefloor/impact-gate` by the release workflow.
- [x] Publish to PyPI. DONE (automation). `pyproject.toml` carries full metadata
  (SPDX license, authors, URLs, classifiers, keywords) with the version single-sourced
  from `impact_gate.__version__`. `twine check` passes. The `release.yml` workflow
  publishes via PyPI trusted publishing (OIDC, no token). One-time publisher setup and
  the release steps are in `RELEASING.md`; the first `pip install impact-gate` works
  once a `vX.Y.Z` tag is pushed.
- [x] Version tags. DONE (automation). Push `vMAJOR.MINOR.PATCH`; the release workflow
  moves the floating major tag (`v0`, `v1`, ...) so the Action pins as
  `officefloor/ImpactGate@v0`. Cut `v0` by pushing `v0.1.0` (see `RELEASING.md`).
- [ ] GitHub Marketplace. `action.yml` is Marketplace-ready (unique `name`, valid
  `branding` icon/color). Publishing is a manual GitHub Release UI step — see the
  Marketplace section of `RELEASING.md`. Do once the action is stable; verify the
  `impact-gate` name is still free first (names are global).

## More CI integrations

- [ ] GitLab CI template. A job using `image:` with the Docker image, scoring `merge-base..HEAD`, posting the score to the MR.
- [ ] Jenkins. A shared-library step or a `docker.inside` snippet.
- [ ] Others as needed. Bitbucket Pipelines, CircleCI, Azure DevOps.

## Hooks and IDE

- [ ] `impact-gate install-hook`. Install a git pre-commit hook that runs staged mode and blocks or warns.
- [ ] `.pre-commit-hooks.yaml` so the tool works with the `pre-commit` framework.
- [ ] IDE integration. Editor feedback over LSP or a plugin. Live gauge as the developer edits.

## Reporting enhancements

- [ ] GitHub Checks annotations. Optionally annotate the specific units driving the impact, inline on the diff.
- [ ] Trend. Show how the score compares to the project's recent commits, once the baseline exists.

## Robustness

- [ ] Bulk-commit guard. `max_diff_lines` exists in the measure config but the gate does not surface or enforce it. Decide how a pathological commit is handled and messaged.
- [ ] Large-diff performance. Confirm scoring stays fast on very large PRs.

## Release and housekeeping

- [ ] Commit the current work. Ignore fix, PR comment, tests, and this file.
- [ ] Docstring and comment style. Remove remaining em dashes from code comments to match the docs style.
- [ ] Keep the README current as features land.

## Notes and decisions

- Measure is single-sourced by vendoring, since Surveyor is a concluded experiment and is not co-developed. If the formula ever changes, re-vendor `impact_gate/core/`.
- Canonical measure is before-context WMC. The measure is hard-wired to before-context; the legacy `after` path and its `--wmc-context` flag have been removed.
- Grading is percentile based because per-commit impact varies by about 300x across projects and 60x across languages. A single absolute threshold cannot work.
- The tool gates change-effort and structural decay, not defect probability. The corpus study found the measure does not beat file size as a defect predictor. Do not market it as one.
- Storage/config are behind two ports in `providers.py` (`GradeProvider`, `PolicyProvider`), ports-and-adapters style. The gate depends only on the ports; local file/`.impact-gate.yml` adapters implement them today, and a hosted store + config service can swap in without touching the CLI or CI plugins. Contract: `grade()` returns None when a backend is unreachable and the caller falls back to the shipped seed; the verdict (exit code) is always computed caller-side from the policy, never by a provider. `select_*_provider` is the single place adapter choice lives. `RemoteGradeProvider`/`RemotePolicyProvider` are documented stubs of the API contract. The port sends only a `ChangeSummary` (composite value + language), never the diff, so a remote never receives source. This is the seam for the planned hosted/UX tier and dataset lock-in; keep local mode fully functional as the OSS wedge and never make the remote a single point of failure in the merge path.
- Next for the hosted store: add incremental append (`POST /observations`, delta walk from the stored `_meta.head`) so the baseline stays live without re-walking; add a baseline head/version field to `Grade` for provenance; add remote selection (a `baseline_source` URL/env) in `select_*_provider`.
