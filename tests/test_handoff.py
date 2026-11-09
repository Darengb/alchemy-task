"""Send to chat: the handoff note, which chat it goes to, the dashboard route and the gateway relay."""
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
DESKTOP = {"session_key": "ses_abc", "source": "desktop", "last_activity_at": 300.0}


@pytest.fixture
def sessions(monkeypatch):
    rows = {"s-dm": TELEGRAM_DM, "s-group": TELEGRAM_GROUP, "s-desk": DESKTOP}
    monkeypatch.setattr(ho, "_session_row", lambda sid: rows.get(sid))
    monkeypatch.setattr(ho, "_home_targets", lambda: [ho._chat_target(TELEGRAM_DM, "home")])
    monkeypatch.setattr(ho, "injection_allowed", lambda: True)
    return rows


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


# ------------------------------------------------------------------ which chat

def test_target_prefers_the_newest_chat_that_worked_on_the_task(ctx, sessions):
    rt = runtime.Runtime(ctx)
    ho.remember_chat(rt, "t1", "s-dm")
    ho.remember_chat(rt, "t1", "s-group")
    ho.remember_chat(rt, "t1", "s-desk")  # local sessions are not messaging chats
    t = ho.resolve_target(rt, "t1")
    assert t["session_key"] == TELEGRAM_GROUP["session_key"] and t["reason"] == "task"


def test_target_uses_a_linked_work_session(ctx, sessions):
    rt = runtime.Runtime(ctx)
    worksession._update_link(rt, "s-dm", task_id="t2", title="x", last_activity=1)
    assert ho.resolve_target(rt, "t2")["session_key"] == TELEGRAM_DM["session_key"]


def test_target_falls_back_to_the_home_channel(ctx, sessions):
    t = ho.resolve_target(runtime.Runtime(ctx), "never-seen")
    assert t["reason"] == "home" and t["session_key"] == TELEGRAM_DM["session_key"]


def test_no_chat_at_all_is_a_named_error(ctx, sessions, monkeypatch):
    monkeypatch.setattr(ho, "_home_targets", lambda: [])
    with pytest.raises(ho.NeedsInput) as exc:
        ho.resolve_target(runtime.Runtime(ctx), "nothing")
    assert exc.value.kind == "no_chat" and "/sethome" in exc.value.message


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


# ------------------------------------------------------------------ route + relay

def test_route_queues_and_the_gateway_relay_injects_into_that_chat(client, ctx, sessions, monkeypatch):
    t = make_task(client, "Book the venue")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "phone"}).json()
    assert out["ok"] and out["mode"] == "chat"
    h = out["handoff"]
    assert h["state"] == "pending" and h["target"] == {"platform": "telegram", "chat_name": "Sam", "reason": "home"}

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


def test_a_refused_injection_is_retried_later_then_reported(client, ctx, sessions, monkeypatch):
    t = make_task(client, "Pay the invoice")
    h = client.post(f"/tasks/{t['task_id']}/handoff", json={}).json()["handoff"]
    ctx.inject_message = Injector(ok=False)
    monkeypatch.setattr(ho, "in_gateway_process", lambda: True)
    rt = runtime.Runtime(ctx)
    now = time.time()
    assert ho.relay_once(rt, now) == []
    assert client.get(f"/handoffs/{h['id']}").json()["handoff"]["state"] == "pending"
    assert ho.relay_once(rt, now + 1) == [] and len(ctx.inject_message.calls) == 1  # waits before retrying
    ho.relay_once(rt, now + ho.GIVE_UP_SECONDS + 5)
    st = client.get(f"/handoffs/{h['id']}").json()["handoff"]
    assert st["state"] == "failed" and "gateway" in st["error"]


def test_desktop_gets_the_note_without_queueing(client, sessions, ctx):
    t = make_task(client, "Draft the agenda")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "desktop"}).json()
    assert out["mode"] == "desktop" and "Draft the agenda" in out["text"] and "(the desktop app)" in out["text"]
    assert not list((runtime.Runtime(ctx).data_dir / "handoffs").glob("*.json"))


def test_without_permission_the_route_says_how_to_allow_it(client, sessions, monkeypatch):
    monkeypatch.setattr(ho, "injection_allowed", lambda: False)
    t = make_task(client, "Call the vet")
    out = client.post(f"/tasks/{t['task_id']}/handoff", json={"surface": "dashboard"})
    body = out.json()
    assert out.status_code == 400 and body["error"]["code"] == "permission"
    assert "allow_gateway_injection true" in body["error"]["message"]
