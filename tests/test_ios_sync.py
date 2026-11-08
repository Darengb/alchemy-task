from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest

from alchemy_task import ios_sync as ios
from alchemy_task import runtime, task_tools
from alchemy_task.core import reminders as rm
from alchemy_task.core import taskfile as tf
from alchemy_task.core.store import TaskStore

from test_research_agent import FakeState

LIST_A, LIST_B = "LIST-DEFAULT", "LIST-OTHER"


class FakePhone:
    """Behaves like the mobile connector: requests succeed while online, stay pending while offline."""

    def __init__(self):
        self.online = True
        self.writes_stall = False  # reads answer, writes stay pending (the app closed mid-sync)
        self.lose_next_response = False
        self.reminders: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.keys: dict[str, str] = {}
        self.writes = 0
        self.lists = [{"id": LIST_A, "title": "Reminders", "writable": True, "default": True},
                      {"id": LIST_B, "title": "Errands", "writable": True, "default": False}]

    # -- device side
    def run(self, req):
        op, a = req["tool"], req["args"]
        if op == "mobile_reminders_list":
            items = [r for r in self.reminders.values() if r["list_id"] in (a.get("list_ids") or [r["list_id"]])]
            st = a.get("status", "incomplete")
            if st != "all":
                items = [r for r in items if r["completed"] == (st == "completed")]
            if a.get("query"):
                items = [r for r in items if a["query"].lower() in (r["title"] + r["notes"]).lower()]
            off, lim = a.get("offset", 0), a.get("limit", 50)
            page = items[off:off + lim]
            nxt = off + lim if off + lim < len(items) else None
            return {"lists": self.lists, "reminders": [dict(r) for r in page], "total": len(items), "next_offset": nxt}
        self.writes += 1
        if op == "mobile_reminder_create":
            rid = str(uuid.uuid4()).upper()
            lst = next(x for x in self.lists if x["id"] == a.get("list_id", LIST_A))
            self.reminders[rid] = {"id": rid, "title": a["title"], "list": lst["title"], "list_id": lst["id"],
                                   "notes": a.get("notes", ""), "priority": a.get("priority", "none"),
                                   "due": None, "due_date": a.get("due_date"), "all_day": bool(a.get("due_date")),
                                   "completed": False}
            return dict(self.reminders[rid])
        r = self.reminders[a["id"]]
        if op == "mobile_reminder_update":
            for k in ("title",):
                if k in a:
                    r[k] = a[k]
            if "due_date" in a:
                r["due_date"], r["due"] = a["due_date"], None
            if a.get("clear_due"):
                r["due_date"] = r["due"] = None
            if a.get("completed") is False:
                r["completed"] = False
                r.pop("completed_at", None)
        if op == "mobile_reminder_complete":
            r["completed"], r["completed_at"] = True, "2026-11-08T15:00:00Z"
        return dict(r)

    def come_online(self):
        self.online = True
        for req in self.requests.values():
            if req["status"] == "pending":
                req["result"] = {"data": self.run(req), "status": "succeeded"}
                req["status"] = "succeeded"

    # -- what Alchemy Task sees
    def dispatch(self, name, args):
        if name == "mobile_devices":
            return json.dumps({"devices": [{"id": "PHONE-1", "name": "iPhone", "grants": ["reminders.read",
                               "reminders.write"], "features": ["reminders.query", "reminders.update"]}]})
        if name == "mobile_request_result":
            req = self.requests.get(args["request_id"])
            if req is None:
                return json.dumps({"status": "failed", "error": "Request not found in this profile"})
            return json.dumps({"id": req["id"], "status": req["status"], "result": req.get("result")})
        assert args.get("notify_when_ready") is False
        key = args.get("idempotency_key")
        if key and key in self.keys:
            req = self.requests[self.keys[key]]
        else:
            req = {"id": uuid.uuid4().hex, "tool": name, "args": dict(args), "status": "pending"}
            self.requests[req["id"]] = req
            if key:
                self.keys[key] = req["id"]
            if self.online and not (self.writes_stall and name != "mobile_reminders_list"):
                req["result"] = {"data": self.run(req), "status": "succeeded"}
                req["status"] = "succeeded"
        if self.lose_next_response and name == "mobile_reminder_create":
            self.lose_next_response = False
            return json.dumps({"error": "connection reset"})
        return json.dumps({"id": req["id"], "status": req["status"], "result": req.get("result")})


class Ctx:
    def __init__(self, settings, data_dir, phone):
        self._s = {"workspace_root": settings.workspace_root, "timezone": "America/New_York"}
        self.state = FakeState(data_dir)
        self.phone = phone

    def get_config(self, key, default=None):
        return self._s.get(key, default)

    def dispatch_tool(self, name, args):
        if self.phone is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        return self.phone.dispatch(name, args)


@pytest.fixture
def phone():
    return FakePhone()


@pytest.fixture
def ctx(settings, data_dir, phone, monkeypatch):
    monkeypatch.setenv("ALCHEMY_TASK_NO_SWEEPER", "1")
    c = Ctx(settings, data_dir, phone)
    runtime.bind(c)
    yield c
    runtime.bind(None)


def ios_call(**args):
    return json.loads(task_tools.task_ios(args))


def setup_ok(areas=("home", "work")):
    prev = ios_call(action="setup", areas=list(areas))
    assert prev["preview"] and prev["list"] == "Reminders"
    out = ios_call(action="setup", areas=list(areas), user_approved=True)
    assert out["saved"]
    return out


def mk(settings, data_dir, title, **kw):
    kw.setdefault("area", "home")
    kw.setdefault("due", "2026-12-01")
    return TaskStore(settings, data_dir).create(title=title, research=False, confirm_new=True, **kw)


def phone_task(phone, title):
    return next(r for r in phone.reminders.values() if r["title"] == title)


def test_projection_and_reconcile():
    assert rm.reconcile({"title": "a", "due": None, "completed": False}, {"title": "b", "due": None, "completed": False},
                        {"title": "a", "due": "2026-11-20", "completed": False}) == \
        {"push": {"title": "b"}, "pull": {"due": "2026-11-20"}, "adopt": {}, "conflicts": {}}
    c = rm.reconcile({"title": "a"}, {"title": "b"}, {"title": "c"})["conflicts"]
    assert c == {"title": {"base": "a", "local": "b", "native": "c"}}
    proj, extras = rm.remote_projection({"title": "x", "due": "2026-11-09T02:30:00Z", "completed": False},
                                        "America/New_York")
    assert proj["due"] == "2026-11-08" and extras["native_due"] == "2026-11-09T02:30:00Z"  # local calendar date
    assert rm.marker_task_id(rm.marker("3f2b8c1e-5d4a-4b6f-9e21-7a8c9d0e1f23")) == "3f2b8c1e-5d4a-4b6f-9e21-7a8c9d0e1f23"


def test_create_cutoff_and_status_rules():
    today = "2026-11-20"
    base = {"task_id": "3f2b8c1e-5d4a-4b6f-9e21-7a8c9d0e1f23", "status": "open"}
    assert rm.eligible_for_create({**base, "due": "2026-11-06"}, today)[0]       # exactly 14 days ago
    assert not rm.eligible_for_create({**base, "due": "2026-11-05"}, today)[0]   # 15 days ago
    assert rm.eligible_for_create({**base, "due": None}, today)[0]
    for status in ("in-progress", "waiting", "done", "cancelled", "todo"):
        assert not rm.eligible_for_create({**base, "status": status}, today)[0]


def test_no_connector(ctx):
    ctx.phone = None
    out = ios_call(action="setup", areas=["home"])
    assert out["needs"] == "ios" and "mobile app" in out["message"]
    assert ios_call()["needs"] == "setup"


def test_first_sync_creates_open_tasks_only_and_second_sync_writes_nothing(ctx, phone, settings, data_dir):
    store = TaskStore(settings, data_dir)
    a = mk(settings, data_dir, "Fix the gate latch", due="Nov 20")
    b = mk(settings, data_dir, "Order bakery boxes", area="work", due=None, undated=True)
    w = mk(settings, data_dir, "Call the plumber")
    store.update(w.task_id, {"status": "waiting", "reason": "plumber away"})
    phone.reminders["X"] = {"id": "X", "title": "Fix the gate latch", "list": "Reminders", "list_id": LIST_A,
                            "notes": "my own reminder", "priority": "none", "due": None, "due_date": None,
                            "completed": False}
    setup_ok()
    out = ios_call()
    assert out["synced"] and out["created"] == 3, out  # plus the open newsletter fixture in work
    titles = sorted(r["title"] for r in phone.reminders.values())
    assert "Call the plumber" not in titles and titles.count("Fix the gate latch") == 2  # the user's own one untouched
    mine = [r for r in phone.reminders.values() if rm.marker_task_id(r["notes"]) == a.task_id][0]
    assert mine["due_date"] == "2026-11-20" and mine["priority"] == "none"
    assert phone.reminders["X"]["notes"] == "my own reminder"
    writes = phone.writes
    again = ios_call()
    assert again["created"] == again["updated"] == 0 and phone.writes == writes
    assert again["problems"] == ["1 task(s) have no ID yet and were skipped (say \"fix my task files\")"]


def test_native_completion_and_reopen_come_back(ctx, phone, settings, data_dir):
    t = mk(settings, data_dir, "Return library books")
    setup_ok(["home"])
    ios_call()
    r = phone_task(phone, "Return library books")
    r["completed"], r["completed_at"] = True, "2026-11-08T03:30:00Z"  # 10:30 PM Nov 7 in New York
    out = ios_call()
    assert out["pulled"] == 1 and out["git"]["pushed"]
    doc = tf.parse_file(t.path)
    assert doc.fm["status"] == "done" and doc.fm["completed"] == "2026-11-07"
    assert "Changed in Apple Reminders: completion." in doc.body
    r["completed"] = False
    r.pop("completed_at")
    ios_call()
    doc = tf.parse_file(t.path)
    assert doc.fm["status"] == "open" and doc.fm["completed"] is None


def test_local_changes_push_and_native_date_edit_pulls(ctx, phone, settings, data_dir):
    store = TaskStore(settings, data_dir)
    t = mk(settings, data_dir, "Renew the passport")
    setup_ok(["home"])
    ios_call()
    store.update(t.task_id, {"title": "Renew the passport online", "status": "done"})
    out = ios_call()
    r = phone_task(phone, "Renew the passport online")
    assert out["updated"] == 2 and r["completed"]
    store.update(t.task_id, {"status": "open", "reopen": True})
    ios_call()
    assert not phone_task(phone, "Renew the passport online")["completed"]
    r = phone_task(phone, "Renew the passport online")
    r["due_date"] = "2026-12-24"
    ios_call()
    doc = tf.parse_file(t.path)
    assert doc.fm["due"] == doc.fm["scheduled"] == "2026-12-24"


def test_conflict_reported_then_resolved(ctx, phone, settings, data_dir):
    store = TaskStore(settings, data_dir)
    t = mk(settings, data_dir, "Plan the garden")
    setup_ok(["home"])
    ios_call()
    phone_task(phone, "Plan the garden")["title"] = "Plan the garden beds"
    store.update(t.task_id, {"title": "Plan the vegetable garden"})
    out = ios_call()
    assert out["conflicts"] == 1
    st = ios_call(action="status")
    assert st["conflicts"][t.task_id]["title"]["native"] == "Plan the garden beds"
    ios_call(action="resolve", task=t.task_id, choices={"title": "native"})
    ios_call()
    assert tf.parse_file(next((settings.root() / "areas/home/tasks").glob("*plan-the-garden*"))).fm["title"] == \
        "Plan the garden beds"


def test_phone_offline_waits_then_settles_without_duplicates(ctx, phone, settings, data_dir):
    mk(settings, data_dir, "Buy stamps")
    setup_ok(["home"])
    phone.online = False
    out = ios_call()
    assert not out["synced"] and "Waiting for your iPhone" in out["message"] and out["created"] == 0
    again = ios_call()  # still offline: no new requests piled up
    assert not again["synced"] and len([q for q in phone.requests.values() if q["tool"] != "mobile_reminders_list"]) <= 1
    phone.come_online()
    done = ios_call()
    assert done["synced"], done
    assert [r["title"] for r in phone.reminders.values()].count("Buy stamps") == 1


def test_lost_response_after_create_does_not_duplicate(ctx, phone, settings, data_dir):
    mk(settings, data_dir, "Water the plants")
    setup_ok(["home"])
    phone.lose_next_response = True
    ios_call()
    ios_call()
    assert [r["title"] for r in phone.reminders.values()].count("Water the plants") == 1
    assert ios_call(action="status")["mirrored"] >= 1


def test_expired_create_is_uncertain_until_confirmed(ctx, phone, settings, data_dir):
    t = mk(settings, data_dir, "Sharpen the knives")
    setup_ok(["home"])
    phone.writes_stall = True
    ios_call()
    for q in phone.requests.values():
        if q["tool"] == "mobile_reminder_create":
            q["status"] = "expired"  # the app closed before the phone ran it
    phone.writes_stall = False
    out = ios_call()
    assert any("may or may not have been created" in p for p in out["problems"])
    assert not any(r["title"] == "Sharpen the knives" for r in phone.reminders.values())
    ios_call(action="confirm_missing", task=t.task_id)
    ios_call()
    assert [r["title"] for r in phone.reminders.values()].count("Sharpen the knives") == 1


def test_disable_fences_and_cancelled_is_left_alone(ctx, phone, settings, data_dir):
    store = TaskStore(settings, data_dir)
    t = mk(settings, data_dir, "Clean the gutters")
    setup_ok(["home"])
    ios_call()
    store.update(t.task_id, {"status": "cancelled", "reason": "hired someone"})
    out = ios_call()
    assert any("cancelled here" in s for s in out["skipped"]) and not phone_task(phone, "Clean the gutters")["completed"]
    ios_call(action="disable")
    assert ios_call()["needs"] == "setup"


def test_done_reopen_done_really_completes(ctx, phone, settings, data_dir):
    store = TaskStore(settings, data_dir)
    t = mk(settings, data_dir, "Toggle me")
    setup_ok(["home"])
    ios_call()
    for status, extra in (("done", {}), ("open", {"reopen": True}), ("done", {})):
        store.update(t.task_id, {"status": status, **extra})
        ios_call()
    assert phone_task(phone, "Toggle me")["completed"]
    ios_call()
    assert tf.parse_file(t.path).fm["status"] == "done"


def test_transient_check_failure_does_not_duplicate(ctx, phone, settings, data_dir):
    mk(settings, data_dir, "Dup check")
    setup_ok(["home"])
    phone.writes_stall = True
    ios_call()
    real = phone.dispatch
    phone.dispatch = lambda n, a: json.dumps({"error": "temporarily unavailable"}) if n == "mobile_request_result" \
        else real(n, a)
    ios_call()
    phone.dispatch = real
    phone.writes_stall = False
    phone.come_online()
    ios_call()
    assert [r["title"] for r in phone.reminders.values()].count("Dup check") == 1


def test_refused_access_is_reported_not_waiting(ctx, phone, settings, data_dir):
    mk(settings, data_dir, "Refused")
    setup_ok(["home"])
    real = phone.dispatch
    phone.dispatch = lambda n, a: json.dumps({"status": "unavailable", "error": "app too old",
                                              "message": "Update Hermes Agent on the iPhone."}) \
        if n == "mobile_reminder_create" else real(n, a)
    out = ios_call()
    assert "refused" in out["message"] and "Waiting" not in out["message"] and not out["synced"]


def test_slash_command_uses_same_engine(ctx, phone, settings, data_dir):
    from alchemy_task.commands import task_command
    mk(settings, data_dir, "Mail the birthday card")
    setup_ok(["home"])
    assert "reminder(s) created" in task_command("ios")
    assert "already matches" in task_command("IOS")
