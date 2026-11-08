from __future__ import annotations

import json
import time

import pytest

from alchemy_task import runtime, task_tools
from alchemy_task import worksession as ws
from alchemy_task.core import checkpoint as ck
from alchemy_task.core import taskfile as tf
from alchemy_task.core.store import TaskStore

from test_research_agent import FakeCtx, FakeLifecycle  # noqa: E402

NEWSLETTER = "3f2b8c1e-5d4a-4b6f-9e21-7a8c9d0e1f23"


class FakeLLM:
    def __init__(self, parsed=None, fail=False):
        self.parsed, self.fail, self.calls = parsed, fail, []

    def complete_structured(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("AuxiliaryClientUnavailable")
        return type("R", (), {"parsed": self.parsed})()


@pytest.fixture
def ctx(settings, data_dir, monkeypatch):
    monkeypatch.setenv("ALCHEMY_TASK_NO_SWEEPER", "1")
    c = FakeCtx(settings, data_dir, FakeLifecycle())
    c.llm = FakeLLM({"state": "waiting_user", "done": "Drafted intro and section list.",
                     "next_step": "Get the customer quote.", "needs_from": "Priya: the quote"})
    runtime.bind(c)
    monkeypatch.setattr(ws, "_transcript", lambda sid: [{"role": "user", "content": "work on the newsletter"},
                                                        {"role": "assistant", "content": "Drafted the intro."}])
    monkeypatch.setattr(ws, "_session_last_activity", lambda sid: None)
    yield c
    runtime.bind(None)


def call(fn, **args):
    session = args.pop("session_id", "chat-1")
    return json.loads(fn(args, session_id=session))


def test_checkpoint_rules():
    with pytest.raises(ck.CheckpointError):
        ck.normalize({"state": "done", "done": "Sent it"})  # no evidence
    with pytest.raises(ck.CheckpointError):
        ck.normalize({"state": "in_progress", "done": "x"})  # no next step
    with pytest.raises(ck.CheckpointError):
        ck.normalize({"state": "waiting_user", "done": "x"})
    assert ck.normalize({"state": "done", "done": "x", "evidence": "y", "next_step": "z"},
                        automatic=True)["state"] == "in_progress"


def test_start_work_links_and_returns_context(ctx, settings):
    out = call(task_tools.task_work_start, task=NEWSLETTER)
    assert out["ok"] and out["task"]["status"] == "in-progress" and "body" in out["task"]
    assert not out["resumed"] and "No checkpoint yet" in out["message"]
    assert ws.linked_task(runtime.Runtime(), "chat-1") == NEWSLETTER
    assert "working on the task" in ws.pre_llm_call(session_id="chat-1")["context"]
    assert ws.pre_llm_call(session_id="other") is None


def test_checkpoint_writes_state_block_status_and_log(ctx, settings):
    call(task_tools.task_work_start, task=NEWSLETTER)
    out = call(task_tools.task_checkpoint, state="waiting_user", done="Drafted the intro.",
               next_step="Add the quote.", needs_from="You: pick the customer quote")
    assert out["ok"] and out["task"]["status"] == "waiting" and out["git"]["pushed"]
    doc = tf.parse_file(settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md")
    assert doc.body.startswith(tf.CURRENT_STATE_START) and "**Waiting on you**" in doc.body
    assert "Checkpoint (waiting on you): Drafted the intro." in doc.body
    assert doc.fm["google_tasks"]["work"]["task_id"] == "FAKETASK1"
    # a second checkpoint replaces the block rather than adding another
    call(task_tools.task_checkpoint, state="in_progress", done="Added quote.", next_step="Proofread.")
    doc = tf.parse_file(doc.path)
    assert doc.body.count(tf.CURRENT_STATE_START) == 1 and "Added quote." in doc.body.split(tf.CURRENT_STATE_END)[0]
    # continue shows the current state
    again = call(task_tools.task_work_start, task=NEWSLETTER, session_id="chat-2")
    assert again["resumed"] and "Proofread." in again["message"]
    # done needs evidence; with it the task closes and the link is released
    assert call(task_tools.task_checkpoint, state="done", done="Sent.", session_id="chat-2")["needs"] == "checkpoint"
    done = call(task_tools.task_checkpoint, state="done", done="Sent.", evidence="Campaign page shows sent to 412",
                session_id="chat-2")
    assert done["task"]["status"] == "done" and done["task"]["completed"]
    assert ws.linked_task(runtime.Runtime(), "chat-2") is None


def test_checkpoint_without_link_asks_for_task(ctx):
    out = call(task_tools.task_checkpoint, state="in_progress", done="x", next_step="y", session_id="nolink")
    assert out["needs"] == "task"


def test_safety_net_on_finalize_uses_model(ctx, settings):
    call(task_tools.task_work_start, task=NEWSLETTER)
    ws.post_llm_call(session_id="chat-1", user_message="draft it", assistant_response="Drafted the intro.")
    ws.on_session_finalize(session_id="chat-1", reason="closed")
    doc = tf.parse_file(settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md")
    assert "automatic checkpoint from the session" in doc.body and "Priya: the quote" in doc.body
    assert doc.fm["status"] == "waiting"
    assert ctx.llm.calls and ctx.llm.calls[0]["json_schema"] == ck.AUTO_SCHEMA
    ws.on_session_finalize(session_id="chat-1")  # nothing new since: no second checkpoint
    assert doc.path.read_text().count("Automatic checkpoint") == 1


def test_safety_net_falls_back_without_model_and_never_marks_done(ctx, settings):
    ctx.llm = FakeLLM(fail=True)
    call(task_tools.task_work_start, task=NEWSLETTER)
    ws.post_llm_call(session_id="chat-1", user_message="send it", assistant_response="I sent the campaign.")
    out = ws.auto_checkpoint(runtime.Runtime(), "chat-1", "test")
    assert out["state"] == "in_progress" and len(ctx.llm.calls) == 2  # our slot, then default route
    doc = tf.parse_file(settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md")
    assert "I sent the campaign." in doc.body and doc.fm["status"] == "in-progress"


def test_closed_task_stops_safety_net_without_model_calls(ctx, settings):
    call(task_tools.task_work_start, task=NEWSLETTER)
    ws.post_llm_call(session_id="chat-1", user_message="x", assistant_response="y")
    TaskStore(settings, settings.root().parent / "plugin-data").update(NEWSLETTER, {"status": "done"})
    assert ws.auto_checkpoint(runtime.Runtime(), "chat-1", "idle") is None
    assert ctx.llm.calls == [] and ws.linked_task(runtime.Runtime(), "chat-1") is None


def test_incomplete_model_output_uses_free_digest(ctx, settings):
    ctx.llm = FakeLLM({"state": "in_progress", "done": "Reviewed the draft.", "next_step": "", "needs_from": ""})
    call(task_tools.task_work_start, task=NEWSLETTER)
    ws.post_llm_call(session_id="chat-1", user_message="looks good", assistant_response="Draft is ready.")
    out = ws.auto_checkpoint(runtime.Runtime(), "chat-1", "idle")
    assert out and out["automatic"]
    doc = tf.parse_file(settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md")
    assert "Draft is ready." in doc.body


def test_sweeper_standby_takes_over(ctx, data_dir, monkeypatch):
    import fcntl
    import os
    import threading
    monkeypatch.setattr(ws, "SWEEP_SECONDS", 0.05)
    swept = threading.Event()
    monkeypatch.setattr(ws, "sweep", lambda rt: swept.set() or [])
    os.makedirs(data_dir / "locks", exist_ok=True)
    holder = os.open(data_dir / "locks" / "sweeper.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(holder, fcntl.LOCK_EX)
    ws._stop.clear()
    t = threading.Thread(target=ws._sweep_loop, args=(str(data_dir),), daemon=True)
    t.start()
    time.sleep(0.2)
    assert t.is_alive() and not swept.is_set()  # standing by
    os.close(holder)  # the holder's process exits
    assert swept.wait(2)
    ws._stop.set()
    t.join(2)


def test_idle_sweep(ctx, settings):
    call(task_tools.task_work_start, task=NEWSLETTER)
    rt = runtime.Runtime()
    now = time.time()
    ws._update_link(rt, "chat-1", last_activity=now, last_checkpoint=0)
    assert ws.sweep(rt, now=now + 60) == []  # not idle yet
    res = ws.sweep(rt, now=now + ws.IDLE_SECONDS + 1)
    assert len(res) == 1 and res[0]["automatic"]
    assert ws.sweep(rt, now=now + ws.IDLE_SECONDS + 2) == []


def test_compaction_moves_link(ctx):
    call(task_tools.task_work_start, task=NEWSLETTER)
    ws.post_compaction(session_id="chat-1b", old_session_id="chat-1")
    rt = runtime.Runtime()
    assert ws.linked_task(rt, "chat-1b") == NEWSLETTER and ws.linked_task(rt, "chat-1") is None


def test_transcript_text_keeps_first_request_and_tail():
    msgs = [{"role": "user", "content": "FIRST"}] + [{"role": "tool", "content": "x" * 5000}] * 30 + \
           [{"role": "assistant", "content": "LAST"}]
    text = ck.transcript_text(msgs, limit=3000)
    assert text.startswith("user: FIRST") and text.endswith("assistant: LAST") and len(text) < 4000
