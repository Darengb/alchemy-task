"""Outcome tests for research launches: worker toolsets (piece 2) and launch context (piece 5)."""
from __future__ import annotations

import pytest

from alchemy_task import jobs
from alchemy_task import research_agent as ra
from alchemy_task import runtime
from test_research_agent import create, ctx  # noqa: F401 - shared fixtures


def _streams(ctx):
    ctx.state.set("streams", {"inbox": {"name": "inbox", "sources": [
        {"name": "Mail", "scope": "work inbox", "toolsets": ["mail-reader", "mcp-mailserver"]},
        {"name": "Chat", "scope": "team", "toolsets": ["chat-reader"]}]}})
    ctx.state.set("discovery_sources", {"inbox": {
        "mail": {"name": "Mail", "scope": "work inbox", "toolsets": ["mail-thread-reader"], "approved": True},
        "stale": {"name": "Gone", "scope": "x", "toolsets": ["unapproved-reader"], "approved": True}}})
    ctx.state.set("discovery_delivery", {"inbox": {"toolsets": ["sender-toolset"]}})


def test_approved_reader_toolsets_come_from_plugin_state(ctx):
    _streams(ctx)
    readers = jobs.approved_reader_toolsets(ctx.state)
    assert readers == ["mail-reader", "chat-reader", "mail-thread-reader"]
    assert jobs.approved_reader_toolsets(None) == []


def test_launch_requests_read_toolsets_and_discovery_readers(ctx, settings, data_dir):
    _streams(ctx)
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    req = ctx.subagent_lifecycle.launched[0]
    assert req.allowed_toolsets[:4] == ("web", "file", "session_search", ra.RESEARCH_TOOLSET)
    assert set(req.allowed_toolsets[4:]) == {"mail-reader", "chat-reader", "mail-thread-reader"}
    assert not [t for t in req.allowed_toolsets if t.startswith("mcp-")]  # MCP comes by inheritance


def test_toolsets_the_host_lacks_are_recorded_not_dropped(ctx, settings, data_dir):
    _streams(ctx)
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    req = ctx.subagent_lifecycle.launched[0]
    assert "chat-reader" in req.allowed_toolsets  # still requested
    run = next(iter(ra._runs.values()))
    assert run["toolsets"]["requested"] == list(req.allowed_toolsets)
    missing = run["toolsets"]["not_available_to_worker"]
    assert {"file", "session_search", "mail-reader", "chat-reader", "mail-thread-reader"} <= set(missing)
    assert "web" not in missing and ra.RESEARCH_TOOLSET not in missing
    saved = ctx.state.get("research_runs")
    assert next(iter(saved.values()))["toolsets"]["not_available_to_worker"] == missing
    assert "not available to you" in req.context and "chat-reader" in req.context


def test_registry_failure_still_launches_and_records_requested(ctx, settings, data_dir, monkeypatch):
    def boom():
        raise RuntimeError("no registry")
    monkeypatch.setattr(ra, "_registry_toolsets", boom)
    doc = create(settings, data_dir)
    assert ra.launch(runtime.Runtime(), doc.task_id)["started"]
    run = next(iter(ra._runs.values()))
    assert run["toolsets"]["requested"][:4] == ["web", "file", "session_search", ra.RESEARCH_TOOLSET]
    assert run["toolsets"]["not_available_to_worker"] is None
