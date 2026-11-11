"""Task and settings routes behind the Tasks UI (dashboard/plugin_api.py), against a real fixture workspace."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from alchemy_task import runtime
from alchemy_task.core import taskfile as tf
from alchemy_task.dashboard import settings_api, tasks_api, ui_common

from helpers import git
from test_setup import SetupCtx, home  # noqa: F401  (fixture)


@pytest.fixture
def ctx(home, settings, data_dir, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ALCHEMY_TASK_NO_SWEEPER", "1")
    c = SetupCtx({"workspace_root": settings.workspace_root, "timezone": "America/New_York",
                  "research_by_default": False}, data_dir)
    c.state.set("timezone_confirmed", True)
    return c


@pytest.fixture
def client(ctx, monkeypatch):
    make = lambda: runtime.Runtime(ctx)  # noqa: E731
    monkeypatch.setattr(tasks_api, "runtime", make)
    monkeypatch.setattr(settings_api, "runtime", make)
    monkeypatch.setattr(ui_common, "admit", lambda request: None)
    app = FastAPI()
    app.include_router(tasks_api.router)
    app.include_router(settings_api.router)
    return TestClient(app)


def today(client):
    return client.get("/meta").json()["today"]


def make_task(client, title="Write the launch plan", date=None, area="work"):
    out = client.post("/tasks", json={"title": title, "date": date or today(client), "area": area}).json()
    assert out["ok"], out
    return out["task"]


def test_meta_reports_today_and_areas(client):
    m = client.get("/meta").json()
    assert m["ok"] and m["configured"] and len(m["today"]) == 10
    assert set(m["areas"]) >= {"work", "home"}


def test_range_lists_by_effective_date_and_optionally_done(client, workspace):
    t = make_task(client)
    day = t["date"]
    rows = client.get("/tasks", params={"from": day, "to": day}).json()["tasks"]
    assert [r["task_id"] for r in rows if r["task_id"] == t["task_id"]]
    assert all(r["revision"] and r["date"] == day for r in rows)
    client.post(f"/tasks/{t['task_id']}/complete")
    open_only = client.get("/tasks", params={"from": day, "to": day}).json()["tasks"]
    assert t["task_id"] not in {r["task_id"] for r in open_only}
    with_done = client.get("/tasks", params={"from": day, "to": day, "include_done": "1"}).json()["tasks"]
    done = next(r for r in with_done if r["task_id"] == t["task_id"])
    assert done["status"] == "done" and done["completed"] == day


def test_overdue_lists_only_open_past_tasks(client):
    t0 = today(client)
    past = make_task(client, "Old thing", date="2026-01-05")
    future = make_task(client, "Future thing", date="2099-01-05")
    ids = {r["task_id"] for r in client.get("/overdue").json()["tasks"]}
    assert past["task_id"] in ids and future["task_id"] not in ids
    assert all(r["date"] < t0 for r in client.get("/overdue").json()["tasks"])


def test_move_sets_both_dates_logs_and_commits(client, workspace):
    t = make_task(client)
    out = client.patch(f"/tasks/{t['task_id']}", json={"date": "2099-03-04"}).json()
    assert out["ok"] and out["task"]["due"] == "2099-03-04" and out["task"]["scheduled"] == "2099-03-04"
    assert "Moved in the Tasks view." in out["task"]["body"]
    assert out["git"]["committed"] and out["git"]["pushed"]
    assert git(workspace, "status", "--porcelain").stdout.strip() == ""


def test_separate_due_date_keeps_the_work_day(client):
    t = make_task(client, date="2099-03-04")
    out = client.patch(f"/tasks/{t['task_id']}", json={"due": "2099-03-10", "keep_separate": True}).json()
    assert out["task"]["due"] == "2099-03-10" and out["task"]["scheduled"] == "2099-03-04"


def test_complete_and_reopen_round_trip(client):
    t = make_task(client)
    done = client.post(f"/tasks/{t['task_id']}/complete").json()["task"]
    assert done["status"] == "done" and done["completed"]
    back = client.post(f"/tasks/{t['task_id']}/reopen").json()["task"]
    assert back["status"] == "open" and "completed" not in back


def test_title_edit_with_stale_revision_is_refused(client):
    t = make_task(client)
    client.patch(f"/tasks/{t['task_id']}", json={"priority": "high"})
    r = client.patch(f"/tasks/{t['task_id']}", json={"title": "New title", "expected_revision": t["revision"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_revision"
    fresh = client.get(f"/tasks/{t['task_id']}").json()["task"]
    ok = client.patch(f"/tasks/{t['task_id']}", json={"title": "New title", "expected_revision": fresh["revision"]}).json()
    assert ok["task"]["title"] == "New title"


def test_body_replace_keeps_frontmatter_and_checks_revision(client, workspace):
    t = client.get(f"/tasks/{make_task(client)['task_id']}").json()["task"]
    body = t["body"].replace("## Log", "## Notes from the editor\n\n- [ ] first step\n\n## Log")
    out = client.put(f"/tasks/{t['task_id']}/body", json={"body": body, "expected_revision": t["revision"]}).json()
    assert out["ok"] and "- [ ] first step" in out["task"]["body"]
    assert "Edited notes in the Tasks view." in out["task"]["body"]
    path = workspace / out["task"]["path"]
    doc = tf.parse_file(path)
    assert doc.fm["task_id"] == t["task_id"] and doc.fm["title"] == t["title"]
    # a second save in the same session adds no second log line
    again = out["task"]["body"].replace("- [ ] first step", "- [x] first step")
    out2 = client.put(f"/tasks/{t['task_id']}/body", json={"body": again, "expected_revision": out["task"]["revision"]}).json()
    assert out2["task"]["body"].count("Edited notes in the Tasks view.") == 1
    stale = client.put(f"/tasks/{t['task_id']}/body", json={"body": body, "expected_revision": t["revision"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_revision"
    assert git(workspace, "status", "--porcelain").stdout.strip() == ""


def test_errors_are_json_with_codes(client):
    assert client.get("/tasks/not-a-task").json()["error"]["code"] == "not_found"
    assert client.get("/tasks", params={"from": "nope"}).json()["error"]["code"] == "invalid_request"
    assert client.post("/tasks", json={"title": ""}).json()["error"]["code"] == "title"
    assert client.post("/tasks", json={"title": "x", "area": "nowhere"}).json()["error"]["code"] == "area"
    r = client.patch("/tasks/00000000-0000-4000-8000-000000000000", json={"bogus": 1})
    assert r.json()["error"]["code"] == "invalid_request"


def test_routes_require_dashboard_admission(ctx, monkeypatch):
    monkeypatch.setattr(tasks_api, "runtime", lambda: runtime.Runtime(ctx))

    def refuse(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    monkeypatch.setattr(ui_common, "admit", refuse)
    app = FastAPI()
    app.include_router(tasks_api.router)
    r = TestClient(app).get("/meta")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_settings_changes_a_stream_schedule_in_place(client, ctx):
    from alchemy_task import task_tools
    runtime.bind(ctx)
    try:
        made = json.loads(task_tools.discovery_stream(
            {"action": "create", "name": "work", "areas": ["work"], "time": "6 PM", "user_approved": True,
             "sources": [{"name": "Work email", "type": "email", "scope": "inbox", "method": "gmail"}]},
            session_id="chat-1"))
        assert made["ok"], made
    finally:
        runtime.bind(None)
    s = client.get("/settings").json()
    stream = next(x for x in s["streams"] if x["name"] == "work")
    assert stream["frequency"] == "daily" and stream["sources"][0]["name"] == "Work email"
    out = client.patch("/settings/streams/work", json={"frequency": "weekdays", "time": "7:30 AM"}).json()
    assert out["ok"] and out["stream"]["when"] == "weekdays at 7:30 AM"
    assert client.patch("/settings/streams/work", json={"frequency": "sometimes"}).json()["error"]["code"] == "invalid_request"


def test_settings_task_defaults(client, ctx):
    out = client.patch("/settings/tasks", json={"research_by_default": True, "default_area": "home"}).json()
    assert out["ok"]
    s = client.get("/settings").json()["tasks"]
    assert s["research_by_default"] is True and s["default_area"] == "home"
    assert client.patch("/settings/tasks", json={"default_area": "mars"}).json()["error"]["code"] == "area"


def test_settings_research_model(client, ctx):
    s = client.get("/settings").json()["tasks"]
    assert s["research_model"] is None and s["research_provider"] is None
    out = client.patch("/settings/tasks", json={"research_model": "  deepseek-v4-flash ",
                                                "research_provider": "openrouter"}).json()
    assert out["ok"]
    s = client.get("/settings").json()["tasks"]
    assert s["research_model"] == "deepseek-v4-flash" and s["research_provider"] == "openrouter"
    assert client.patch("/settings/tasks", json={"research_model": 5}).json()["error"]["code"] == "invalid_request"
    assert client.patch("/settings/tasks", json={"research_model": "x" * 201}).json()["error"]["code"] == \
        "invalid_request"
    assert client.patch("/settings/tasks", json={"research_model": "", "research_provider": ""}).json()["ok"]
    s = client.get("/settings").json()["tasks"]
    assert s["research_model"] is None and s["research_provider"] is None


# ------------------------------------------------------------------ research button

def _set_research(workspace_task_path, enrichment):
    doc = tf.parse_file(workspace_task_path)
    fm = dict(doc.fm)
    if enrichment is None:
        fm.pop("enrichment", None)
    else:
        fm["enrichment"] = enrichment
    tf.atomic_write(doc.path, tf.render(fm, doc.body, seq_offset=doc.seq_offset, keep_blank=doc.blank_keys).encode(),
                    expect=doc.raw)


def _task_path(ctx, task_id):
    return runtime.Runtime(ctx).store().resolve(task_id).path


def _enrichment(ctx, task_id):
    return tf.parse_file(_task_path(ctx, task_id)).fm.get("enrichment") or {}


class RunCtx(SetupCtx):
    """Records sweep runs fired through the public cronjob_manage tool."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.runs: list[str] = []
        self.sweep_jobs = {"sweep1": {"enabled": True, "state": "scheduled"}}

    def dispatch_tool(self, name, args):
        if name == "cronjob_manage" and args.get("action") == "list":
            return json.dumps({"jobs": [{"job_id": k, **v} for k, v in self.sweep_jobs.items()]})
        if name == "cronjob_manage" and args.get("action") == "run":
            self.runs.append(args["job_id"])
            return json.dumps({"success": True, "job": {"id": args["job_id"]}})
        return super().dispatch_tool(name, args)


@pytest.fixture
def rclient(home, settings, data_dir, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ALCHEMY_TASK_NO_SWEEPER", "1")
    c = RunCtx({"workspace_root": settings.workspace_root, "timezone": "America/New_York",
                "research_by_default": False}, data_dir)
    c.state.set("timezone_confirmed", True)
    make = lambda: runtime.Runtime(c)  # noqa: E731
    monkeypatch.setattr(tasks_api, "runtime", make)
    monkeypatch.setattr(ui_common, "admit", lambda request: None)
    monkeypatch.setattr(tasks_api, "_background", lambda fn: fn())  # run the sweep trigger inline in tests
    app = FastAPI()
    app.include_router(tasks_api.router)
    return TestClient(app), c


def test_research_button_queues_a_never_researched_task_and_starts_the_sweep(rclient):
    client, c = rclient
    c.state.set("jobs", {"research-sweep": {"job_id": "sweep1", "hash": "x"}})
    t = make_task(client)
    _set_research(_task_path(c, t["task_id"]), None)
    assert client.get(f"/tasks/{t['task_id']}").json()["task"]["research"] == "none"
    out = client.post(f"/tasks/{t['task_id']}/research").json()
    assert out["ok"] and out["queued"] is True and out["starts"] == "now", out
    assert out["task"]["research"] == "pending"
    assert c.runs == ["sweep1"]
    assert _enrichment(c, t["task_id"])["status"] == "pending"
    assert "Research requested in the Tasks view." in tf.parse_file(_task_path(c, t["task_id"])).body


def test_research_button_refreshes_complete_and_retries_skipped_or_failed(rclient):
    client, c = rclient  # no sweep job registered: queue only, the next sweep starts it
    for status in ("complete", "skipped", "failed"):
        t = make_task(client, title=f"Task {status}")
        _set_research(_task_path(c, t["task_id"]), {"status": status, "attempts": 3, "updated": "2026-11-01T00:00:00Z"})
        out = client.post(f"/tasks/{t['task_id']}/research").json()
        assert out["ok"] and out["queued"] is True and out["starts"] != "now", out
        assert "scheduled jobs are set up" in out["message"], out
        st = _enrichment(c, t["task_id"])
        assert st["status"] == "pending" and st["attempts"] == 0
    assert c.runs == []


def test_research_button_refuses_pending_or_running(rclient):
    client, c = rclient
    c.state.set("jobs", {"research-sweep": {"job_id": "sweep1", "hash": "x"}})
    t = make_task(client)
    path = _task_path(c, t["task_id"])
    _set_research(path, {"status": "pending", "attempts": 0, "updated": "2026-11-01T00:00:00Z"})
    r = client.post(f"/tasks/{t['task_id']}/research")
    assert r.status_code == 409 and r.json()["error"]["code"] == "research_busy"
    from alchemy_task.core import research as rs
    _set_research(path, {"status": "running", "attempts": 1, "run_id": "r1", "claimed_at": rs.now_iso(),
                         "updated": rs.now_iso()})
    before = tf.parse_file(path).raw
    r = client.post(f"/tasks/{t['task_id']}/research")
    assert r.status_code == 409 and r.json()["error"]["code"] == "research_busy"
    assert tf.parse_file(path).raw == before and c.runs == []


def test_research_button_unknown_task_and_closed_task(rclient):
    client, c = rclient
    r = client.post("/tasks/00000000-0000-4000-8000-000000000000/research")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    t = make_task(client)
    client.post(f"/tasks/{t['task_id']}/complete")
    r = client.post(f"/tasks/{t['task_id']}/research")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_research_button_requires_admission_and_rejects_extra_fields(rclient, monkeypatch):
    client, c = rclient
    t = make_task(client)
    assert client.post(f"/tasks/{t['task_id']}/research", json={"bogus": 1}).json()["error"]["code"] == "invalid_request"

    def refuse(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    monkeypatch.setattr(ui_common, "admit", refuse)
    r = client.post(f"/tasks/{t['task_id']}/research")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert _enrichment(c, t["task_id"])["status"] == "skipped"


def test_research_button_still_queues_when_the_sweep_cannot_start(rclient):
    client, c = rclient
    c.state.set("jobs", {"research-sweep": {"job_id": "sweep1", "hash": "x"}})

    def boom(name, args):
        raise RuntimeError("cron unavailable")
    c.dispatch_tool = boom
    t = make_task(client)
    out = client.post(f"/tasks/{t['task_id']}/research").json()
    assert out["ok"] and out["queued"] is True
    assert _enrichment(c, t["task_id"])["status"] == "pending"


def test_research_button_does_not_say_starting_now_for_a_paused_or_missing_sweep_job(rclient):
    client, c = rclient
    c.state.set("jobs", {"research-sweep": {"job_id": "sweep1", "hash": "x"}})
    for jobs, words in (({"sweep1": {"enabled": False, "state": "paused"}}, "research sweep job is resumed"),
                        ({"sweep1": {"paused": True}}, "research sweep job is resumed"),
                        ({}, "scheduled jobs are set up")):
        c.sweep_jobs = jobs
        t = make_task(client, title=f"Task {words} {len(jobs)}")
        _set_research(_task_path(c, t["task_id"]), None)
        out = client.post(f"/tasks/{t['task_id']}/research").json()
        assert out["ok"] and out["queued"] is True and out["starts"] != "now", out
        assert words in out["message"] and "Starting now" not in out["message"], out
        assert _enrichment(c, t["task_id"])["status"] == "pending"
    assert c.runs == []
