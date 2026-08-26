"""Test helpers: build throwaway git repos and score changes.

Deterministic. Commits use a fixed identity and date. System and global git config
are disabled, so a developer's own git settings cannot affect a run.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from impact_gate import engine, gitio

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00", "GIT_COMMITTER_DATE": "2020-01-01T00:00:00",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(repo, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True, text=True, env=_ENV)


def init_repo(path) -> Path:
    repo = Path(path)
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "checkout", "-q", "-b", "main")
    return repo


def write(repo, rel: str, content: str) -> None:
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def commit(repo, msg: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def stage(repo, rel: str, content: str) -> None:
    write(repo, rel, content)
    git(repo, "add", rel)


def score(repo, mode: str = "worktree", base: str = "main",
          wmc_context: str = "before"):
    changed = gitio.changed_files(str(repo), mode, base)
    return engine.score_change(changed, wmc_context=wmc_context)


def cc_func(name: str, branches: int) -> str:
    """A function with cyclomatic complexity == branches + 1 (one per `if`)."""
    lines = [f"def {name}(x):"]
    for i in range(branches):
        lines.append(f"    if x == {i}:")
        lines.append(f"        return {i}")
    lines.append("    return -1")
    return "\n".join(lines) + "\n"
