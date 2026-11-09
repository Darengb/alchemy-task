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
