"""Start in chat: the handoff note, which chat the reply goes to, and the one-time job that writes it."""
from __future__ import annotations

import json
import re

import pytest

from alchemy_task import handoff as ho
from alchemy_task import runtime

from test_ui_api import client, ctx, make_task  # noqa: F401  (fixtures)
from test_setup import home  # noqa: F401  (fixture)

# host_origin rows by session id: a Telegram topic, a Slack channel, and an app chat (never deliverable).
ORIGINS = {
    "s-setup": {"source": "telegram", "chat_id": "-100", "thread_id": "7", "chat_name": "Hermes Group"},
    "s-slack": {"source": "slack", "chat_id": "C1", "thread_id": "", "chat_name": "ops"},
    "s-app": {"source": "desktop", "chat_id": "x", "thread_id": "", "chat_name": ""},
}


@pytest.fixture
def origins(monkeypatch):
    rows = dict(ORIGINS)
    monkeypatch.setattr(ho, "_host_origin", lambda sid: rows.get(sid))
    return rows


@pytest.fixture
def jobs(ctx):
    """Records cronjob_manage calls made through the plugin context."""
    calls = []

    def dispatch(name, args):
        calls.append((name, args))
        return json.dumps({"success": True, "job_id": f"job{len(calls)}"})
    ctx.dispatch_tool = dispatch
    return calls


def stream(ctx, name, area, deliver, origin_session="s-app", created=1.0):
    streams = ctx.state.get("streams", default={}) or {}
    streams[name] = {"name": name, "areas": [area], "deliver": deliver, "origin_session": origin_session,
                     "job_id": f"j-{name}", "created_at": created}
    ctx.state.set("streams", streams)


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


def test_a_delivered_reply_carries_the_task_id_so_the_receiving_chat_can_start_it():
    text = ho.build_text({"task_id": "x-1", "title": "Call the bank"}, "phone", new_session=True,
                         delivered_to="Telegram (Hermes Group)")
    assert "delivered to the user's chat (Telegram (Hermes Group))" in text
    assert 'Reply **go** to start.\nTask ID: x-1"' in text
    local = ho.build_text({"task_id": "x-1", "title": "Call the bank"}, "phone", new_session=True)
    assert "This is a new chat about one task" in local and 'Task ID: x-1"' not in local


# ------------------------------------------------------------------ which chat

def test_the_task_areas_discovery_chat_wins(ctx, origins):
    rt = runtime.Runtime(ctx)
    ho.remember_setup_chat(rt, "s-setup")
    stream(ctx, "work", "work", "slack:C9")
    stream(ctx, "home", "home", "origin", origin_session="s-slack")
    assert ho.delivery_target(rt, "work")["deliver"] == "slack:C9"
    assert ho.delivery_target(rt, "home")["deliver"] == "slack:C1"  # deliver=origin: the stream's own chat


def test_an_area_without_discovery_uses_the_setup_chat(ctx, origins):
    rt = runtime.Runtime(ctx)
    stream(ctx, "work", "work", "slack:C9")
    ho.remember_setup_chat(rt, "s-setup")
    t = ho.delivery_target(rt, "home")
    assert t["deliver"] == "telegram:-100:7" and ho.label(t) == "Telegram (Hermes Group)"


def test_the_setup_chat_survives_its_session_being_pruned(ctx, origins):
    rt = runtime.Runtime(ctx)
    ho.remember_setup_chat(rt, "s-setup")
    origins.clear()
    assert ho.delivery_target(rt, "home")["deliver"] == "telegram:-100:7"


def test_older_installs_resolve_the_recorded_setup_session_once(ctx, origins):
    rt = runtime.Runtime(ctx)
    ctx.state.set("jobs", {"sweep": {"job_id": "j1", "origin_session": "s-setup"}})
    assert ho.delivery_target(rt, "home")["deliver"] == "telegram:-100:7"
    assert ctx.state.get(ho.SETUP_CHAT_KEY)["deliver"] == "telegram:-100:7"


def test_app_setup_chats_are_not_delivery_targets(ctx, origins):
    rt = runtime.Runtime(ctx)
    ho.remember_setup_chat(rt, "s-app")
    stream(ctx, "home", "home", "origin", origin_session="s-app")
    assert ho.delivery_target(rt, "home") is None


# ------------------------------------------------------------------ the request

def test_dashboard_press_creates_a_job_delivered_to_the_chat(client, ctx, origins, jobs):
    runtime.Runtime(ctx)
    ho.remember_setup_chat(runtime.Runtime(ctx), "s-setup")
    t = make_task(client, "Draft the agenda", area="home")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "phone"}).json()
    h = out["handoff"]
    assert out["mode"] == "chat" and h["route"] == "session" and h["state"] == "started"
    assert h["target"]["label"] == "Telegram (Hermes Group)"
    (name, args), = jobs
    assert name == "cronjob_manage" and args["action"] == "create" and args["name"] == "Draft the agenda"
    assert args["repeat"] == 1 and args["deliver"] == "telegram:-100:7" and args["attach_to_session"] is True
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$", args["schedule"])
    assert t["task_id"] in args["prompt"] and "Telegram (Hermes Group)" in args["prompt"]
    assert client.get(f"/handoffs/{h['id']}").json()["handoff"]["target"]["label"] == "Telegram (Hermes Group)"


def test_without_a_messaging_chat_the_reply_stays_in_the_app(client, ctx, origins, jobs):
    t = make_task(client, "Draft the agenda")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={}).json()["handoff"]
    assert h["target"] is None
    (_, args), = jobs
    assert args["deliver"] == "local" and "attach_to_session" not in args
    assert "This is a new chat about one task" in args["prompt"]


def test_desktop_gets_the_note_without_a_job(client, origins, jobs):
    t = make_task(client, "Draft the agenda")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "desktop"}).json()
    assert out["mode"] == "desktop" and "Draft the agenda" in out["text"] and "(the desktop app)" in out["text"]
    assert not jobs
