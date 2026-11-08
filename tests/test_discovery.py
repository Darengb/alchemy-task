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
    assert 'discovery_research_run' in job['prompt'] and 'discovery_join' in job['prompt']
    assert 'alchemy-task-discovery' in job['enabled_toolsets']
    assert 'alchemy-task-discovery-child' in job['enabled_toolsets']


def test_freeform_research_is_not_a_discovery_acceptance(ctx):
    make_stream()
    before = len(runtime.Runtime().store().scan().tasks)
    result = tool(task_tools.discovery_submit, stream="work", candidates=CANDS, coverage=[])
    assert result["ok"] is False and "research" in result["message"]
    assert len(runtime.Runtime().store().scan().tasks) == before


def test_title_similarity_never_skips_unresearched_source(ctx):
    make_stream()
    result = tool(task_tools.discovery_submit, stream="work", candidates=[CANDS[2]], coverage=[])
    assert result["ok"] is False
    assert not ctx.state.get("discovery_seen")


def test_unconfigured_prose_reader_does_not_fake_complete_start(ctx):
    make_stream()
    result = tool(task_tools.discovery_start, stream="work")
    assert result["ok"] is False and "configure" in result["message"]


def test_two_streams_preserve_origin_labels_not_source_skip(ctx):
    make_stream("work")
    make_stream("home")
    streams = dv._streams(runtime.Runtime())
    assert streams["work"]["label"] == "W" and streams["home"]["label"] == "H"
    for stream in streams:
        result = tool(task_tools.discovery_submit, stream=stream, candidates=CANDS[:1], coverage=[])
        assert result["ok"] is False
    assert not ctx.state.get("discovery_seen")


def test_separate_origin_chats_keep_plain_labels(ctx):
    make_stream("work", session="one")
    make_stream("home", session="two")
    assert all(not s["label"] for s in dv._streams(runtime.Runtime()).values())


def test_empty_submit_still_requires_saved_joined_run(ctx):
    make_stream()
    assert tool(task_tools.discovery_submit, stream="work", candidates=[], coverage=[])["ok"] is False


def test_missing_or_wrong_proposal_approval_never_creates_task(ctx):
    make_stream()
    before = len(runtime.Runtime().store().scan().tasks)
    assert tool(task_tools.discovery_decide, approve=["1"], edits={"1": {"undated": True}})["ok"] is False
    assert len(runtime.Runtime().store().scan().tasks) == before


def test_malformed_hint_cannot_be_converted_from_freeform(ctx):
    make_stream()
    assert tool(task_tools.discovery_submit, stream="work", candidates=[{**CANDS[1], "due_hint": "not a date"}], coverage=[])["ok"] is False


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
