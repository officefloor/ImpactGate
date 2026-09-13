"""Sticky MR-note logic for GitLab, without touching the network."""
from impact_gate import glapi


class FakeAPI:
    def __init__(self, existing):
        self.existing = existing
        self.created = []
        self.updated = []

    def list_mr_notes(self, project, mr_iid):
        return self.existing

    def create_note(self, project, mr_iid, body):
        self.created.append((project, mr_iid, body))

    def update_note(self, project, mr_iid, note_id, body):
        self.updated.append((project, mr_iid, note_id, body))


def test_find_existing_matches_marker():
    notes = [{"body": "unrelated"}, {"id": 5, "body": glapi.MARKER + "\nhi"}]
    assert glapi.find_existing(notes)["id"] == 5
    assert glapi.find_existing([{"body": "none here"}]) is None


def test_upsert_creates_when_absent():
    api = FakeAPI(existing=[])
    result = glapi.upsert_mr_note(api, "42", 3, "BODY")
    assert result == "created"
    project, mr_iid, body = api.created[0]
    assert project == "42" and mr_iid == 3
    assert glapi.MARKER in body and "BODY" in body
    assert not api.updated


def test_upsert_updates_when_present():
    api = FakeAPI(existing=[{"id": 7, "body": glapi.MARKER + "\nold"}])
    result = glapi.upsert_mr_note(api, "42", 3, "NEW BODY")
    assert result == "updated"
    project, mr_iid, note_id, body = api.updated[0]
    assert note_id == 7
    assert "NEW BODY" in body and glapi.MARKER in body
    assert not api.created


def test_project_path_is_url_encoded():
    # A namespaced path must collapse to one URL-encoded segment; a numeric id is untouched.
    assert glapi.GitLabAPI._project("group/sub/project") == "group%2Fsub%2Fproject"
    assert glapi.GitLabAPI._project("42") == "42"
