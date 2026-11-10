"""Read-only git tools for research workers: find repos, log, show, grep, ls-files; secrets refused."""
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
def repo(settings, data_dir, tmp_path):
    home = Path(os.environ["HOME"])           # the workspace fixture points HOME at tmp_path/home
    r = home / "code" / "app"
    (r / "src").mkdir(parents=True)
    git(r, "init", "-q", "-b", "main")
    (r / "src" / "main.py").write_text("def hello():\n    return 'needle here'\n")
    (r / ".env").write_text("API_TOKEN=needle-secret\n")
    (r / "config").mkdir()
    (r / "config" / "auth.json").write_text('{"token": "needle-secret"}\n')
    (r / "deploy.pem").write_text("needle-secret\n")
    (r / "secrets.yaml").write_text("needle-secret\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "first commit")
    (r / "src" / "main.py").write_text("def hello():\n    return 'needle changed'\n")
    git(r, "commit", "-qam", "second commit")
    # noise that find must skip
    (home / "code" / "web" / "node_modules" / "dep").mkdir(parents=True)
    git(home / "code" / "web" / "node_modules" / "dep", "init", "-q")
    (home / ".cache" / "hidden").mkdir(parents=True)
    git(home / ".cache" / "hidden", "init", "-q")
    (home / ".hermes" / "plugins" / "x").mkdir(parents=True)
    git(home / ".hermes" / "plugins" / "x", "init", "-q")
    outside = tmp_path / "outside"
    outside.mkdir()
    git(outside, "init", "-q")
    runtime.bind(Ctx(settings, data_dir))
    yield r
    runtime.bind(None)


def call(fn, **args):
    return json.loads(fn(args))


def test_find_repos_under_home_and_workspace(repo, settings):
    data = call(rg.t_git_find_repos)
    assert data["ok"]
    found = {Path(p).resolve() for p in data["repos"]}
    assert repo.resolve() in found
    assert Path(settings.workspace_root).resolve() in found
    home = Path(os.environ["HOME"]).resolve()
    names = " ".join(str(Path(p).resolve().relative_to(home)) for p in data["repos"] if home in Path(p).resolve().parents)
    assert "node_modules" not in names and ".cache" not in names and ".hermes" not in names
    assert data["roots"]


def test_log_show_grep_ls_files(repo):
    log = call(rg.t_git_log, repo=str(repo))
    assert log["ok"] and "second commit" in log["output"] and "first commit" in log["output"]
    show = call(rg.t_git_show, repo=str(repo), rev="HEAD")
    assert show["ok"] and "needle changed" in show["output"]
    blob = call(rg.t_git_show, repo=str(repo), rev="HEAD~1", path="src/main.py")
    assert blob["ok"] and "needle here" in blob["output"]
    grep = call(rg.t_git_grep, repo=str(repo), pattern="needle")
    assert grep["ok"] and "src/main.py" in grep["output"]
    files = call(rg.t_git_ls_files, repo=str(repo))
    assert files["ok"] and "src/main.py" in files["output"]


def test_credential_files_refused_or_hidden(repo):
    for path in (".env", "config/auth.json", "deploy.pem", "secrets.yaml"):
        res = call(rg.t_git_show, repo=str(repo), rev="HEAD", path=path)
        assert not res["ok"] and "credential" in res["error"].lower()
        res = call(rg.t_git_grep, repo=str(repo), pattern="needle", path=path)
        assert not res["ok"]
    res = call(rg.t_git_show, repo=str(repo), rev="HEAD:.env")
    assert not res["ok"]
    # whole-repo reads never include secret contents or names
    grep = call(rg.t_git_grep, repo=str(repo), pattern="needle")
    assert "needle-secret" not in grep["output"]
    first = call(rg.t_git_show, repo=str(repo), rev="HEAD~1")
    assert "needle-secret" not in first["output"]
    logp = call(rg.t_git_log, repo=str(repo), patch=True)
    assert "needle-secret" not in logp["output"]
    files = call(rg.t_git_ls_files, repo=str(repo))
    for name in (".env", "auth.json", "deploy.pem", "secrets.yaml"):
        assert name not in files["output"]


def test_secret_path_rules():
    bad = [".env", "a/.env.local", "auth.json", "x/server.pem", "tls.key", "id_rsa", "id_ed25519.pub", ".netrc",
           ".git-credentials", "credentials.json", "aws/Credentials", "secrets.toml", "/home/u/.ssh/config",
           "/home/u/.aws/config", "/home/u/.config/gh/hosts.yml", "/home/u/.hermes/config.yaml"]
    for p in bad:
        assert rg.is_secret_path(p), p
    for p in ("src/main.py", "README.md", "docs/env.md", "keyboard.py", "config/settings.yaml"):
        assert not rg.is_secret_path(p), p


def test_outside_roots_and_secret_dirs_refused(repo, tmp_path):
    res = call(rg.t_git_log, repo=str(tmp_path / "outside"))
    assert not res["ok"] and "outside" in res["error"].lower()
    res = call(rg.t_git_log, repo=str(Path(os.environ["HOME"]) / ".hermes" / "plugins" / "x"))
    assert not res["ok"]
    res = call(rg.t_git_ls_files, repo=str(repo), path="../../outside")
    assert not res["ok"]
    res = call(rg.t_git_ls_files, repo=str(repo), path="/etc")
    assert not res["ok"]


def test_argument_injection_refused(repo, tmp_path):
    target = tmp_path / "x"
    for args in ({"rev": "--output=" + str(target)}, {"rev": "-c"}, {"path": "-c"}, {"path": "--output=x"},
                 {"rev": "HEAD", "path": ":(top)"}):
        res = call(rg.t_git_show, repo=str(repo), **args)
        assert not res["ok"], args
        res = call(rg.t_git_log, repo=str(repo), **args)
        assert not res["ok"], args
    assert not target.exists()
    res = call(rg.t_git_grep, repo=str(repo), pattern="--output=x")   # a pattern is data, passed after -e
    assert res["ok"] and not Path("x").exists()
    res = call(rg.t_git_log, repo="-c", rev="HEAD")
    assert not res["ok"]


def test_output_is_capped(repo):
    big = repo / "src" / "big.txt"
    big.write_text("needle line\n" * 20000)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "big")
    res = call(rg.t_git_grep, repo=str(repo), pattern="needle")
    assert res["ok"] and res["truncated"] and len(res["output"]) <= rg.OUTPUT_CAP


def test_file_read_guard_refuses_credentials():
    assert rg.refuse_file_read("read_file", {"path": "/home/u/project/.env"})
    assert rg.refuse_file_read("read_file", {"path": "~/.ssh/id_rsa"})
    assert rg.refuse_file_read("search_files", {"path": "/home/u/.hermes"})
    assert rg.refuse_file_read("search_files", {"path": "/home/u/code", "file_glob": "*.pem"})
    assert rg.refuse_file_read("read_file", {"path": "/home/u/code/src/main.py"}) is None
    assert rg.refuse_file_read("web_search", {"query": ".env"}) is None
    assert rg.refuse_file_read("read_file", None) is None


def test_tools_are_registered_in_research_toolset():
    from alchemy_task import research_agent as ra
    names = {s["name"] for s, _ in ra.RESEARCH_TOOLS}
    for n in ("research_git_find_repos", "research_git_log", "research_git_show", "research_git_grep",
              "research_git_ls_files"):
        assert n in names
    declared = (Path(ra.__file__).parent / "plugin.yaml").read_text()
    for n in names:
        assert f"  - {n}\n" in declared, n
