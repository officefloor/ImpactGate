"""impact-gate command line.

  impact-gate score [--mode staged|worktree|range] [--base main] ...

Exit codes: 0 = ok or warn (change allowed), 2 = blocked (impact too high, enforcement
'block'), 1 = usage/environment error. CI wrappers (GitHub/GitLab/Jenkins) call this
same command and translate the exit code + JSON into a check result / comment.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from .core.config import MeasureConfig

from . import __version__, baseline, gitio, providers, report
from .config import ENFORCEMENTS, GateConfig
from .engine import score_change


def _add_score_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=gitio.MODES, default="staged",
                   help="what to score: 'staged' (the commit you're about to make, "
                        "default), 'worktree' (uncommitted edits), or 'range' "
                        "(committed branch vs --base, for CI/PR).")
    p.add_argument("--base", default="main",
                   help="base ref for --mode range (default: main). Use e.g. "
                        "origin/main in CI.")
    p.add_argument("--repo", default=".", help="path to the git repo (default: .)")
    p.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    p.add_argument("--config", help="path to an .impact-gate.yml (else auto-discovered in --repo)")
    # threshold / enforcement overrides (win over the config file when given)
    p.add_argument("--warn-at", type=int)
    p.add_argument("--block-at", type=int)
    p.add_argument("--enforcement", choices=ENFORCEMENTS)
    p.add_argument("--tolerance", type=float)
    p.add_argument("--measure-config", help="Surveyor-style YAML for ignore globs etc.")
    # grading curve (percentile gate) overrides
    p.add_argument("--curve", dest="curve_enabled", action="store_const", const=True,
                   default=None, help="gate on the change's percentile grade against the "
                   "baseline distribution instead of absolute thresholds")
    p.add_argument("--baseline-file", dest="baseline_file",
                   help="project baseline cache to grade against (default: "
                        ".impact-gate-baseline.json)")
    p.add_argument("--warn-percentile", dest="warn_percentile", type=float)
    p.add_argument("--block-percentile", dest="block_percentile", type=float)
    p.add_argument("--curve-prior-weight", dest="curve_prior_weight", type=float,
                   help="K in the empirical-Bayes blend w = n/(n+K) between the project "
                        "baseline and the shipped seed. 0 grades PURELY against the "
                        "--baseline-file distribution (ignore the seed); large K leans on "
                        "the seed. Default from config (200).")
    # cognitive-complexity gate (absolute per-method; independent of the change-impact gate)
    p.add_argument("--cognitive-max", dest="cognitive_max", type=int,
                   help="block when any method in a changed file has cognitive complexity "
                        "(Campbell 2018) above this. Catches deeply-nested, hard-to-read "
                        "methods the change-impact score cannot see. Off unless set; "
                        "SonarSource's default line is 15.")


# Gate knobs an argparse flag may override on top of the config file, when given.
_OVERRIDE_ATTRS = ("warn_at", "block_at", "enforcement", "tolerance", "measure_config",
                   "curve_enabled", "baseline_file", "warn_percentile", "block_percentile",
                   "curve_prior_weight", "cognitive_max")


def _resolve_config(args) -> GateConfig:
    # Base policy from the policy port (local .impact-gate.yml today); CLI flags are the
    # outermost layer and win over whatever the provider supplied.
    cfg = providers.select_policy_provider(args.config, args.repo).policy(args.repo)
    for attr in _OVERRIDE_ATTRS:
        val = getattr(args, attr, None)
        if val is not None:
            setattr(cfg, attr, val)
    cfg.validate()
    return cfg


def _cmd_score(args) -> int:
    cfg = _resolve_config(args)
    mcfg = MeasureConfig.load(cfg.measure_config)
    try:
        changed = gitio.changed_files(args.repo, args.mode, args.base)
    except gitio.DiffError as e:
        print(f"impact-gate: {e}", file=sys.stderr)
        return 1

    score = score_change(changed, mcfg)

    grade = None
    if cfg.curve_enabled:
        grades = providers.select_grade_provider(args.repo, cfg.baseline_file,
                                                 cfg.curve_prior_weight)
        grade = grades.grade(providers.ChangeSummary.of(score), args.repo)
        if grade is None:                    # backend unreachable -> shipped-seed only
            grade = providers.seed_grade(score, cfg.curve_prior_weight)
        level = cfg.level_for_grade(grade.percentile)
        blocked = cfg.blocks_grade(grade.percentile)
    else:
        level = cfg.level(score.impact)
        blocked = cfg.blocks(score.impact)

    # Cognitive gate: an ABSOLUTE per-method readability check, OR'd with the change-impact gate.
    # A change can pass on impact yet block here for leaving a deeply-nested, hard-to-read method.
    if cfg.cognitive_enabled() and cfg.cognitive_level(score.cognitive_max) == "block":
        level = "block"
        blocked = blocked or cfg.blocks_cognitive(score.cognitive_max)

    if args.format == "json":
        print(report.render_json(score, cfg, level, args.mode, args.base, blocked, grade))
    elif args.format == "markdown":
        print(report.render_markdown(score, cfg, level, args.mode, args.base, blocked, grade))
    else:
        print(report.render_text(score, cfg, level, args.mode, args.base, blocked, grade))
        if blocked:
            print("\nimpact-gate: change BLOCKED. Impact exceeds the block threshold. "
                  "Simplify the change or refactor the code it touches, then retry.",
                  file=sys.stderr)
    return 2 if blocked else 0


def _cmd_baseline(args) -> int:
    """Walk the merged mainline into the project distribution and cache it to disk."""
    cfg = _resolve_config(args)
    mcfg = MeasureConfig.load(cfg.measure_config)
    out_path = os.path.join(args.repo, cfg.baseline_file)
    try:
        bl = baseline.build_baseline(
            args.repo, mcfg,
            base_ref=args.base_ref,
            max_commits=args.max_commits,
            exclude_subject_pattern=args.exclude_subject_pattern,
        )
    except (gitio.DiffError, OSError, ValueError,
            subprocess.CalledProcessError) as e:
        print(f"impact-gate: could not build baseline (is '{args.base_ref or 'main'}' "
              f"a branch with history?): {e}", file=sys.stderr)
        return 1
    if bl.n == 0:
        print(f"impact-gate: no landed changes found on '{bl.base_ref}'; nothing to "
              "baseline. Check --base-ref points at a branch with history.",
              file=sys.stderr)
        return 1
    providers.select_grade_provider(args.repo, cfg.baseline_file,
                                    cfg.curve_prior_weight).publish(args.repo, bl)
    print(f"impact-gate: baseline written to {out_path} "
          f"({bl.n} observations from '{bl.base_ref}').")
    return 0


def _detect_provider() -> str:
    """Guess the CI provider from the environment when --provider is not given."""
    if os.environ.get("GITLAB_CI") or os.environ.get("CI_MERGE_REQUEST_IID"):
        return "gitlab"
    return "github"


def _cmd_comment(args) -> int:
    provider = args.provider or _detect_provider()
    body = (open(args.body_file, encoding="utf-8").read()
            if args.body_file else sys.stdin.read())
    if provider == "gitlab":
        return _comment_gitlab(args, body)
    return _comment_github(args, body)


def _comment_github(args, body: str) -> int:
    from . import ghapi
    token = args.token or os.environ.get("GITHUB_TOKEN")
    repo = args.repo_slug or os.environ.get("GITHUB_REPOSITORY")
    pr = args.pr or ghapi.detect_pr_number(os.environ.get("GITHUB_EVENT_PATH"))
    if not token or not repo or not pr:
        print("impact-gate: need a token, repo (owner/name), and PR number to comment "
              "(GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_EVENT_PATH are set in Actions).",
              file=sys.stderr)
        return 1
    try:
        result = ghapi.upsert_pr_comment(ghapi.GitHubAPI(token), repo, int(pr), body)
    except Exception as e:
        print(f"impact-gate: could not post PR comment: {e}", file=sys.stderr)
        return 1
    print(f"impact-gate: PR comment {result}")
    return 0


def _comment_gitlab(args, body: str) -> int:
    from . import glapi
    token = args.token or os.environ.get("GITLAB_TOKEN")
    project = args.repo_slug or os.environ.get("CI_PROJECT_ID")
    mr = args.pr or os.environ.get("CI_MERGE_REQUEST_IID")
    api_base = os.environ.get("CI_API_V4_URL") or glapi.API
    if not token or not project or not mr:
        print("impact-gate: need a token, project, and MR iid to comment on GitLab "
              "(GITLAB_TOKEN with api scope; CI_PROJECT_ID and CI_MERGE_REQUEST_IID are "
              "set in merge-request pipelines).", file=sys.stderr)
        return 1
    try:
        result = glapi.upsert_mr_note(glapi.GitLabAPI(token, api_base),
                                      project, int(mr), body)
    except Exception as e:
        print(f"impact-gate: could not post MR note: {e}", file=sys.stderr)
        return 1
    print(f"impact-gate: MR note {result}")
    return 0


_HOOK_TEMPLATE = """\
#!/bin/sh
# impact-gate pre-commit hook (installed by `impact-gate install-hook`).
# Scores the staged change: a 'block' verdict (exit 2) aborts the commit, while ok/warn
# (exit 0) let it proceed. Configure thresholds and enforcement in .impact-gate.yml.
exec "{python}" -m impact_gate score --mode staged
"""


def _cmd_install_hook(args) -> int:
    """Install a git pre-commit hook that scores staged changes and gates the commit."""
    import stat
    try:
        rel = gitio._git(args.repo, "rev-parse", "--git-path", "hooks").strip()
    except subprocess.CalledProcessError:
        print(f"impact-gate: '{args.repo}' is not a git repository.", file=sys.stderr)
        return 1
    hooks_dir = rel if os.path.isabs(rel) else os.path.join(args.repo, rel)
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-commit")
    if os.path.exists(hook_path) and not args.force:
        print(f"impact-gate: a pre-commit hook already exists at {hook_path}. Re-run "
              "with --force to overwrite it.", file=sys.stderr)
        return 1
    with open(hook_path, "w", encoding="utf-8") as fh:
        fh.write(_HOOK_TEMPLATE.format(python=sys.executable))
    os.chmod(hook_path, os.stat(hook_path).st_mode
             | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"impact-gate: installed pre-commit hook at {hook_path}. It scores staged "
          "changes; set 'enforcement: block' in .impact-gate.yml to block risky commits.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="impact-gate",
                                 description="Report and gate on the change-impact of a change.")
    ap.add_argument("--version", action="version", version=f"impact-gate {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="score the current change and gate on it")
    _add_score_args(s)
    s.set_defaults(func=_cmd_score)

    b = sub.add_parser("baseline",
                       help="build and cache the project baseline distribution")
    b.add_argument("--repo", default=".", help="path to the git repo (default: .)")
    b.add_argument("--config", help="path to an .impact-gate.yml (else auto-discovered)")
    b.add_argument("--base-ref", dest="base_ref",
                   help="mainline branch to walk (default: main, or config's base_ref)")
    b.add_argument("--max-commits", dest="max_commits", type=int,
                   help="cap how many recent mainline commits are walked")
    b.add_argument("--exclude-subject-pattern", dest="exclude_subject_pattern",
                   help="regex on a merge subject to skip that MR entirely")
    b.add_argument("--baseline-file", dest="baseline_file",
                   help="where to write the cache (default: .impact-gate-baseline.json)")
    b.add_argument("--measure-config", help="Surveyor-style YAML for ignore globs etc.")
    b.set_defaults(func=_cmd_baseline)

    c = sub.add_parser("comment",
                       help="upsert a sticky PR/MR comment with a report (CI)")
    c.add_argument("--provider", choices=("github", "gitlab"),
                   help="CI provider to post to (default: auto-detected from the "
                        "environment; GitLab when GITLAB_CI/CI_MERGE_REQUEST_IID is set, "
                        "else GitHub).")
    c.add_argument("--body-file", help="markdown file to post (default: read stdin)")
    c.add_argument("--repo-slug",
                   help="GitHub owner/name (default: $GITHUB_REPOSITORY) or GitLab "
                        "project id/path (default: $CI_PROJECT_ID).")
    c.add_argument("--pr", type=int,
                   help="GitHub PR number (default: from $GITHUB_EVENT_PATH) or GitLab "
                        "MR iid (default: $CI_MERGE_REQUEST_IID).")
    c.add_argument("--token",
                   help="API token (default: $GITHUB_TOKEN, or $GITLAB_TOKEN for GitLab).")
    c.set_defaults(func=_cmd_comment)

    h = sub.add_parser("install-hook",
                       help="install a git pre-commit hook that gates staged changes")
    h.add_argument("--repo", default=".", help="path to the git repo (default: .)")
    h.add_argument("--force", action="store_true",
                   help="overwrite an existing pre-commit hook")
    h.set_defaults(func=_cmd_install_hook)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:            # config validation, bad args
        print(f"impact-gate: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
