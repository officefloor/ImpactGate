import pytest

from gitutil import init_repo


@pytest.fixture
def repo(tmp_path):
    """A fresh git repo on branch `main`, empty."""
    return init_repo(tmp_path / "proj")
