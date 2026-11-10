"""Plugin-side research flow with a fake Hermes context (launch, submit, budget, stop, notice, recovery)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from alchemy_task import research_agent as ra
from alchemy_task import runtime
from alchemy_task.core import research as rs
from alchemy_task.core import taskfile as tf
from alchemy_task.core.store import TaskStore


class FakeState:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._d = {}

    def get(self, key, default=None):
        return json.loads(json.dumps(self._d.get(key, default)))

    def set(self, key, value):
        self._d[key] = json.loads(json.dumps(value))


class FakeLifecycle:
    def __init__(self, fail=False):
        self.launched, self.fail, self.n = [], fail, 0

    def launch(self, req):
        if self.fail:
            raise RuntimeError("No active Hermes parent session is available")
        self.n += 1
        self.launched.append(req)
        return {"subagent_id": f"sa-{self.n}", "contract_version": 1}

    def wait(self, handle, timeout_seconds=None):
        return "SUCCEEDED"


class FakeCtx:
    def __init__(self, settings, data_dir, lifecycle):
        self._s = dataclasses.asdict(settings)
        self.state = FakeState(data_dir)
        self.subagent_lifecycle = lifecycle

    def get_config(self, key, default=None):
        return self._s.get(key, default)

    def dispatch_tool(self, name, args):
        return json.dumps({"tool": name, "args": args})


@pytest.fixture
def ctx(settings, data_dir, monkeypatch):
    monkeypatch.setattr(ra, "_make_request", lambda **kw: type("Req", (), kw)())
    monkeypatch.setattr(ra, "_registry_toolsets", lambda: {
        "web": {"available": True, "tools": ["web_search", "web_extract"]},
        "mcp-notion": {"available": True, "tools": ["notion_search"]},
        ra.RESEARCH_TOOLSET: {"available": True, "tools": ["research_submit"]}})
    c = FakeCtx(settings, data_dir, FakeLifecycle())
    runtime.bind(c)
    ra._runs.clear()
    ra._by_child_session.clear()
    yield c
    runtime.bind(None)


PAYLOAD = {"recommended_approach": ["Do it with the browser."], "execution": "autonomous",
           "access_plan": [{"need": "Browser", "status": "available", "via": "browser_exec"}],
           "sources": [{"title": "x", "url": "https://example.com", "relevance": "y"}]}


def create(settings, data_dir, title="Order cafe chairs"):
    return TaskStore(settings, data_dir).create(title=title, area="work", due="2026-12-01")


def test_launch_submit_notice(ctx, settings, data_dir):
    doc = create(settings, data_dir)
    rt = runtime.Runtime()
    out = ra.launch(rt, doc.task_id, origin_session="chat-1")
    req = ctx.subagent_lifecycle.launched[0]
    assert out["started"] and req.allowed_toolsets[:4] == ("web", "file", "session_search", ra.RESEARCH_TOOLSET)
    assert out["run_id"] in req.goal and "Order cafe chairs" in req.context
    assert tf.parse_file(doc.path).fm["enrichment"]["status"] == "running"
    # wrong agent cannot submit someone else's run
    bad = json.loads(ra.t_submit({"run_id": out["run_id"], **PAYLOAD}, task_id="sa-99"))
    assert not bad["ok"]
    res = json.loads(ra.t_submit({"run_id": out["run_id"], **PAYLOAD}, task_id="sa-1"))
    assert res["ok"] and res["git"]["pushed"], res
    final = tf.parse_file(doc.path)
    assert final.fm["enrichment"]["status"] == "complete" and rs.START in final.body
    assert "Research added" in final.body.split(rs.START)[0]  # log line sits in Log, above the dossier
    note = ra.pre_llm_call(session_id="chat-1")
    assert note and "Research finished" in note["context"]
    assert ra.pre_llm_call(session_id="chat-1") is None  # delivered once
    # a second submit for the same run is rejected (claim released)
    assert not json.loads(ra.t_submit({"run_id": out["run_id"], **PAYLOAD}, task_id="sa-1"))["ok"]


def test_budget_blocks_everything_but_submit(ctx, settings, data_dir):
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    for _ in range(ra.CALL_BUDGET):
        assert ra.pre_tool_call(tool_name="web_search", task_id="sa-1", session_id="child-1") is None
    blocked = ra.pre_tool_call(tool_name="web_search", task_id="sa-1", session_id="child-1")
    assert blocked["action"] == "block"
    assert ra.pre_tool_call(tool_name="research_submit", task_id="sa-1") is None
    assert ra.pre_tool_call(tool_name="web_search", task_id="main-session") is None  # other agents untouched


def test_stop_without_submit_requeues_then_fails(ctx, settings, data_dir):
    doc = create(settings, data_dir)
    for attempt in (1, 2, 3):
        ra.launch(runtime.Runtime(), doc.task_id)
        sid = f"sa-{attempt}"
        ra.pre_tool_call(tool_name="web_search", task_id=sid, session_id=f"child-{attempt}")
        ra.subagent_stop(child_session_id=f"child-{attempt}", child_status="failed")
        st = tf.parse_file(doc.path).fm["enrichment"]
        assert st["status"] == ("failed" if attempt == 3 else "pending")
    assert "Research failed after 3 attempts" in tf.parse_file(doc.path).body


def test_child_dying_before_first_tool_call_is_requeued(ctx, settings, data_dir):
    doc = create(settings, data_dir)
    ra.subagent_start(child_session_id="child-x", child_subagent_id="sa-1")  # fires before launch returns
    ra.launch(runtime.Runtime(), doc.task_id)
    ra.subagent_stop(child_session_id="child-x", child_status="error")
    assert tf.parse_file(doc.path).fm["enrichment"]["status"] == "pending"


def test_request_again_refuses_closed_task_without_writing(ctx, settings, data_dir):
    store = TaskStore(settings, data_dir)
    doc = create(settings, data_dir)
    store.update(doc.task_id, {"status": "done"})
    before = doc.path.read_bytes()
    with pytest.raises(rs.ResearchError):
        ra.request_again(runtime.Runtime(), doc.task_id)
    assert doc.path.read_bytes() == before


def test_launch_failure_leaves_task_queued_and_recover_runs_queue(ctx, settings, data_dir):
    ctx.subagent_lifecycle.fail = True
    doc = create(settings, data_dir)
    out = ra.launch(runtime.Runtime(), doc.task_id)
    assert not out["started"]
    st = tf.parse_file(doc.path).fm["enrichment"]
    assert st["status"] == "pending" and "could not start" in st["last_error"]
    ctx.subagent_lifecycle.fail = False
    result = ra.recover(runtime.Runtime(), limit=3, wait_seconds=0)
    assert result["queued"] == 1 and len(result["started"]) == 1


def test_capabilities_and_skill_tools(ctx):
    caps = json.loads(ra.t_capabilities({}))
    assert caps["ok"] and [t["toolset"] for t in caps["toolsets"]] == ["web"]
    assert caps["mcp_servers"][0]["server"] == "notion"
    again = json.loads(ra.t_capabilities({}))
    assert again["cached_minutes_ago"] == 0 and "toolsets" in again
    assert json.loads(ra.t_skill_view({"name": "x"}))["tool"] == "skill_view"
