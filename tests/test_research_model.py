"""Research model setting: config, setup save, launch, failure handling."""
from __future__ import annotations

import json

from alchemy_task.core.config import Settings

from test_setup import call, home, make_ctx  # noqa: F401


def test_config_round_trip_and_defaults():
    s = Settings.load(lambda k, d: {}.get(k, d))
    assert s.research_model == "" and s.research_provider == ""
    s = Settings.load(lambda k, d: {"research_model": "  deepseek/deepseek-v4-flash ",
                                     "research_provider": " openrouter "}.get(k, d))
    assert s.research_model == "deepseek/deepseek-v4-flash" and s.research_provider == "openrouter"


def test_setup_save_status_and_clear(home, workspace, data_dir):  # noqa: F811
    ctx = make_ctx(data_dir, workspace_root=str(workspace))
    st = call(action="status")
    assert st["receipt"]["research"]["model"] is None
    assert "Research model: main model" in st["text"]
    out = call(action="save", research_model=" glm-5-flash ", research_provider="openrouter")
    assert out["ok"], out
    assert ctx._s["research_model"] == "glm-5-flash" and ctx._s["research_provider"] == "openrouter"
    st = call(action="status")
    assert st["receipt"]["research"]["model"] == "glm-5-flash"
    assert st["receipt"]["research"]["provider"] == "openrouter"
    assert "Research model: glm-5-flash (openrouter)" in st["text"]
    out = call(action="save", research_model="", research_provider="")
    assert out["ok"] and ctx._s["research_model"] == "" and ctx._s["research_provider"] == ""
    assert "Research model: main model" in call(action="status")["text"]
    bad = call(action="save", research_model="x" * 201)
    assert not bad.get("ok") and "research_model" in bad["message"]


# ------------------------------------------------------------------ piece 2: launches carry the model

import dataclasses  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from alchemy_task import research_agent as ra  # noqa: E402
from alchemy_task import runtime  # noqa: E402
from test_research_agent import create, ctx  # noqa: E402,F401


def _set_model(ctx, model, provider=""):  # noqa: F811
    ctx._s["research_model"] = model
    ctx._s["research_provider"] = provider


def test_task_research_launch_carries_model_and_provider(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "deepseek-v4-flash", "openrouter")
    doc = create(settings, data_dir)
    assert ra.launch(runtime.Runtime(), doc.task_id)["started"]
    req = ctx.subagent_lifecycle.launched[0]
    assert req.model == "deepseek-v4-flash" and req.provider == "openrouter"


def test_task_research_launch_omits_model_when_empty(ctx, settings, data_dir):  # noqa: F811
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    req = ctx.subagent_lifecycle.launched[0]
    assert not hasattr(req, "model") and not hasattr(req, "provider")


def test_model_only_omits_provider(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "qwen3.6-plus")
    doc = create(settings, data_dir)
    ra.launch(runtime.Runtime(), doc.task_id)
    req = ctx.subagent_lifecycle.launched[0]
    assert req.model == "qwen3.6-plus" and not hasattr(req, "provider")


def test_toolset_fallback_launch_keeps_the_research_model(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "glm-5-flash", "zai")
    lc = ctx.subagent_lifecycle
    real = lc.launch
    calls = []

    def launch(req):
        calls.append(req)
        if len(calls) == 1:
            raise RuntimeError("Unknown toolsets requested: file")
        return real(req)
    lc.launch = launch
    doc = create(settings, data_dir)
    assert ra.launch(runtime.Runtime(), doc.task_id)["started"]
    assert len(calls) == 2 and all(r.model == "glm-5-flash" and r.provider == "zai" for r in calls)


def _discovery_request(tmp_path, settings_obj):
    from test_discovery_runner import setup_runner
    runner, store, _, run = setup_runner(tmp_path, count=1)
    runner.rt.settings = settings_obj
    cid = store.get_run(run)["candidates"][0]["candidate_id"]
    attempt = store.reserve_attempt(run, cid, owner_session="parent")
    return runner._bootstrap(run, attempt)


def test_discovery_child_launch_carries_model(tmp_path):
    req = _discovery_request(tmp_path, SimpleNamespace(research_model="deepseek-v4-flash",
                                                       research_provider="openrouter"))
    assert req["model"] == "deepseek-v4-flash" and req["provider"] == "openrouter"


def test_discovery_child_launch_omits_model_when_empty(tmp_path):
    req = _discovery_request(tmp_path, SimpleNamespace(research_model="", research_provider=""))
    assert "model" not in req and "provider" not in req
