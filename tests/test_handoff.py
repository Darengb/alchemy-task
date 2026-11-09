"""Send to chat: the handoff note, route choice (messaging chat or new session), the relay and the fallback."""
from __future__ import annotations

import json
import re
import time

import pytest

from alchemy_task import handoff as ho
from alchemy_task import runtime, worksession

from test_ui_api import client, ctx, make_task  # noqa: F401  (fixtures)
from test_setup import home  # noqa: F401  (fixture)

TELEGRAM_DM = {"session_key": "agent:main:telegram:dm:555", "source": "telegram", "display_name": "Sam",
               "last_activity_at": 100.0}
TELEGRAM_GROUP = {"session_key": "agent:main:telegram:group:-1:7", "source": "telegram", "display_name": "Ops",
                  "last_activity_at": 200.0}
APP = {"id": "20261109_080859_ca6a5c", "session_key": None, "source": "gui", "title": "Hi", "last_activity_at": 300.0}
CRON = {"id": "c1", "session_key": "agent:main:local:dm:c1", "source": "cron", "last_activity_at": 400.0}


@pytest.fixture
def sessions(monkeypatch):
    rows = {"s-dm": TELEGRAM_DM, "s-group": TELEGRAM_GROUP, "s-app": APP, "s-cron": CRON}
    monkeypatch.setattr(ho, "_session_row", lambda sid: rows.get(sid))
    monkeypatch.setattr(ho, "_home_targets", lambda: [ho._chat_target(TELEGRAM_DM, "home")])
    monkeypatch.setattr(ho, "injection_allowed", lambda: True)
    monkeypatch.setattr(ho, "gateway_running", lambda: True)
    return rows


@pytest.fixture
def jobs(ctx):
    """Records cronjob_manage calls made through the plugin context (route 2)."""
    calls = []

    def dispatch(name, args):
        calls.append((name, args))
        return json.dumps({"success": True, "job_id": f"job{len(calls)}"})
    ctx.dispatch_tool = dispatch
    return calls


class Injector:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def __call__(self, content, role="user", *, session_key=None, origin=None):
        self.calls.append({"content": content, "role": role, "session_key": session_key, "origin": origin})
        return self.ok


# ------------------------------------------------------------------ the note

def test_note_explains_itself_reads_the_task_and_gives_the_reply():
    text = ho.build_text({"task_id": "abc-123", "title": "Renew the domain", "due": "2026-11-12", "area": "home",
                          "priority": "high", "summary": "The domain lapses Friday.",
                          "current_state": "Waiting on the registrar\nlogin."}, "phone")
    assert text.startswith("[Alchemy Task handoff]")
    assert "(a phone)" in text and "not from the user typing" in text and "Do not start the task" in text
    assert 'call task_find with task_id "abc-123" and include_body true' in text
    assert "Reply **go** to start." in text and "task_work_start" in text
    assert "Due: 2026-11-12 · Area: home · Priority: high" in text
    assert "Current state: Waiting on the registrar login." in text


def test_note_is_gender_neutral_and_drops_empty_fields():
    text = ho.build_text({"task_id": "x", "title": "Call the bank", "priority": "normal"}, "dashboard")
    assert not re.search(r"\b(he|him|his|she|her|hers)\b", text, re.I)
    assert "Summary:" not in text and "Current state:" not in text and "Priority" not in text


def test_new_session_note_says_it_is_a_new_chat():
    text = ho.build_text({"task_id": "x", "title": "Call the bank"}, "phone", new_session=True)
    assert "This is a new chat about one task" in text


# ------------------------------------------------------------------ which chat

def test_target_prefers_the_newest_messaging_chat_that_worked_on_the_task(ctx, sessions):
    rt = runtime.Runtime(ctx)
    for sid in ("s-dm", "s-group", "s-app", "s-cron"):  # app and cron sessions are never targets
        ho.remember_chat(rt, "t1", sid)
    t = ho.resolve_target(rt, "t1")
    assert t["session_key"] == TELEGRAM_GROUP["session_key"] and t["reason"] == "task"


def test_target_uses_a_linked_work_session(ctx, sessions):
    rt = runtime.Runtime(ctx)
    worksession._update_link(rt, "s-dm", task_id="t2", title="x", last_activity=1)
    assert ho.resolve_target(rt, "t2")["session_key"] == TELEGRAM_DM["session_key"]


def test_target_falls_back_to_the_home_channel_then_none(ctx, sessions, monkeypatch):
    rt = runtime.Runtime(ctx)
    assert ho.resolve_target(rt, "never-seen")["reason"] == "home"
    monkeypatch.setattr(ho, "_home_targets", lambda: [])
    assert ho.resolve_target(rt, "never-seen") is None


def test_tool_calls_record_the_chat(ctx, sessions):
    runtime.bind(ctx)
    tid = "3f2b8c1e-5d4a-4b6f-9e21-7a8c9d0e1f23"
    ho.post_tool_call(tool_name="task_update", args={"task_id": tid}, result="{}", session_id="s-dm")
    ho.post_tool_call(tool_name="web_search", args={"task_id": tid}, result="{}", session_id="s-group")
    other = "11111111-2222-4333-8444-555555555555"
    ho.post_tool_call(tool_name="task_create", args={}, session_id="s-group",
                      result=json.dumps({"ok": True, "task": {"task_id": other}}))
    chats = ctx.state.get("task_chats", default={})
    assert chats[tid] == ["s-dm"] and chats[other] == ["s-group"]


# ------------------------------------------------------------------ route 1: messaging chat

def test_route_one_queues_and_the_gateway_relay_injects_into_that_chat(client, ctx, sessions, jobs, monkeypatch):
    t = make_task(client, "Book the venue")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "phone"}).json()
    assert out["ok"] and out["mode"] == "chat"
    h = out["handoff"]
    assert h["route"] == "chat" and h["state"] == "pending"
    assert h["target"] == {"platform": "telegram", "chat_name": "Sam", "reason": "home"}
    assert not jobs

    inject = Injector()
    ctx.inject_message = inject
    rt = runtime.Runtime(ctx)
    monkeypatch.setattr(ho, "in_gateway_process", lambda: False)
    assert ho.relay_once(rt) == [] and not inject.calls  # never outside the gateway's process
    monkeypatch.setattr(ho, "in_gateway_process", lambda: True)
    assert ho.relay_once(rt) == [h["id"]]
    assert inject.calls[0]["session_key"] == TELEGRAM_DM["session_key"] and inject.calls[0]["role"] == "user"
    assert "Book the venue" in inject.calls[0]["content"] and "(a phone)" in inject.calls[0]["content"]
    assert ho.relay_once(rt) == []  # sent once
    assert client.get(f"/handoffs/{h['id']}").json()["handoff"]["state"] == "sent"


# ------------------------------------------------------------------ route 2: new session

@pytest.mark.parametrize("why", ["no_gateway", "no_permission", "no_chat"])
def test_route_two_starts_a_one_time_session_when_route_one_cannot_work(client, ctx, sessions, jobs, monkeypatch, why):
    if why == "no_gateway":
        monkeypatch.setattr(ho, "gateway_running", lambda: False)
    elif why == "no_permission":
        monkeypatch.setattr(ho, "injection_allowed", lambda: False)
    else:
        monkeypatch.setattr(ho, "_home_targets", lambda: [])
    t = make_task(client, "Draft the agenda")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "phone"}).json()["handoff"]
    assert h["route"] == "session" and h["state"] == "started" and h["reason"] == why
    (name, args), = jobs
    assert name == "cronjob_manage" and args["action"] == "create" and args["name"] == "Draft the agenda"
    assert args["repeat"] == 1 and args["deliver"] == "local"
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$", args["schedule"])
    assert "This is a new chat about one task" in args["prompt"] and t["task_id"] in args["prompt"]
    assert client.get(f"/handoffs/{h['id']}").json()["handoff"]["route"] == "session"
    assert not list((runtime.Runtime(ctx).data_dir / "handoffs").glob(f"{h['id']}.json"))  # nothing queued


def test_a_silent_gateway_falls_back_to_a_new_session(client, ctx, sessions, jobs):
    t = make_task(client, "Pay the invoice")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={}).json()["handoff"]
    rt = runtime.Runtime(ctx)
    early = ho.status(rt, h["id"], now=time.time() + 2)
    assert early["route"] == "chat" and early["state"] == "pending" and not jobs
    late = ho.status(rt, h["id"], now=time.time() + ho.FALLBACK_SECONDS + 1)
    assert late["route"] == "session" and late["state"] == "started" and late["reason"] == "gateway_silent"
    assert len(jobs) == 1 and jobs[0][1]["name"] == "Pay the invoice"
    ctx.inject_message = Injector()
    assert ho.relay_once(rt) == [] and not ctx.inject_message.calls  # the gateway never also sends it
    assert ho.status(rt, h["id"])["route"] == "session" and len(jobs) == 1  # and it is not started twice


def test_a_refused_injection_is_retried_then_falls_back(client, ctx, sessions, jobs, monkeypatch):
    t = make_task(client, "Order the banners")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={}).json()["handoff"]
    ctx.inject_message = Injector(ok=False)
    monkeypatch.setattr(ho, "in_gateway_process", lambda: True)
    rt = runtime.Runtime(ctx)
    now = time.time()
    ho.relay_once(rt, now)
    ho.relay_once(rt, now + 1)  # waits before retrying
    ho.relay_once(rt, now + 4)
    assert len(ctx.inject_message.calls) == 2
    assert ho.status(rt, h["id"], now=now + ho.FALLBACK_SECONDS + 1)["route"] == "session" and len(jobs) == 1


def test_desktop_gets_the_note_without_queueing(client, sessions, jobs, ctx):
    t = make_task(client, "Draft the agenda")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "desktop"}).json()
    assert out["mode"] == "desktop" and "Draft the agenda" in out["text"] and "(the desktop app)" in out["text"]
    assert not jobs and not list((runtime.Runtime(ctx).data_dir / "handoffs").glob("*.json"))


def test_the_relay_thread_uses_the_folder_captured_at_load(client, ctx, sessions, monkeypatch):
    # A thread does not inherit the profile Hermes selected when the plugin loaded, so the relay is handed
    # its profile's folder and only needs the plugin context.
    t = make_task(client, "Renew the lease")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={}).json()["handoff"]
    ctx.inject_message = Injector()
    monkeypatch.setattr(ho, "in_gateway_process", lambda: True)
    data_dir = runtime.Runtime(ctx).data_dir
    assert ho.relay_once(ho._RelayRuntime(ctx), data_dir=data_dir) == [h["id"]]
    assert ho.relay_once(ho._RelayRuntime(ctx), data_dir=data_dir / "elsewhere") == []


def test_the_background_fallback_works_with_no_screen_asking(client, ctx, sessions, jobs):
    t = make_task(client, "Call the accountant")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={}).json()["handoff"]
    rt = runtime.Runtime(ctx)
    assert ho.fallback_once(rt, rt.data_dir, now=time.time() + 2) == [] and not jobs  # not due yet
    assert ho.fallback_once(rt, rt.data_dir, now=time.time() + ho.FALLBACK_SECONDS + 1) == [h["id"]]
    assert len(jobs) == 1 and jobs[0][1]["name"] == "Call the accountant"
    assert ho.fallback_once(rt, rt.data_dir, now=time.time() + 60) == [] and len(jobs) == 1  # once only
    st = client.get(f"/handoffs/{h['id']}").json()["handoff"]
    assert st["route"] == "session" and st["reason"] == "gateway_silent"


def test_the_worker_thread_keeps_the_profile_selected_when_the_plugin_loaded(tmp_path, monkeypatch):
    # Hermes marks the selected profile in a context variable; a plain thread would start without it.
    import contextvars
    import threading
    profile = contextvars.ContextVar("profile", default="launch profile")
    seen, ready = [], threading.Event()

    def fake_loop(ctx, data_dir, stop):
        seen.append(profile.get())
        ready.set()
    monkeypatch.delenv("ALCHEMY_TASK_NO_RELAY", raising=False)
    monkeypatch.setattr(ho, "_loop", fake_loop)
    token = profile.set("twf-ui")
    try:
        ho.ensure_relay(object(), tmp_path)
    finally:
        profile.reset(token)
    assert ready.wait(5) and seen == ["twf-ui"]
    ho.stop_relay()
