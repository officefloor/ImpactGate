"""Turn a git change into the `ChangedFile` list the engine scores.

Three change modes, one per trigger:
  - range    : merge-base(base, HEAD)..HEAD  — the committed branch vs `main` (CI / PR).
  - staged   : HEAD vs the index             — the commit you are about to make (pre-commit).
  - worktree : HEAD vs files on disk         — uncommitted local edits.

Uses the vendored git plumbing (`GitRepo.blob` for cat-file streaming, `parse_diff`
for the -U0 hunk parse); the mode/base wiring and the working-tree read live here.
"""
from __future__ import annotations

import os
import subprocess

from .core.gitplumb import GitRepo, parse_diff

from .engine import ChangedFile

MODES = ("range", "staged", "worktree")

_DIFF = ["diff", "-U0", "-M", "--no-color", "--no-ext-diff", "--find-renames"]


class DiffError(RuntimeError):
    """A change could not be resolved (e.g. no merge-base — shallow clone)."""


def _git(repo_path: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", repo_path, *args],
                         check=True, capture_output=True)
    return out.stdout.decode("utf-8", errors="replace")


def _merge_base(repo_path: str, a: str, b: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", repo_path, "merge-base", a, b],
                             check=True, capture_output=True)
        return out.stdout.decode().strip() or None
    except subprocess.CalledProcessError:
        return None


def _blob_bytes(repo: GitRepo, rev: str, path: str) -> bytes | None:
    got = repo.blob(rev, path)      # rev="" addresses the index (stage 0): ":path"
    return got[1] if got else None


def _worktree_bytes(repo_path: str, path: str) -> bytes | None:
    try:
        with open(os.path.join(repo_path, path), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def changed_files(repo_path: str, mode: str = "staged",
                  base: str = "main") -> list[ChangedFile]:
    """Resolve the change under `mode` into scored-ready `ChangedFile`s."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    repo = GitRepo(repo_path)
    try:
        if mode == "range":
            old_rev = _merge_base(repo_path, base, "HEAD")
            if old_rev is None:
                raise DiffError(
                    f"no merge-base between {base!r} and HEAD — the base branch is not "
                    f"present. Fetch full history first (on GitHub set "
                    f"`actions/checkout` with `fetch-depth: 0`, or `git fetch origin {base}`).")
            text = _git(repo_path, *_DIFF, old_rev, "HEAD")
        elif mode == "staged":
            old_rev = "HEAD"
            text = _git(repo_path, *_DIFF, "--cached", "HEAD")
        else:  # worktree
            old_rev = "HEAD"
            text = _git(repo_path, *_DIFF, "HEAD")

        out: list[ChangedFile] = []
        for d in parse_diff(text):
            if d.is_binary:
                continue
            new_path = d.new_path or d.old_path or ""
            old_path = d.old_path or new_path
            before = None if d.status == "A" else _blob_bytes(repo, old_rev, old_path)
            if d.status == "D":
                after = None
            elif mode == "staged":
                after = _blob_bytes(repo, "", new_path)          # the index version
            elif mode == "worktree":
                after = _worktree_bytes(repo_path, new_path)
            else:  # range
                after = _blob_bytes(repo, "HEAD", new_path)
            out.append(ChangedFile(path=new_path, status=d.status,
                                   before=before, after=after,
                                   added=d.added, removed=d.removed))

        # `git diff HEAD` shows only tracked files, so a brand-new untracked file is
        # invisible in worktree mode. Include those explicitly (all lines added), so a
        # locally-created file is scored like the added file it will become on commit.
        if mode == "worktree":
            others = _git(repo_path, "ls-files", "--others", "--exclude-standard")
            for path in others.split("\n"):
                if not path:
                    continue
                data = _worktree_bytes(repo_path, path)
                if data is None:
                    continue
                nlines = data.count(b"\n") + 1
                out.append(ChangedFile(path=path, status="A", before=None,
                                       after=data, added=[(1, nlines)], removed=[]))
        return out
    finally:
        repo.close()
