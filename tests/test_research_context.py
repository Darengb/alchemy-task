"""Outcome tests for the research launch context and origin session (piece 5)."""
from __future__ import annotations

import pytest

from alchemy_task import research_agent as ra
from alchemy_task import runtime
from alchemy_task.core.store import TaskStore
from test_research_agent import create, ctx  # noqa: F401 - shared fixtures


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "hermes-home"
    h.mkdir()
    monkeypatch.setattr(ra, "_hermes_home", lambda: h)
    return h


def _memory(home, memory="Prefers short replies.", user="Works on chairs."):
    (home / "memories").mkdir(exist_ok=True)
    (home / "memories" / "MEMORY.md").write_text(memory)
    (home / "memories" / "USER.md").write_text(user)


def _contexts(ctx):
    return [r.context for r in ctx.subagent_lifecycle.launched]


def test_create_launch_carries_origin_and_persists_it(ctx, settings, data_dir, home):
    doc = create(settings, data_dir)
    ra.on_task_created(runtime.Runtime(), doc, "chat-A")
    context = _contexts(ctx)[0]
    assert "chat-A" in context and "session_search" in context
    assert ctx.state.get("origin_sessions")[doc.task_id] == "chat-A"


def test_task_create_tool_saves_origin_even_without_research(ctx, settings, data_dir, home):
    from alchemy_task import task_tools
    import json
    out = json.loads(task_tools.task_create({"title": "Fix the gate", "area": "work", "due": "2026-12-01",
                                             "research": False}, session_id="chat-B"))
    task_id = out["task"]["task_id"]
    assert ctx.state.get("origin_sessions")[task_id] == "chat-B"


def test_sweep_launch_after_restart_carries_origin(ctx, settings, data_dir, home):
    doc = create(settings, data_dir)
    ra.on_task_created(runtime.Runtime(), doc, "chat-A")
    ra.subagent_start(child_session_id="child-1", child_subagent_id="sa-1")
    ra.subagent_stop(child_session_id="child-1", child_status="failed")  # requeued
    ra._runs.clear()  # plugin restart: in-memory registry gone
    ra._by_child_session.clear()
    result = ra.recover(runtime.Runtime(), limit=3, wait_seconds=0)
    assert len(result["started"]) == 1
    assert "chat-A" in _contexts(ctx)[-1]
    run = next(iter(ra._runs.values()))
    assert run["origin_session"] == "chat-A"  # the finished notice reaches the creating chat


def test_retry_launch_carries_creating_chat(ctx, settings, data_dir, home):
    doc = create(settings, data_dir)
    ra.on_task_created(runtime.Runtime(), doc, "chat-A")
    ra.subagent_start(child_session_id="child-1", child_subagent_id="sa-1")
    ra.subagent_stop(child_session_id="child-1", child_status="failed")
    ra.request_again(runtime.Runtime(), doc.task_id, origin_session="chat-C")
    context = _contexts(ctx)[-1]
    assert "chat-A" in context and "chat-C" in context
    assert ctx.state.get("origin_sessions")[doc.task_id] == "chat-A"


def test_memory_files_are_in_context(ctx, settings, data_dir, home):
    _memory(home)
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    context = _contexts(ctx)[0]
    assert "Prefers short replies." in context and "Works on chairs." in context
    assert str(home / "cron" / "output") in context


def test_missing_memory_files_do_not_fail_launch(ctx, settings, data_dir, home):
    doc = create(settings, data_dir)
    assert ra.launch(runtime.Runtime(), doc.task_id)["started"]
    assert "Order cafe chairs" in _contexts(ctx)[0]


def test_unreadable_home_does_not_fail_launch(ctx, settings, data_dir, monkeypatch):
    def boom():
        raise RuntimeError("no home")
    monkeypatch.setattr(ra, "_hermes_home", boom)
    doc = create(settings, data_dir)
    assert ra.launch(runtime.Runtime(), doc.task_id)["started"]


def test_cap_holds_with_huge_memory_and_keeps_priorities(ctx, settings, data_dir, home):
    _memory(home, memory="M" * 100_000, user="U" * 100_000)
    doc = create(settings, data_dir)
    ra.on_task_created(runtime.Runtime(), doc, "chat-A")
    context = _contexts(ctx)[0]
    assert len(context) <= ra.CONTEXT_CAP < 32_000
    assert "Order cafe chairs" in context and "chat-A" in context and "MMMM" in context


def test_related_tasks_include_done_ones(ctx, settings, data_dir, home):
    store = TaskStore(settings, data_dir)
    other = store.create(title="Return the cafe chairs", area="work", due="2026-11-01")
    store.update(other.task_id, {"status": "done"})
    store.create(title="Paint the fence", area="work", due="2026-11-01")
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    context = _contexts(ctx)[-1]
    related = context.split("Related tasks", 1)[1]
    assert "Return the cafe chairs" in related and "done" in related
    assert "Paint the fence" not in related
