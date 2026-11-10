"""Outcome tests: plugin-started research children cannot write or execute (piece 3)."""
from __future__ import annotations

import pytest

from alchemy_task import research_agent as ra
from alchemy_task import runtime
from test_research_agent import create, ctx  # noqa: F401 - shared fixtures
from test_discovery_orchestration_outcomes import make

BLOCKED = ("write_file", "patch", "skill_manage", "terminal", "execute_code", "process_manage")
READS = ("read_file", "search_files", "session_search", "skill_view", "web_search", "research_submit")


@pytest.fixture(autouse=True)
def _fresh_children():
    ra._research_children.clear()
    yield
    ra._research_children.clear()


def _start_child(ctx, settings, data_dir, session="child-1"):
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id, origin_session="chat-1")
    ra.subagent_start(child_session_id=session, child_subagent_id="sa-1")
    return doc


@pytest.mark.parametrize("tool", BLOCKED)
def test_research_child_is_refused_write_and_exec_tools(ctx, settings, data_dir, tool):
    _start_child(ctx, settings, data_dir)
    # matched by the child's session id alone (the host may omit task_id)
    verdict = ra.pre_tool_call(tool_name=tool, session_id="child-1", task_id="")
    assert verdict and verdict["action"] == "block"
    assert "read-only" in verdict["message"] and tool in verdict["message"]
    # and by subagent id alone
    assert ra.pre_tool_call(tool_name=tool, task_id="sa-1")["action"] == "block"


@pytest.mark.parametrize("tool", BLOCKED + READS)
def test_normal_sessions_are_untouched(ctx, settings, data_dir, tool):
    _start_child(ctx, settings, data_dir)
    assert ra.pre_tool_call(tool_name=tool, session_id="main-chat", task_id="") is None
    assert ra.pre_tool_call(tool_name=tool, session_id="chat-1", task_id="main-task") is None


@pytest.mark.parametrize("tool", READS)
def test_research_child_reads_pass(ctx, settings, data_dir, tool):
    _start_child(ctx, settings, data_dir)
    assert ra.pre_tool_call(tool_name=tool, session_id="child-1", task_id="sa-1") is None


def test_blocked_calls_do_not_use_the_budget(ctx, settings, data_dir):
    _start_child(ctx, settings, data_dir)
    for _ in range(ra.CALL_BUDGET + 5):
        ra.pre_tool_call(tool_name="write_file", session_id="child-1", task_id="sa-1")
    assert ra.pre_tool_call(tool_name="web_search", session_id="child-1", task_id="sa-1") is None


def test_guard_never_raises_and_fails_closed_for_blocked_tools(ctx, settings, data_dir, monkeypatch):
    class Broken:
        def __contains__(self, item):
            raise RuntimeError("boom")
    monkeypatch.setattr(ra, "_research_children", Broken())
    assert ra.pre_tool_call(tool_name="write_file", session_id="child-1", task_id="sa-1")["action"] == "block"
    monkeypatch.undo()
    ra.pre_tool_call(tool_name=["unhashable"], session_id={}, task_id=None)  # must not raise


def test_blocking_survives_a_plugin_reload(ctx, settings, data_dir):
    _start_child(ctx, settings, data_dir)
    ra._research_children.clear()
    ra._runs.clear()
    ra._by_child_session.clear()
    assert ra.pre_tool_call(tool_name="write_file", session_id="child-1") is None  # memory lost
    ra.reload_children(ctx)
    assert ra.pre_tool_call(tool_name="write_file", session_id="child-1")["action"] == "block"
    assert ra.pre_tool_call(tool_name="terminal", task_id="sa-1")["action"] == "block"
    assert ra.pre_tool_call(tool_name="read_file", session_id="child-1") is None


def test_plugin_register_reloads_children(ctx, settings, data_dir):
    import alchemy_task
    _start_child(ctx, settings, data_dir)
    ra._research_children.clear()
    calls = []
    for name in ("register_tool", "register_hook", "register_skill", "register_command",
                 "register_system_prompt_section", "register_cli_command"):
        setattr(ctx, name, lambda *a, _n=name, **k: calls.append(_n))
    try:
        alchemy_task.register(ctx)
    except Exception:  # noqa: BLE001 - other registrations may need more host surface
        pass
    assert ra.pre_tool_call(tool_name="patch", session_id="child-1")["action"] == "block"


@pytest.mark.parametrize("tool", BLOCKED)
def test_discovery_child_is_blocked_too(tmp_path, tool):
    runner, store, pool, run = make(tmp_path, 1, {})
    runner.run(run, session_id="parent")
    verdict = runner.pre_tool_call(tool_name=tool, session_id="child-1", task_id="sa-1")
    assert verdict and verdict["action"] == "block"
    assert runner.pre_tool_call(tool_name=tool, session_id="unrelated", task_id="") is None
    assert runner.pre_tool_call(tool_name="read_file", session_id="child-1", task_id="sa-1") is None
