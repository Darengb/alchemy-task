"""Load the plugin directory as package `alchemy_task` and provide fixtures."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if "alchemy_task" not in sys.modules:
    spec = importlib.util.spec_from_file_location("alchemy_task", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["alchemy_task"] = mod
    spec.loader.exec_module(mod)

from alchemy_task.core.config import Settings  # noqa: E402
from helpers import FIXTURES, git  # noqa: E402


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace repo with two areas, a bare remote and one pushed commit."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / ".gitconfig").write_text("[user]\n\tname = Test\n\temail = t@example.com\n"
                                                  "[init]\n\tdefaultBranch = main\n")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(remote))
    ws = tmp_path / "ws"
    ws.mkdir()
    git(ws, "init", "-q", "-b", "main")
    for area in ("work", "home"):
        (ws / "areas" / area / "tasks").mkdir(parents=True)
        (ws / "areas" / area / "tasks" / ".keep").write_text("")
    for f in FIXTURES.glob("*.md"):
        (ws / "areas" / "work" / "tasks" / f.name).write_bytes(f.read_bytes())
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "init")
    git(ws, "remote", "add", "origin", str(remote))
    git(ws, "push", "-q", "origin", "main")
    return ws


@pytest.fixture
def settings(workspace):
    return Settings(workspace_root=str(workspace), timezone="America/New_York", git_run_hooks=True)


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "plugin-data"
    d.mkdir()
    return d


@pytest.fixture
def owner_only_feature(monkeypatch):
    """Planned follow-up: approvals.owner_only is gated off in v1. Tests of the gated
    enrollment/authorization code opt in here; production never sets this."""
    from alchemy_task import discovery_integration
    monkeypatch.setattr(discovery_integration, 'OWNER_ONLY_AVAILABLE', True, raising=False)
