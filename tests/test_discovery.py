from __future__ import annotations

import json

import pytest

from alchemy_task import discovery as dv
from alchemy_task import runtime, task_tools
from alchemy_task.core import taskfile as tf

from test_setup import SetupCtx, home  # noqa: F401  (fixture)

SRC = [{"name": "Work email", "type": "email", "scope": "label:clients", "method": "gmail MCP"},
       {"name": "Team chat", "type": "chat", "scope": "#launch", "method": "slack skill"}]


@pytest.fixture
def ctx(home, settings, data_dir, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ALCHEMY_TASK_NO_SWEEPER", "1")
    c = SetupCtx({"workspace_root": settings.workspace_root, "timezone": "America/New_York"}, data_dir)
    c.state.set("timezone_confirmed", True)
    runtime.bind(c)
    yield c
    runtime.bind(None)


def tool(fn, session="disc-chat", **args):
    return json.loads(fn(args, session_id=session))


def make_stream(name="work", session="disc-chat", **kw):
    args = dict(action="create", name=name, areas=["work"], sources=SRC, time="6 PM", user_approved=True)
    args.update(kw)
    return tool(task_tools.discovery_stream, session=session, **args)


CANDS = [
    {"title": "Send Sam the revised quote", "source_id": "msg-1", "summary": "Sam asked for the revised quote",
     "why": "You promised it on the call", "source": "email from Sam", "source_type": "email",
     "due_hint": "2026-11-12", "link": "https://mail.example.com/msg-1", "research_notes": "Quote template exists."},
    {"title": "Book the launch retro", "source_id": "slack-9", "summary": "Lee: can you set up the retro?",
     "source": "#launch", "source_type": "chat"},
    {"title": "Draft spring newsletter", "source_id": "msg-2", "summary": "dup of an open task"},
]


def test_schedule_parsing():
    assert dv.schedule_for("daily", "6 PM") == ("0 18 * * *", "daily at 6:00 PM")
    assert dv.schedule_for("daily", "6:00 PM (recommended)")[0] == "0 18 * * *"
    assert dv.schedule_for("weekdays", "9:30 am") == ("30 9 * * 1-5", "weekdays at 9:30 AM")
    assert dv.schedule_for("hourly", "")[0] == "5 * * * *"
    with pytest.raises(dv.DiscoveryError):
        dv.parse_time("25:00")


def test_create_requires_approval_sources_and_timezone(ctx):
    assert tool(task_tools.discovery_stream, action="create", name="work", sources=SRC)["needs"] == "discovery"
    assert make_stream(sources=[])["needs"] == "discovery"
    out = make_stream()
    assert out["ok"] and out["stream"]["when"] == "daily at 6:00 PM"
    job = next(iter(ctx.cron.values()))
    assert job["deliver"] == "origin" and job["attach_to_session"] and job["timezone"] == "America/New_York"
    assert job["schedule"] == "0 18 * * *" and "discovery_start" in job["prompt"]


def test_run_digest_dedupe_and_decide(ctx, settings):
    make_stream()
    start = tool(task_tools.discovery_start, stream="work")
    assert start["sources"] == [dict(s) for s in SRC] and start["research_remaining_today"] == 50
    assert any(t["title"] == "Draft the spring newsletter" for t in start["open_tasks"])
    sub = tool(task_tools.discovery_submit, stream="work", candidates=CANDS,
               coverage=[{"source": "Work email", "status": "ok"},
                         {"source": "Team chat", "status": "failed", "note": "token expired"}])
    assert sub["added"] == 2 and sub["skipped"][0]["why"].startswith("open task exists")
    d = sub["digest"]
    assert "**1.** Send Sam the revised quote (work, due 2026-11-12, email from Sam)" in d
    assert "**2.** Book the launch retro" in d and "⚠️ Team chat: failed (token expired)" in d
    assert "Checked: Work email." in d
    # same source never proposed twice
    again = tool(task_tools.discovery_submit, stream="work", candidates=CANDS[:1], coverage=[])
    assert again["added"] == 0 and again["skipped"][0]["why"] == "already proposed"
    # the digest chat gets a hint for numeric replies
    assert "discovery_decide" in dv.pre_llm_call(session_id="disc-chat")["context"]
    # approving #2 needs a due date; #1 has a hint
    need = tool(task_tools.discovery_decide, approve=["1", "2"])
    assert need["needs"] == "due" and "2" in need["message"]
    done = tool(task_tools.discovery_decide, approve=["1", "2"], edits={"2": {"due": "2026-11-15"}})
    assert done["ok"] and len(done["results"]) == 2 and done["git"]["pushed"]
    doc = tf.parse_file(settings.root() / "areas/work/tasks" /
                        next(p.name for p in (settings.root() / "areas/work/tasks").glob("*send-sam*")))
    assert "Found by the work discovery stream" in doc.body and "Source ID: `msg-1`" in doc.body
    assert "Discovery research: Quote template exists." in doc.body and doc.fm["due"] == "2026-11-12"
    # a later run lists only new items
    nxt = tool(task_tools.discovery_submit, stream="work", candidates=[], coverage=[])
    assert "Nothing new" in nxt["digest"]
    assert tool(task_tools.discovery_decide, approve=["1"])["needs"] == "discovery"  # already added


def test_unpicked_items_are_not_relisted_but_stay_replyable(ctx):
    make_stream()
    tool(task_tools.discovery_submit, stream="work", candidates=CANDS[:2], coverage=[])
    tool(task_tools.discovery_decide, approve=["1"])  # the user ignores 2
    out = tool(task_tools.discovery_submit, stream="work", candidates=[], coverage=[])
    assert "Book the launch" not in out["digest"]
    later = tool(task_tools.discovery_decide, approve=["2"], edits={"2": {"due": "2026-11-20"}})
    assert later["results"][0]["title"] == "Book the launch retro"


def test_two_streams_in_one_chat_get_letters_and_cross_stream_dedupe(ctx):
    make_stream("work")
    make_stream("bakery", areas=["home"])
    streams = dv._streams(runtime.Runtime())
    assert {streams["work"]["label"], streams["bakery"]["label"]} == {"W", "B"}
    tool(task_tools.discovery_submit, stream="work", candidates=CANDS[:1], coverage=[])
    other = tool(task_tools.discovery_submit, stream="bakery", candidates=CANDS[:1], coverage=[])
    assert other["added"] == 0  # same message already proposed by the work stream
    assert "**W1.**" in dv.render_digest(streams["work"], list(dv._props(runtime.Runtime(), "work")["items"]
                                                             .values()), [], "x")
    tool(task_tools.discovery_submit, stream="bakery", candidates=[{**CANDS[1], "source_id": "b-1"}], coverage=[])
    assert tool(task_tools.discovery_decide, approve=["1"])["needs"] == "discovery"  # ambiguous without letter
    ok = tool(task_tools.discovery_decide, dismiss=["B1"])
    assert ok["ok"] and ok["dismissed"] == ["Book the launch retro"]


def test_separate_chats_keep_plain_numbers_and_research_cap(ctx):
    make_stream("work", session="chat-a", research_cap=1)
    make_stream("bakery", session="chat-b", areas=["home"])
    assert dv._streams(runtime.Runtime())["work"]["label"] == ""
    many = [{**CANDS[0], "source_id": f"m{i}", "title": f"Reply to client {i}"} for i in range(3)]
    tool(task_tools.discovery_submit, stream="work", candidates=many, coverage=[])
    items = dv._props(runtime.Runtime(), "work")["items"]
    assert sum(1 for p in items.values() if p["researched"]) == 1


def test_numbers_continue_through_the_day_and_restart_next_day(ctx, monkeypatch):
    make_stream()
    v = [{**CANDS[1], "source_id": f"s{i}", "title": f"Call supplier number {i}", "due_hint": "2026-11-20"}
         for i in range(1, 6)]
    d1 = tool(task_tools.discovery_submit, stream="work", candidates=v[:3], coverage=[])["digest"]
    d2 = tool(task_tools.discovery_submit, stream="work", candidates=[{**v[3], "title": "Ask the printer about badge stock"}],
              coverage=[])["digest"]
    assert "**3.**" in d1 and "**4.** Ask the printer about badge stock" in d2 and "**1.**" not in d2
    assert tool(task_tools.discovery_decide, approve=["2"])["results"][0]["title"] == "Call supplier number 2"
    # next day: numbers restart; a bare number means today's, day=yesterday reaches back
    monkeypatch.setattr(dv, "_today", lambda rt: "2099-01-02")
    d3 = tool(task_tools.discovery_submit, stream="work", candidates=[{**v[4], "title": "Renew the domain"}],
              coverage=[])["digest"]
    assert "**1.** Renew the domain" in d3
    assert tool(task_tools.discovery_decide, approve=["1"])["results"][0]["title"] == "Renew the domain"
    earlier = runtime.Runtime().settings.today()
    back = tool(task_tools.discovery_decide, approve=["3"], day=earlier)
    assert back["results"][0]["title"] == "Call supplier number 3"
    monkeypatch.setattr(dv, "_today", lambda rt: __import__("datetime").date.today().isoformat())


def test_invalid_edit_creates_nothing_and_failures_stay_open(ctx, settings):
    make_stream()
    tool(task_tools.discovery_submit, stream="work", candidates=CANDS[:2], coverage=[])
    tasks = settings.root() / "areas/work/tasks"
    before = len(list(tasks.glob("*.md")))
    bad = tool(task_tools.discovery_decide, approve=["1", "2"], edits={"2": {"due": "someday soon"}})
    assert bad["needs"] == "fix_call" and len(list(tasks.glob("*.md"))) == before
    bad = tool(task_tools.discovery_decide, approve=["2"], edits={"2": {"due": "2026-11-13", "area": "garden"}})
    assert bad["needs"] == "fix_call"
    ok = tool(task_tools.discovery_decide, approve=["1", "1", "2"], edits={"2": {"due": "2026-11-13"}})
    assert len([r for r in ok["results"] if r.get("task_id")]) == 2
    assert len(list(tasks.glob("*.md"))) == before + 2
    assert all(r["due"] for r in ok["results"])


def test_bad_due_hint_is_dropped(ctx):
    make_stream()
    out = tool(task_tools.discovery_submit, stream="work",
               candidates=[{**CANDS[1], "due_hint": "next Friday"}], coverage=[])
    assert out["added"] == 1


def test_update_keeps_schedule_parts_and_chat(ctx):
    make_stream(time="7 PM")
    jid = next(iter(ctx.cron))
    out = tool(task_tools.discovery_stream, session="other-chat", action="update", name="work",
               frequency="weekdays", user_approved=True)
    assert out["ok"] and out["stream"]["when"] == "weekdays at 7:00 PM"
    assert list(ctx.cron) == [jid] and ctx.cron[jid]["schedule"] == "0 19 * * 1-5"
    assert ctx.cron[jid]["deliver"] == "origin"  # same job: still posts to its own chat
    out = tool(task_tools.discovery_stream, action="update", name="work", time="8 AM", user_approved=True)
    assert out["stream"]["when"] == "weekdays at 8:00 AM"


def test_update_one_thing_at_a_time(ctx):
    make_stream()
    jid = next(iter(ctx.cron))
    out = tool(task_tools.discovery_stream, action="update", name="work", frequency="hourly", user_approved=True)
    assert out["stream"]["when"] == "hourly" and ctx.cron[jid]["schedule"] == "5 * * * *"
    out = tool(task_tools.discovery_stream, action="update", name="work", time="9 AM", user_approved=True)
    assert out["stream"]["when"] == "daily at 9:00 AM"
    gmail = {"name": "Gmail", "type": "email", "scope": "inbox, not newsletters", "method": "gmail MCP"}
    out = tool(task_tools.discovery_stream, action="update", name="work", add_sources=[gmail], user_approved=True)
    names = [s["name"] for s in out["stream"]["sources"]]
    assert names == ["Work email", "Team chat", "Gmail"] and "Added source(s): Gmail" in out["message"]
    out = tool(task_tools.discovery_stream, action="update", name="work", remove_sources=["Team chat"],
               user_approved=True)
    assert [s["name"] for s in out["stream"]["sources"]] == ["Work email", "Gmail"]
    assert tool(task_tools.discovery_stream, action="update", name="work", remove_sources=["Nope"],
                user_approved=True)["needs"] == "discovery"
    assert out["stream"]["when"] == "daily at 9:00 AM" and list(ctx.cron) == [jid]


def test_remove_and_teardown(ctx):
    make_stream()
    assert tool(task_tools.discovery_stream, action="remove", name="work")["ok"] and ctx.cron == {}
    make_stream("a1")
    assert dv.teardown_streams(runtime.Runtime()) == ["a1"] and ctx.cron == {}
