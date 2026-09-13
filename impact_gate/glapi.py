"""Minimal GitLab REST client for posting a sticky merge-request note.

Standard library only (urllib), mirroring ghapi so the tool keeps its lizard-only
footprint. Used by the `impact-gate comment --provider gitlab` subcommand from GitLab CI.
The pure helper (`find_existing`) is separated from HTTP so it can be unit tested
without network.

Auth is a token with `api` scope sent as the PRIVATE-TOKEN header (a project or personal
access token; the pipeline's CI_JOB_TOKEN cannot post notes). The API base defaults to
gitlab.com but is overridable (CI_API_V4_URL) so self-managed instances work.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

# Hidden marker used to find and update our own note, so each run edits one sticky note
# instead of adding a new one every time. Shared spelling with ghapi.MARKER on purpose.
MARKER = "<!-- impact-gate -->"
API = "https://gitlab.com/api/v4"


def find_existing(notes: list, marker: str = MARKER):
    """Return the first note whose body carries the marker, or None."""
    for n in notes:
        if marker in (n.get("body") or ""):
            return n
    return None


class GitLabAPI:
    def __init__(self, token: str, api: str = API):
        self.token = token
        self.api = api.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None):
        url = path if path.startswith("http") else f"{self.api}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("PRIVATE-TOKEN", self.token)
        req.add_header("User-Agent", "impact-gate")
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None

    @staticmethod
    def _project(project: str) -> str:
        # A numeric id passes through; a namespaced path (group/project) is URL-encoded
        # into a single path segment, as the GitLab API requires.
        return urllib.parse.quote(str(project), safe="")

    def list_mr_notes(self, project: str, mr_iid: int) -> list:
        out: list = []
        page = 1
        pid = self._project(project)
        while True:
            batch = self._request(
                "GET",
                f"/projects/{pid}/merge_requests/{mr_iid}/notes?per_page=100&page={page}")
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out

    def create_note(self, project: str, mr_iid: int, body: str):
        return self._request(
            "POST", f"/projects/{self._project(project)}/merge_requests/{mr_iid}/notes",
            {"body": body})

    def update_note(self, project: str, mr_iid: int, note_id: int, body: str):
        return self._request(
            "PUT",
            f"/projects/{self._project(project)}/merge_requests/{mr_iid}/notes/{note_id}",
            {"body": body})


def upsert_mr_note(api: GitLabAPI, project: str, mr_iid: int, body: str,
                   marker: str = MARKER) -> str:
    """Create the sticky note, or update it if one already exists. Returns which."""
    tagged = f"{marker}\n{body}"
    existing = find_existing(api.list_mr_notes(project, mr_iid), marker)
    if existing:
        api.update_note(project, mr_iid, existing["id"], tagged)
        return "updated"
    api.create_note(project, mr_iid, tagged)
    return "created"
