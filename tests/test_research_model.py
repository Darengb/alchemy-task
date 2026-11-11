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


# ------------------------------------------------------------------ review fixes

def test_sweep_wake_sees_blocked_task_once_the_setting_changes(ctx, settings, data_dir):  # noqa: F811
    from alchemy_task.core import precheck
    _set_model(ctx, "old-model-v1", "openrouter")

    def launch(req):
        raise RuntimeError("Provider 'openrouter' rejected model 'old-model-v1': model not found")
    ctx.subagent_lifecycle.launch = launch
    doc = create(settings, data_dir)
    assert not ra.launch(runtime.Runtime(), doc.task_id)["started"]
    old = dataclasses.replace(settings, research_model="old-model-v1", research_provider="openrouter")
    assert precheck.research_wake(old, str(data_dir)) == {"wakeAgent": False}
    new = dataclasses.replace(settings, research_model="new-model-flash", research_provider="openrouter")
    woke = precheck.research_wake(new, str(data_dir))
    assert woke["wakeAgent"] and woke["waiting"] == 1
    ctx.subagent_lifecycle.launch = lambda req: {"subagent_id": "sa-9", "contract_version": 1}
    _set_model(ctx, "new-model-flash", "openrouter")
    assert ra.recover(runtime.Runtime(), wait_seconds=0)["started"]


def test_model_key_lives_in_core():
    s = SimpleNamespace(research_model="m", research_provider="p")
    assert rs.model_route(s) == {"model": "m", "provider": "p"} and rs.model_key(s) == "m|p"
    assert rs.model_key(SimpleNamespace(research_model="", research_provider="")) == "|"


ROUTED = SimpleNamespace(research_model="glm-5-flash", research_provider="openrouter")


@pytest.mark.parametrize("text", [
    "model not found", "Unknown model glm-5-flash", "Unsupported model for this endpoint",
    "model glm-5-flash does not exist", "Invalid API key", "Error code: 401", "401 Unauthorized",
    "no credentials for provider openrouter", "No API key configured", "Insufficient credits",
    "insufficient quota", "billing hard limit reached"])
def test_classifier_matches_model_failures(text):
    assert ra.model_failure(text, ROUTED)


@pytest.mark.parametrize("text", [
    "rate limit exceeded for model glm-5-flash", "Error code: 429 for model glm-5-flash invalid",
    "Connection error talking to provider openrouter, model not found", "request timed out for model x",
    "The author compared pricing model options from each provider", "authority approved the budget",
    "403 forbidden on the vendor site", "quota of seats per provider", "the model and provider are fine"])
def test_classifier_ignores_ordinary_failures(text):
    assert ra.model_failure(text, ROUTED) is None


@pytest.mark.parametrize("status", ["interrupted", "completed", "timeout", ""])
def test_child_stop_classifies_only_failed_statuses(ctx, settings, data_dir, status):  # noqa: F811
    _set_model(ctx, "deepseek-v4-flash", "openrouter")
    doc = create(settings, data_dir)
    out = ra.launch(runtime.Runtime(), doc.task_id)
    ra.subagent_start(child_session_id="child-1", child_subagent_id=out["subagent_id"])
    ra.subagent_stop(child_session_id="child-1", child_status=status,
                     child_summary="Notes so far: invalid API key handling and the unknown model pricing model")
    st = _enrichment(doc)
    assert "could not be used" not in str(st.get("last_error")) and "blocked_model" not in st


def test_child_error_status_is_classified(ctx, settings, data_dir):  # noqa: F811
    _set_model(ctx, "deepseek-v4-flash", "openrouter")
    doc = create(settings, data_dir)
    out = ra.launch(runtime.Runtime(), doc.task_id)
    ra.subagent_start(child_session_id="child-1", child_subagent_id=out["subagent_id"])
    ra.subagent_stop(child_session_id="child-1", child_status="error", child_summary="Unknown model deepseek-v4-flash")
    assert _enrichment(doc)["status"] == "failed"


def _auto_submit(runner, store, pool, run):
    from test_discovery_runner import callback_all
    original, submitted = pool.status, set()

    def status(h):
        if not pool.fail and h["subagent_id"] not in submitted:
            submitted.add(h["subagent_id"])
            callback_all(runner, store, pool, run, h)
        return original(h)
    pool.status = status


def _budget_units(tmp_path):
    files = list((tmp_path / "discovery").rglob("budgets/*.json"))
    return sum(len(json.loads(f.read_text())["charged"]) for f in files)


def test_discovery_model_launch_error_relaunches_after_release(tmp_path):
    from test_discovery_runner import drive, setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    runner.rt.settings = SimpleNamespace(research_model="old-model-v1", research_provider="nous")
    real = pool.launch

    def broken(request):
        raise RuntimeError("Unknown provider 'nous' for model old-model-v1")
    pool.launch = broken
    first = runner.run(run, session_id="parent")
    # the call that set the hold reports it
    assert first["status"] == "held" and "research_model" in first["holds"]
    assert "old-model-v1 could not be used" in first["research_model_error"]
    attempts = list(store.get_run(run)["attempts"].values())
    assert not any(a["fenced"] for a in attempts)
    runner.rt.settings = SimpleNamespace(research_model="new-model-flash", research_provider="openrouter")
    pool.launch = real
    _auto_submit(runner, store, pool, run)
    runner.release_hold(run, "user changed the research model", session_id="parent")
    drive(runner, store, run)
    assert len(pool.requests) == 1 and pool.requests[0]["model"] == "new-model-flash"
    cid = store.get_run(run)["candidates"][0]["candidate_id"]
    assert store.accepted_bundle(run, cid)
    joined = runner.join(run, session_id="parent")
    assert joined["joined"] and not joined["degraded"]
    assert _budget_units(tmp_path) == 1


def test_discovery_child_model_failure_holds_without_retry(tmp_path):
    from test_discovery_runner import drive, setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    runner.rt.settings = SimpleNamespace(research_model="old-model-v1", research_provider="nous")
    pool.fail = True
    real_result = pool.result
    pool.result = lambda h: {**real_result(h), "summary": "Error: unknown model old-model-v1"}
    reports = [runner.run(run, session_id="parent") for _ in range(3)]
    assert len(pool.requests) == 1  # not retried on the same model
    held = next(r for r in reports if r["status"] == "held")
    assert "old-model-v1 could not be used" in held["research_model_error"]
    assert "set my research model" in held["next_action"]
    pool.fail = False
    pool.result = real_result
    runner.rt.settings = SimpleNamespace(research_model="new-model-flash", research_provider="")
    _auto_submit(runner, store, pool, run)
    runner.release_hold(run, "user changed the research model", session_id="parent")
    drive(runner, store, run)
    assert len(pool.requests) == 2 and pool.requests[1]["model"] == "new-model-flash"
    cid = store.get_run(run)["candidates"][0]["candidate_id"]
    assert store.accepted_bundle(run, cid)


def test_discovery_ordinary_child_failure_still_retries(tmp_path):
    from test_discovery_runner import setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    runner.rt.settings = SimpleNamespace(research_model="glm-5-flash", research_provider="")
    pool.fail = True
    reports = [runner.run(run, session_id="parent") for _ in range(4)]
    assert len(pool.requests) == 2 and all(r["status"] != "held" for r in reports)


def test_model_hold_message_keeps_reconcile_step_when_other_holds_exist(tmp_path):
    from test_discovery_runner import setup_runner
    runner, store, pool, run = setup_runner(tmp_path, count=1)
    with runner._state(run) as state:
        state["holds"] = ["research_model", "interrupted"]
        state["research_model_error"] = "the research model x could not be used: boom."
    out = runner.run(run, session_id="parent")
    assert out["status"] == "held" and "could not be used" in out["next_action"]
    assert "discovery_recover" in out["next_action"]
    with runner._state(run) as state:
        state["holds"] = ["research_model"]
    assert "discovery_recover" not in runner.run(run, session_id="parent")["next_action"]


def test_setup_save_caps_provider_and_requires_a_model(home, workspace, data_dir):  # noqa: F811
    ctx = make_ctx(data_dir, workspace_root=str(workspace))
    bad = call(action="save", research_model="m", research_provider="p" * 65)
    assert not bad.get("ok") and "research_provider" in bad["message"] and "64" in bad["message"]
    assert call(action="save", research_model="m", research_provider="p" * 64)["ok"]
    call(action="save", research_model="", research_provider="")
    alone = call(action="save", research_provider="openrouter")
    assert not alone.get("ok") and "needs a research model" in alone["message"]
    assert ctx._s.get("research_provider", "") == ""
    assert call(action="save", research_model="glm-5-flash", research_provider="openrouter")["ok"]
    dropped = call(action="save", research_model="")
    assert not dropped.get("ok") and ctx._s["research_model"] == "glm-5-flash"
    assert call(action="save", research_model="", research_provider="")["ok"]


def test_skill_says_a_provider_needs_a_model():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "skills/tasks/SKILL.md").read_text()
    section = text[text.index("## Research model"):]
    assert "A provider needs a model" in section and "\u2014" not in section
