"""Minimal GitHub REST client for posting a sticky PR comment.

Standard library only (urllib), so the tool keeps its lizard-only footprint. Used by
the `impact-gate comment` subcommand from CI. The pure helpers (`find_existing`,
`detect_pr_number`) are separated from HTTP so they can be unit tested without network.
"""
from __future__ import annotations

import json
import os
import urllib.request

# Hidden marker used to find and update our own comment, so each run edits one sticky
# comment instead of adding a new one every time.
MARKER = "<!-- impact-gate -->"
API = "https://api.github.com"


def find_existing(comments: list, marker: str = MARKER):
    """Return the first comment whose body carries the marker, or None."""
    for c in comments:
        if marker in (c.get("body") or ""):
            return c
    return None


def detect_pr_number(event_path: str | None) -> int | None:
    """Read the PR number from the GitHub event payload (GITHUB_EVENT_PATH)."""
    if not event_path or not os.path.isfile(event_path):
        return None
    try:
        with open(event_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(data.get("pull_request"), dict) and data["pull_request"].get("number"):
        return int(data["pull_request"]["number"])
    if data.get("number"):
        return int(data["number"])
    return None


class GitHubAPI:
    def __init__(self, token: str, api: str = API):
        self.token = token
        self.api = api.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None):
        url = path if path.startswith("http") else f"{self.api}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "impact-gate")
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None

    def list_issue_comments(self, repo: str, issue: int) -> list:
        out: list = []
        page = 1
        while True:
            batch = self._request(
                "GET", f"/repos/{repo}/issues/{issue}/comments?per_page=100&page={page}")
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out

    def create_comment(self, repo: str, issue: int, body: str):
        return self._request("POST", f"/repos/{repo}/issues/{issue}/comments",
                             {"body": body})

    def update_comment(self, repo: str, comment_id: int, body: str):
        return self._request("PATCH", f"/repos/{repo}/issues/comments/{comment_id}",
                             {"body": body})


def upsert_pr_comment(api: GitHubAPI, repo: str, pr: int, body: str,
                      marker: str = MARKER) -> str:
    """Create the sticky comment, or update it if one already exists. Returns which."""
    tagged = f"{marker}\n{body}"
    existing = find_existing(api.list_issue_comments(repo, pr), marker)
    if existing:
        api.update_comment(repo, existing["id"], tagged)
        return "updated"
    api.create_comment(repo, pr, tagged)
    return "created"
