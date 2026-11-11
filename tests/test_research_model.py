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


# ------------------------------------------------------------------ piece 3: stop and tell on model failure

from alchemy_task.core import research as rs  # noqa: E402
from alchemy_task.core import taskfile as tf  # noqa: E402


def _enrichment(doc):
    return rs.state(tf.parse_file(doc.path).fm)


def test_model_launch_failure_stops_tells_and_is_not_retried(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "old-model-v1", "openrouter")
    lc = ctx.subagent_lifecycle

    def launch(req):
        raise RuntimeError("Provider 'openrouter' rejected model 'old-model-v1': model not found")
    lc.launch = launch
    doc = create(settings, data_dir)
    out = ra.launch(runtime.Runtime(), doc.task_id, origin_session="chat-1")
    assert not out["started"]
    msg = out["error"]
    assert "the research model old-model-v1 could not be used" in msg
    assert 'Change it with "set my research model"' in msg and "clear it to use the main model" in msg
    st = _enrichment(doc)
    assert st["status"] == "failed" and st["attempts"] >= rs.MAX_ATTEMPTS
    body = tf.parse_file(doc.path).body
    assert "the research model old-model-v1 could not be used" in body
    notices = ctx.state.get("notices")["chat-1"]
    assert any("research model old-model-v1 could not be used" in n for n in notices)
    # the sweep does not retry it while the setting is unchanged
    assert ra.recover(runtime.Runtime(), wait_seconds=0)["queued"] == 0
    # changing the setting makes it eligible again
    lc.launch = lambda req: {"subagent_id": "sa-9", "contract_version": 1}
    _set_model(ctx, "new-model-flash", "openrouter")
    again = ra.recover(runtime.Runtime(), wait_seconds=0)
    assert again["queued"] == 1 and again["started"]


def test_non_model_launch_failure_keeps_normal_retry(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "glm-5-flash")
    ctx.subagent_lifecycle.fail = True
    doc = create(settings, data_dir)
    out = ra.launch(runtime.Runtime(), doc.task_id)
    assert not out["started"] and "research model" not in out["error"]
    assert _enrichment(doc)["status"] == "pending"


def test_main_model_failure_is_not_blamed_on_research_model(ctx, settings, data_dir):  # noqa: F811
    def launch(req):
        raise RuntimeError("model not found")
    ctx.subagent_lifecycle.launch = launch
    doc = create(settings, data_dir)
    out = ra.launch(runtime.Runtime(), doc.task_id)
    assert "research model" not in out["error"] and _enrichment(doc)["status"] == "pending"


def test_child_failing_with_model_error_stops_research(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "deepseek-v4-flash", "openrouter")
    doc = create(settings, data_dir)
    rt = runtime.Runtime()
    out = ra.launch(rt, doc.task_id, origin_session="chat-2")
    ra.subagent_start(child_session_id="child-1", child_subagent_id=out["subagent_id"])
    ra.subagent_stop(child_session_id="child-1", child_status="failed",
                     child_summary="Error code: 401 - invalid API key for provider openrouter")
    st = _enrichment(doc)
    assert st["status"] == "failed" and "deepseek-v4-flash could not be used" in st["last_error"]
    assert any("deepseek-v4-flash could not be used" in n for n in ctx.state.get("notices")["chat-2"])


def test_discovery_model_launch_error_holds_the_run(tmp_path):
    from test_discovery_runner import setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    runner.rt.settings = SimpleNamespace(research_model="old-model-v1", research_provider="nous")

    def launch(request):
        raise RuntimeError("Unknown provider 'nous' for model old-model-v1")
    pool.launch = launch
    first = runner.run(run, session_id="parent")
    again = runner.run(run, session_id="parent")
    text = json.dumps([first, again])
    assert again["status"] == "held" and "research_model" in again["holds"]
    assert "the research model old-model-v1 could not be used" in text
    assert "set my research model" in text
