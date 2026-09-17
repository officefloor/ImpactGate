"""GitRepo blob streaming: the persistent cat-file --batch protocol."""
import pytest

from impact_gate.core.gitplumb import GitRepo
from gitutil import commit, write


def test_blob_reads_file_with_newline_in_name(repo):
    write(repo, "plain.py", "x = 1\n")
    write(repo, "a\nb.py", "y = 2\n")
    commit(repo, "base")
    r = GitRepo(str(repo))
    if not r._supports_batch_z():
        r.close()
        pytest.skip("git cat-file --batch -Z unsupported (git < 2.42)")
    try:
        assert r.blob("HEAD", "a\nb.py")[1] == b"y = 2\n"
        assert r.blob("HEAD", "plain.py")[1] == b"x = 1\n"
    finally:
        r.close()


def test_blob_falls_back_to_newline_protocol_without_batch_z(repo):
    write(repo, "plain.py", "x = 1\n")
    commit(repo, "base")
    r = GitRepo(str(repo))
    r._batch_z = False
    try:
        assert "-Z" not in r._ensure_batch().args
        assert r.blob("HEAD", "plain.py")[1] == b"x = 1\n"
    finally:
        r.close()
