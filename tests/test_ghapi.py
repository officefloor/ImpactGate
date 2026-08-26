"""Sticky PR-comment logic, without touching the network."""
import json

from impact_gate import ghapi


class FakeAPI:
    def __init__(self, existing):
        self.existing = existing
        self.created = []
        self.updated = []

    def list_issue_comments(self, repo, pr):
        return self.existing

    def create_comment(self, repo, pr, body):
        self.created.append((repo, pr, body))

    def update_comment(self, repo, comment_id, body):
        self.updated.append((repo, comment_id, body))


def test_find_existing_matches_marker():
    comments = [{"body": "unrelated"}, {"id": 5, "body": ghapi.MARKER + "\nhi"}]
    assert ghapi.find_existing(comments)["id"] == 5
    assert ghapi.find_existing([{"body": "none here"}]) is None


def test_detect_pr_number(tmp_path):
    p = tmp_path / "event.json"
    p.write_text(json.dumps({"pull_request": {"number": 7}}))
    assert ghapi.detect_pr_number(str(p)) == 7
    p2 = tmp_path / "event2.json"
    p2.write_text(json.dumps({"number": 9}))
    assert ghapi.detect_pr_number(str(p2)) == 9
    assert ghapi.detect_pr_number(None) is None
    assert ghapi.detect_pr_number(str(tmp_path / "missing.json")) is None


def test_upsert_creates_when_absent():
    api = FakeAPI(existing=[])
    result = ghapi.upsert_pr_comment(api, "o/r", 3, "BODY")
    assert result == "created"
    repo, pr, body = api.created[0]
    assert repo == "o/r" and pr == 3
    assert ghapi.MARKER in body and "BODY" in body
    assert not api.updated


def test_upsert_updates_when_present():
    api = FakeAPI(existing=[{"id": 42, "body": ghapi.MARKER + "\nold"}])
    result = ghapi.upsert_pr_comment(api, "o/r", 3, "NEW BODY")
    assert result == "updated"
    repo, comment_id, body = api.updated[0]
    assert comment_id == 42
    assert "NEW BODY" in body and ghapi.MARKER in body
    assert not api.created
