"""Outcome tests: the research sweep job enables the worker's read toolsets (piece 6). Fake cron only."""
from __future__ import annotations

import json

from alchemy_task import jobs
from alchemy_task import setup_flow as sf
from test_setup import home, make_ctx  # noqa: F401 - shared fixtures and fake cron

STREAMS = {"inbox": {"name": "inbox", "sources": [
    {"name": "Mail", "scope": "work inbox", "toolsets": ["mail-reader", "mcp-mailserver"]}]}}


def _sweep(ctx):
    return next(v for v in ctx.cron.values() if v["name"] == jobs.job_name("research-sweep"))


def _create(ctx, monkeypatch):
    monkeypatch.setattr(sf, "_timezone_state", lambda rt: {"timezone": "America/New_York", "likely_unset": False})
    return sf.jobs_create(sf.Runtime(), user_approved=True, session_id="setup-chat")


def test_sweep_job_enables_read_toolsets(home, data_dir, monkeypatch):
    ctx = make_ctx(data_dir)
    made = _create(ctx, monkeypatch)
    assert [r["status"] for r in made["results"]] == ["created", "created"]
    enabled = _sweep(ctx)["enabled_toolsets"]
    assert {"alchemy-task-sweep", "alchemy-task-research", "web", "file", "session_search"} <= set(enabled)


def test_sweep_job_adds_approved_readers_and_readback_accepts_it(home, data_dir, monkeypatch):
    ctx = make_ctx(data_dir)
    ctx.state.set("streams", STREAMS)
    _create(ctx, monkeypatch)
    enabled = _sweep(ctx)["enabled_toolsets"]
    # the job is the workers' parent: it must hold every reader, MCP included, so children can inherit them
    assert "mail-reader" in enabled and "mcp-mailserver" in enabled
    assert enabled == jobs.sweep_toolsets(ctx.state)
    again = _create(ctx, monkeypatch)
    assert [r["status"] for r in again["results"]] == ["already created"] * 2
    assert sf.jobs_preview(sf.Runtime())["approval_needed"] is False


def test_readback_mismatch_is_not_reported_as_created(home, data_dir, monkeypatch):
    ctx = make_ctx(data_dir)
    real = ctx.dispatch_tool

    def lossy(name, args):
        out = real(name, args)
        if args["action"] == "create" and "enabled_toolsets" in args:
            jid = json.loads(out)["job_id"]
            ctx.cron[jid]["enabled_toolsets"] = ["web"]  # host silently dropped toolsets
        return out
    ctx.dispatch_tool = lossy
    made = _create(ctx, monkeypatch)
    sweep = next(r for r in made["results"] if r["job"] == "research-sweep")
    assert sweep["status"] == "failed" and "toolsets" in sweep["error"]


def test_stream_change_reverifies_sweep_job(home, data_dir, monkeypatch):
    ctx = make_ctx(data_dir)
    _create(ctx, monkeypatch)
    assert "mail-reader" not in _sweep(ctx)["enabled_toolsets"]
    ctx.state.set("streams", STREAMS)
    assert sf.jobs_preview(sf.Runtime())["approval_needed"] is True  # readers changed: job is out of date
    out = sf.reconcile_sweep_job(sf.Runtime())
    assert out["state"] == "verified" and "mail-reader" in _sweep(ctx)["enabled_toolsets"]
    assert sf.jobs_preview(sf.Runtime())["approval_needed"] is False
    assert sf.reconcile_sweep_job(sf.Runtime())["state"] == "verified"


def test_reconcile_without_sweep_job_is_a_no_op(home, data_dir):
    ctx = make_ctx(data_dir)
    assert sf.reconcile_sweep_job(sf.Runtime())["state"] == "not_configured"
    assert ctx.cron == {}
