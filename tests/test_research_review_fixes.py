"""Outcome tests for the research-access review findings B1, B2, M1, M2, M3, M4."""
from __future__ import annotations

import os
import subprocess

import pytest

from alchemy_task import research_agent as ra
from alchemy_task import research_git as rg
from alchemy_task import runtime
from test_research_agent import create, ctx  # noqa: F401 - shared fixtures


@pytest.fixture(autouse=True)
def _fresh_children():
    ra._research_children.clear()
    yield
    ra._research_children.clear()


def _child(ctx, settings, data_dir):
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id, origin_session="chat-1")
    ra.subagent_start(child_session_id="child-1", child_subagent_id="sa-1")
    return doc


# B1: MCP / connector / browser write tools are refused; read-verb tools pass
@pytest.mark.parametrize("tool", ["mcp__amplitude__use_amp_flags", "mcp__treg__call", "connectors__gmail__send_email",
                                  "connectors__slack__post_message", "mcp_github_create_issue", "browser_click",
                                  "browser_exec", "kanban_complete", "ha_call_service", "mcp__x__weird"])
def test_research_child_refused_write_like_external_tools(ctx, settings, data_dir, tool):
    _child(ctx, settings, data_dir)
    v = ra.pre_tool_call(tool_name=tool, session_id="child-1", task_id="sa-1")
    assert v and v["action"] == "block"
    assert ra.pre_tool_call(tool_name=tool, session_id="main-chat", task_id="") is None


@pytest.mark.parametrize("tool", ["mcp__amplitude__get_amplitude_context", "mcp__amplitude__query_amplitude_data",
                                  "connectors__gmail__search_messages", "connectors__slack__list_channels",
                                  "mcp__notion__read_page", "web_search", "session_search", "tool_search"])
def test_research_child_read_external_tools_pass(ctx, settings, data_dir, tool):
    _child(ctx, settings, data_dir)
    assert ra.pre_tool_call(tool_name=tool, session_id="child-1", task_id="sa-1") is None


def test_is_write_like_never_raises():
    assert ra.is_write_like(object()) in (True, False)
    assert ra.is_write_like(None) is False


# B2 / M1: a toolset rejection falls back to the old safe set; unavailable toolsets are dropped
class _Rejecting:
    def __init__(self, msg):
        self.msg, self.requests = msg, []

    def launch(self, req):
        self.requests.append(req)
        if len(self.requests) == 1:
            raise ValueError(self.msg)
        return {"subagent_id": "sa-fb", "state": "RUNNING"}


@pytest.mark.parametrize("msg", ["Requested toolsets would broaden parent permissions.", "Unknown toolsets: slack."])
def test_launch_falls_back_when_parent_lacks_toolsets(ctx, settings, data_dir, monkeypatch, msg):
    doc = create(settings, data_dir)
    fake = _Rejecting(msg)
    monkeypatch.setattr(runtime.Runtime().ctx, "subagent_lifecycle", fake, raising=False)
    res = ra.launch(runtime.Runtime(), doc.task_id, origin_session="chat-1")
    assert res["started"] is True
    last = fake.requests[-1]
    toolsets = last["allowed_toolsets"] if isinstance(last, dict) else last.allowed_toolsets
    assert tuple(toolsets) == ra.FALLBACK_TOOLSETS


def test_launch_does_not_fall_back_on_other_errors(ctx, settings, data_dir, monkeypatch):
    doc = create(settings, data_dir)
    fake = _Rejecting("No active Hermes parent session is available.")
    monkeypatch.setattr(runtime.Runtime().ctx, "subagent_lifecycle", fake, raising=False)
    res = ra.launch(runtime.Runtime(), doc.task_id, origin_session="chat-1")
    assert res["started"] is False and len(fake.requests) == 1


# M2: discovery children get the same guard
def test_discovery_guard_refuses_write_like_and_credential_reads():
    from alchemy_task.discovery_runner import DiscoveryRunner
    r = DiscoveryRunner.__new__(DiscoveryRunner)
    r._child_for = lambda s, t: ("run-1", None)
    assert r.pre_tool_call("mcp__treg__call", {}, "c", "t")["action"] == "block"
    assert r.pre_tool_call("read_file", {"path": "~/.ssh/id_ed25519"}, "c", "t")["action"] == "block"
    assert r.pre_tool_call("read_file", {"path": "/srv/app/README.md"}, "c", "t") is None


# M3: symlinks, broader names and folders
@pytest.mark.parametrize("path", ["~/.supabase/access-token", "/home/u/.npmrc", "/home/u/.bash_history",
                                  "/home/u/.config/google-chrome/Default/Cookies",
                                  "/home/u/.config/google-chrome/Default/Login Data", "/home/u/.docker/config.json",
                                  "/home/u/.kube/config", "/home/u/app/token.json", "/home/u/app/.git/config",
                                  "/home/u/app/config/prod.env", "/home/u/.config/gcloud/adc.json",
                                  "~/private/notes.md"])
def test_more_credential_paths_refused(path):
    assert rg.is_secret_path(path)


@pytest.mark.parametrize("path", ["/home/u/app/tokenizer.py", "/home/u/app/docs/secrets-management.md",
                                  "/home/u/app/src/private_api.py", "/home/u/app/README.md"])
def test_ordinary_code_files_still_readable(path):
    assert not rg.is_secret_path(path)


def test_symlink_to_credential_is_refused(tmp_path):
    secret = tmp_path / ".ssh"
    secret.mkdir()
    (secret / "id_ed25519").write_text("x")
    link = tmp_path / "innocent.txt"
    link.symlink_to(secret / "id_ed25519")
    assert rg.is_secret_path(str(link))


# M4: git output is redacted
def test_git_output_is_redacted(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@e"}
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    (repo / "settings.py").write_text("API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz123456'\nghp = 'ghp_" + "a" * 36 + "'\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True, env=env)
    out = rg._git(repo, ["show", "HEAD"])
    assert "sk-abcdefghijklmnop" not in out and "ghp_aaaa" not in out and "[redacted]" in out


# R1: relative paths, globs and patterns are not judged by the gateway's working directory
def test_relative_paths_allowed_even_from_a_dot_hermes_cwd(tmp_path, monkeypatch):
    d = tmp_path / ".hermes"
    d.mkdir()
    monkeypatch.chdir(d)
    assert rg.refuse_file_read("read_file", {"path": "notes/x.md"}) is None
    assert rg.refuse_file_read("search_files", {"pattern": "def", "path": "."}) is None
    assert rg.refuse_file_read("search_files", {"pattern": "*.md", "target": "files", "file_glob": "*.py"}) is None
    assert rg.refuse_file_read("read_file", {"path": ".env"})  # still refused by name
    assert rg.refuse_file_read("search_files", {"pattern": "*.pem", "target": "files"})


# R2: redaction is fast on adversarial input and still masks
def test_redact_is_linear_on_adversarial_input():
    import time
    t = time.time()
    rg.redact("KEY" * 70000)
    rg.redact("key_" * 50000 + "=")
    assert time.time() - t < 2
    assert "hunter2hunter2" not in rg.redact("API_KEY = 'hunter2hunter2'")


# R3: ordinary code files about tokens and credentials stay readable
@pytest.mark.parametrize("path", ["src/refresh_token_flow.py", "tests/test_access_token.py", "docs/api_token.md",
                                  "app/credentials.py", "app/tokenizer.py", "app/auth.py"])
def test_token_named_code_files_readable(path):
    assert not rg.is_secret_path(path)


# R4: camelCase and noun-first read tools pass; risky verbs are blocked
@pytest.mark.parametrize("tool,blocked", [("mcp__linear__getIssues", False), ("mcp__notion__notion-search", False),
                                          ("mcp__shop__catalog_search", False), ("mcp__x__export_and_delete", True),
                                          ("mcp__x__status_set", True), ("mcp__x__check_in", True),
                                          ("mcp__x__delete_search", True), ("connectors__gmail__SEND_EMAIL", True),
                                          ("connectors__gmail__GMAIL_FETCH_EMAILS", False),
                                          ("connectors__gmail__GMAIL_SEND_EMAIL", True)])
def test_mcp_verb_rules(tool, blocked):
    assert ra.is_write_like(tool) is blocked


def test_hermes_cache_and_plugin_data_are_readable_but_its_credentials_are_not():
    for ok in ("/home/u/.hermes/cache/scratch/C03T74B10SG.json", "/home/u/.hermes/plugin-data/x/discovery/run.json",
               "/home/u/.hermes/cron/output/job/run.md"):
        assert not rg.is_secret_path(ok), ok
    for bad in ("/home/u/.hermes/.env", "/home/u/.hermes/auth.json", "/home/u/.hermes/config.yaml",
                "/home/u/.hermes/mcp-tokens/slack.json", "/home/u/.hermes/browser-profiles/default/Cookies",
                "/home/u/.hermes/google_accounts/mbg.json", "/home/u/.hermes/profiles/other/.env"):
        assert rg.is_secret_path(bad), bad
