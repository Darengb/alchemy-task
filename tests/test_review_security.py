"""Review fixes: research git env, read-only discovery bindings, sweeper context, no ~/.hermes fallback."""
import contextvars
import subprocess
import threading
from types import SimpleNamespace

import pytest

from alchemy_task import research_git as rg
from alchemy_task import worksession as ws
from alchemy_task.core import reader_policy as rp
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.core.gitops import minimal_git_env
from test_discovery_integration import configure, service


# ------------------------------------------------------------ item 1: research git env

def test_research_git_child_gets_only_allowlisted_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/evil.so")
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw["env"])
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(rg.subprocess, "run", fake_run)
    rg._git_capped(tmp_path, ["log"])
    assert "OPENAI_API_KEY" not in seen and "ANTHROPIC_API_KEY" not in seen
    assert "LD_PRELOAD" not in seen and "GIT_DIR" not in seen
    allowed = set(minimal_git_env()) | set(rg._GIT_ENV)
    assert set(seen) <= allowed
    for k, v in rg._GIT_ENV.items():
        assert seen[k] == v
    assert seen["PATH"]


def test_research_git_env_really_reaches_git_without_keys(monkeypatch, tmp_path):
    """Real git: an alias that prints the env shows no provider key."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    env = rg._child_env()
    out = subprocess.run(["git", "-C", str(repo), "-c", "alias.envdump=!env", "envdump"], env=env,
                         capture_output=True, text=True, check=True).stdout
    assert "sk-should-not-leak" not in out and "OPENAI_API_KEY" not in out


# ------------------------------------------------------------ item 3: read-only bindings

def test_banned_toolsets_cover_exec_write_and_composites():
    for name in ("terminal", "code_execution", "file", "cronjob", "delegation", "browser", "computer_use",
                 "hermes-cli", "hermes-cron", "debugging", "coding", "", None, 3):
        assert rp.banned_toolset(name), name
    for name in ("web", "mail", "approved-messaging", "session_search", "mcp-gmail"):
        assert not rp.banned_toolset(name), name
    assert rp.allowed_reader_toolsets(["mail", "terminal", "mail", "web", "file"]) == ["mail", "web"]


def test_check_binding_refuses_write_like_tool_and_banned_toolsets():
    assert rp.check_binding("mcp_gmail__search_threads", ["mcp-gmail"]) == ["mcp-gmail"]
    with pytest.raises(UserError, match="discovery readers must be read-only tools"):
        rp.check_binding("terminal", [])
    with pytest.raises(UserError, match="discovery readers must be read-only tools"):
        rp.check_binding("mcp_gmail__send_email", [])
    with pytest.raises(UserError, match="terminal"):
        rp.check_binding("reader", ["mail", "terminal"])
    # a sender keeps its send tool, but not exec toolsets
    assert rp.check_binding("send_message", ["messaging"], sender=True) == ["messaging"]
    with pytest.raises(UserError, match="code_execution"):
        rp.check_binding("send_message", ["code_execution"], sender=True)


def test_configure_refuses_write_like_reader_and_banned_toolset(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    base = {'source_key': 'feed', 'name': 'Feed', 'account_key': 'account', 'scope': ['board'],
            'relevance': {'identity_requirements': [], 'rules': 'All issues'}}
    fields = {k: k for k in ['account_key', 'scope', 'start', 'end', 'items', 'next_cursor', 'pagination_exhausted']}
    with pytest.raises(UserError, match="discovery readers must be read-only tools"):
        integration.configure('work', {**base, 'read_method': 'terminal',
                                       'binding': {'tool': 'terminal', 'response_fields': fields}}, user_approved=True)
    with pytest.raises(UserError, match="terminal"):
        integration.configure('work', {**base, 'read_method': 'reader', 'toolsets': ['terminal'],
                                       'binding': {'tool': 'reader', 'response_fields': fields}}, user_approved=True)
    with pytest.raises(UserError, match="read-only"):
        integration.configure('work', {**base, 'read_method': 'reader',
                                       'binding': {'tool': 'reader', 'response_fields': fields},
                                       'thread_binding': {'tool': 'mcp_slack__post_message'}}, user_approved=True)
    assert not (ctx.state.get('discovery_sources', default={}) or {}).get('work')
    assert configure(integration)['approved'] is True  # the normal read-only reader still works


def _delivery(**over):
    b = {'origin_session': 'parent', 'target': 'synthetic-chat', 'scheduled_approved': True,
         'toolsets': ['approved-messaging'], 'verification_message_id': 'existing', 'verification_text': 'Existing message',
         'send_tool': 'approved_sender', 'read_tool': 'approved_message_reader', 'send_arguments': {},
         'send_fields': {'chat': 'target', 'text': 'text'}, 'send_id_path': 'message.id', 'read_arguments': {},
         'read_fields': {'chat': 'target', 'id': 'message_id'},
         'read_response': {'message_id': 'id', 'target': 'chat', 'text': 'text'}}
    b.update(over)
    return b


def test_delivery_binding_refuses_banned_toolsets_and_write_like_readback(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    calls = []
    ctx.dispatch_tool = lambda name, args: calls.append(name) or {'id': 'existing', 'chat': 'synthetic-chat', 'text': 'Existing message'}
    with pytest.raises(UserError, match="terminal"):
        integration.configure_delivery('work', _delivery(toolsets=['approved-messaging', 'terminal']), user_approved=True)
    with pytest.raises(UserError, match="discovery readers must be read-only tools"):
        integration.configure_delivery('work', _delivery(read_tool='execute_code'), user_approved=True)
    assert calls == []  # refused before any dispatch
    assert not (ctx.state.get('discovery_delivery', default={}) or {}).get('work')


def test_read_page_never_dispatches_a_saved_write_like_reader(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    ctx.dispatch_tool = lambda *a: pytest.fail("dispatched")
    with pytest.raises(UserError, match="read-only"):
        integration._read_page({}, 's', 'e', None, binding={'tool': 'terminal', 'response_fields': {}})


def test_stream_reader_toolsets_union_minus_banned():
    stream = {'name': 'work', 'sources': [{'name': 'Feed', 'scope': ['b'], 'toolsets': ['mail', 'terminal']}]}
    configs = {'feed': {'name': 'Feed', 'scope': ['b'], 'toolsets': ['web', 'file'],
                        'binding': {'toolsets': ['mcp-gmail']}},
               'other': {'name': 'Other', 'scope': ['x'], 'toolsets': ['notmine']}}
    got = rp.stream_reader_toolsets(stream, configs, {'toolsets': ['approved-messaging', 'code_execution', 'mail']})
    assert got == ['mail', 'web', 'mcp-gmail', 'approved-messaging']


def test_needs_read_only_reader_reports_old_streams_without_crashing(settings, data_dir, tmp_path):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    assert rp.needs_read_only_reader(rt) == []
    streams = ctx.state.get('streams')
    streams['work']['sources'][0]['toolsets'] = ['terminal']
    ctx.state.set('streams', streams)
    ctx.state.set('discovery_sources', {'work': {'feed': {'name': 'Feed', 'read_method': 'execute_code', 'toolsets': ['mail']},
                                                 'junk': 'not a dict'}})
    ctx.state.set('discovery_delivery', {'work': {'toolsets': ['hermes-cli'], 'read_tool': 'reader'}})
    rows = rp.needs_read_only_reader(rt)
    assert {'stream': 'work', 'source_key': 'Feed', 'reason': 'needs toolset(s) terminal'} in rows
    assert {'stream': 'work', 'source_key': 'feed', 'reason': 'reader execute_code is not a read-only tool'} in rows
    assert {'stream': 'work', 'source_key': 'delivery', 'reason': 'needs toolset(s) hermes-cli'} in rows
    assert "need a read-only reader" in rp.needs_read_only_reader_text(rt)
    broken = SimpleNamespace(ctx=SimpleNamespace(state=None))
    assert rp.needs_read_only_reader(broken) == []


# ------------------------------------------------------------ recommended items

PROFILE = contextvars.ContextVar("profile", default="launch")


def test_sweeper_thread_runs_in_copied_context(monkeypatch, tmp_path):
    monkeypatch.delenv("ALCHEMY_TASK_NO_SWEEPER", raising=False)
    seen, done = {}, threading.Event()
    monkeypatch.setattr(ws, "_sweep_loop", lambda data_dir: seen.update(profile=PROFILE.get()) or done.set())
    monkeypatch.setattr(ws, "_sweeper", None)
    token = PROFILE.set("beta")
    try:
        ws._ensure_sweeper(SimpleNamespace(data_dir=tmp_path))
    finally:
        PROFILE.reset(token)
    assert done.wait(2) and seen["profile"] == "beta"
    ws._sweeper.join(2)
    monkeypatch.setattr(ws, "_sweeper", None)


def test_hermes_home_comes_from_hermes_constants(monkeypatch, tmp_path):
    import hermes_constants
    from alchemy_task import discovery_sources, research_agent
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path / "profile-home")
    assert research_agent._hermes_home() == tmp_path / "profile-home"
    assert discovery_sources._hermes_home() == tmp_path / "profile-home"
