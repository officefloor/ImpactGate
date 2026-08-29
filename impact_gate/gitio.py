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

# git's canonical empty-tree object; the "parent" a root commit is diffed against.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


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


# ---- history walk (for the project baseline) -----------------------------------

def head_sha(repo_path: str, rev: str = "HEAD") -> str:
    return _git(repo_path, "rev-parse", rev).strip()


def merge_base(repo_path: str, a: str, b: str) -> str | None:
    """Public alias: the best common ancestor (branch-start point) of two revs."""
    return _merge_base(repo_path, a, b)


def is_ancestor(repo_path: str, ancestor: str, descendant: str) -> bool:
    """True if `ancestor` is reachable from `descendant` — used to tell a child MR
    (feature merged into the branch) from a sync (parent/main merged into the branch)."""
    r = subprocess.run(["git", "-C", repo_path, "merge-base", "--is-ancestor",
                        ancestor, descendant], capture_output=True)
    return r.returncode == 0


def rev_parents(repo_path: str, rev: str = "HEAD") -> dict[str, list[str]]:
    """Map every commit reachable from `rev` -> its parent SHAs (first parent first)."""
    out = _git(repo_path, "rev-list", "--parents", rev)
    parents: dict[str, list[str]] = {}
    for line in out.split("\n"):
        if not line:
            continue
        shas = line.split()
        parents[shas[0]] = shas[1:]
    return parents


def mainline_commits(repo_path: str, rev: str = "HEAD",
                     max_commits: int | None = None) -> list[str]:
    """The first-parent spine of `rev`, newest first (the landed-changes mainline)."""
    args = ["rev-list", "--first-parent"]
    if max_commits is not None:
        args += ["-n", str(max_commits)]
    args.append(rev)
    return [s for s in _git(repo_path, *args).split("\n") if s]


def first_parent_spine(repo_path: str, start: str, tip: str) -> list[str]:
    """Commits on `tip`'s first-parent chain back to but excluding `start`
    (newest first). This is one branch's own line of commits."""
    out = _git(repo_path, "rev-list", "--first-parent", f"{start}..{tip}")
    return [s for s in out.split("\n") if s]


def commit_subject(repo_path: str, rev: str) -> str:
    return _git(repo_path, "log", "-1", "--format=%s", rev).strip()


def diff_between(repo: GitRepo, old_rev: str, new_rev: str) -> list[ChangedFile]:
    """The `ChangedFile`s of the net diff old_rev..new_rev, with before/after bytes.

    Shares the -U0 rename-aware diff and blob streaming used by the live modes, so a
    historical range is scored exactly as the same change would be today. `old_rev` may
    be EMPTY_TREE to score a root commit's whole content as added.
    """
    out: list[ChangedFile] = []
    for d in repo.diff(old_rev, new_rev):
        if d.is_binary:
            continue
        new_path = d.new_path or d.old_path or ""
        old_path = d.old_path or new_path
        before = None if d.status == "A" else _blob_bytes(repo, old_rev, old_path)
        after = None if d.status == "D" else _blob_bytes(repo, new_rev, new_path)
        out.append(ChangedFile(path=new_path, status=d.status, before=before,
                               after=after, added=d.added, removed=d.removed))
    return out
