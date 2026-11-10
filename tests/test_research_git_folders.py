"""Git tools given a folder path: list its files with or without a trailing slash, never an empty success."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from alchemy_task import research_git as rg
from alchemy_task import runtime
from helpers import git


class State:
    def __init__(self, data_dir):
        self.data_dir, self._d = data_dir, {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def set(self, key, value):
        self._d[key] = value


class Ctx:
    def __init__(self, settings, data_dir):
        self._s = dataclasses.asdict(settings)
        self.state = State(data_dir)

    def get_config(self, key, default=None):
        return self._s.get(key, default)


@pytest.fixture
def repo(settings, data_dir):
    r = Path(os.environ["HOME"]) / "code" / "deep"
    d = r / "claude-api" / "deployment"
    d.mkdir(parents=True)
    git(r, "init", "-q", "-b", "main")
    (d / "deploy.sh").write_text("echo deploy-needle\n")
    (d / "build.sh").write_text("echo build-needle\n")
    (d / "server.key").write_text("deploy-needle-secret\n")
    (d / ".env").write_text("TOKEN=deploy-needle-secret\n")
    (d / ".ssh").mkdir()
    (d / ".ssh" / "config").write_text("Host x\n")
    (r / "claude-api" / "only-keys").mkdir()
    (r / "claude-api" / "only-keys" / "prod.pem").write_text("x\n")
    (r / "README.md").write_text("hello\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "deploy scripts")
    runtime.bind(Ctx(settings, data_dir))
    yield r
    runtime.bind(None)


def call(fn, **args):
    return json.loads(fn(args))


@pytest.mark.parametrize("path", ["claude-api/deployment", "claude-api/deployment/", "claude-api"])
def test_folder_lists_tracked_files_with_or_without_slash(repo, path):
    res = call(rg.t_git_ls_files, repo=str(repo), path=path)
    assert res["ok"], res
    names = res["output"].split()
    assert "claude-api/deployment/deploy.sh" in names and "claude-api/deployment/build.sh" in names
    for bad in ("server.key", ".env", ".ssh", "prod.pem"):
        assert bad not in res["output"]


@pytest.mark.parametrize("path", ["claude-api/deployment", "claude-api/deployment/"])
def test_folder_grep_and_log_find_the_files(repo, path):
    grep = call(rg.t_git_grep, repo=str(repo), pattern="needle", path=path)
    assert grep["ok"] and "deploy.sh" in grep["output"] and "build.sh" in grep["output"]
    assert "secret" not in grep["output"]
    log = call(rg.t_git_log, repo=str(repo), path=path)
    assert log["ok"] and "deploy scripts" in log["output"]


def test_folder_of_only_credentials_is_empty_not_leaked(repo):
    res = call(rg.t_git_ls_files, repo=str(repo), path="claude-api/only-keys")
    assert res["ok"] and res["output"].strip() == ""
    assert "prod.pem" not in json.dumps(res)


def test_missing_folder_is_clean_empty(repo):
    res = call(rg.t_git_ls_files, repo=str(repo), path="no/such/folder")
    assert res["ok"] and res["output"].strip() == ""


def test_listing_failure_is_an_error_not_empty_success(repo, monkeypatch):
    """If git drops every file for a path that has tracked files, the tool says so instead of returning nothing."""
    monkeypatch.setattr(rg, "_ls_listing", lambda repo_, path: ("", False))   # git drops everything
    res = call(rg.t_git_ls_files, repo=str(repo), path="claude-api/deployment")
    assert not res["ok"] and "listing failed" in res["error"].lower()
    # a folder holding only credential files is still a clean empty, not an error
    res = call(rg.t_git_ls_files, repo=str(repo), path="claude-api/only-keys")
    assert res["ok"] and res["output"].strip() == ""
