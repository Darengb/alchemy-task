"""Optional Apple Reminders sync through the Hermes mobile app connector (beta).

User-triggered only (`/task ios`, "sync reminders", "sync iOS"). One engine for every entry point. The phone
answers only while the Hermes app is open, so every phone request is recorded durably before it is sent, and a
pending request is reported as waiting, never as synced.

State (plugin data, never the public repo or Git): config, mappings task_id -> reminder, outbox of phone
operations, unresolved conflicts, last sync.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from .core import reminders as rm
from .core import taskfile as tf
from .core.locks import workspace_lock
from .core.store import NeedsInput
from .runtime import Runtime

MAX_IN_FLIGHT = 4
MAX_WRITES = 20
BUDGET_SECONDS = 60
UNKNOWN_DISPATCH_MAX_AGE = 20 * 3600  # re-sending the same key is safe well inside the connector's retention
WAITING = "Waiting for your iPhone. Open the Hermes app and run /task ios (or say \"sync reminders\") again."


class SyncError(ValueError):
    pass


# ------------------------------------------------------------------ state

def _path(rt: Runtime) -> Path:
    return rt.data_dir / "ios-reminders.json"


def load(rt: Runtime) -> dict[str, Any]:
    try:
        st = json.loads(_path(rt).read_text())
    except (OSError, ValueError):
        st = {}
    for key, default in (("config", {}), ("mappings", {}), ("ops", {}), ("conflicts", {}), ("reads", {}),
                         ("notes", {})):
        st.setdefault(key, default)
    return st


def save(rt: Runtime, st: dict[str, Any], *, keep_disk_config: bool = False) -> None:
    path = _path(rt)
    path.parent.mkdir(parents=True, exist_ok=True)
    with workspace_lock(rt.data_dir, "ios-state"):
        if keep_disk_config:  # a sync never overwrites a disable/setup made while it ran
            try:
                st["config"] = json.loads(path.read_text()).get("config", st["config"])
            except (OSError, ValueError):
                pass
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as fh:
            json.dump(st, fh, indent=1, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)


@contextlib.contextmanager
def _lease(rt: Runtime):
    path = rt.data_dir / "locks" / "ios-sync.lease"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SyncError("a Reminders sync is already running; try again in a minute")
        yield
    finally:
        os.close(fd)


# ------------------------------------------------------------------ phone

def _call(rt: Runtime, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    raw = rt.ctx.dispatch_tool(tool, args)
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (TypeError, ValueError):
        return {"status": "failed", "error": str(raw)[:300]}
    if "error" in data and "status" not in data:
        text = str(data["error"])
        if "Unknown tool" in text:
            return {"status": "no_connector", "error": text}
        return {"status": "failed", "error": text}
    return data


def _phone_args(cfg: dict[str, Any], **extra: Any) -> dict[str, Any]:
    args = {"device_id": cfg.get("device_id"), "notify_when_ready": False}
    args.update({k: v for k, v in extra.items() if v is not None})
    return args


def _data(resp: dict[str, Any]) -> dict[str, Any]:
    result = resp.get("result") or {}
    return result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else {}


def _key(*parts: Any) -> str:
    return "alchemy-task-" + hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


# ------------------------------------------------------------------ setup

def setup(rt: Runtime, args: dict[str, Any]) -> dict[str, Any]:
    devices = _call(rt, "mobile_devices", {})
    if devices.get("status") == "no_connector":
        raise SyncError("Reminders sync needs the Hermes mobile app (beta) and its device-access connector on this "
                        "Hermes. Everything else in Alchemy Task works without it.")
    eligible = [d for d in devices.get("devices") or []
                if "reminders.write" in (d.get("grants") or []) and "reminders.update" in (d.get("features") or [])]
    if not eligible:
        raise SyncError("No paired iPhone shares Reminders with this Hermes. In the Hermes app: Settings → Device "
                        "Access → Reminders.")
    device_id = args.get("device_id")
    if device_id:
        if device_id not in {d["id"] for d in eligible}:
            raise SyncError("that device is not paired with Reminders access")
    elif len(eligible) == 1:
        device_id = eligible[0]["id"]
    else:
        return {"needs": "device", "devices": [{"id": d["id"], "name": d.get("name")} for d in eligible],
                "message": "Several phones are paired; ask which one to use and pass device_id."}
    cfg = {"device_id": device_id}
    probe = _call(rt, "mobile_reminders_list", _phone_args(cfg, query=f"alchemy-task-list-probe-{uuid.uuid4().hex}",
                                                           limit=1, status="incomplete", wait_seconds=20))
    if probe.get("status") != "succeeded":
        return {"waiting": True, "message": WAITING if probe.get("status") in ("pending", "running") else
                f"The phone did not answer ({probe.get('status')}: {probe.get('error', '')})."}
    lists = [x for x in _data(probe).get("lists") or [] if x.get("writable")]
    wanted = str(args.get("list") or "").strip().lower()
    if wanted:
        matches = [x for x in lists if str(x.get("title") or "").strip().lower() == wanted]
        if not matches:
            raise SyncError(f"No writable Reminders list called {args['list']!r}. Lists: "
                            f"{', '.join(x['title'] for x in lists)}. (Alchemy Task does not create lists.)")
        if len(matches) > 1:
            raise SyncError(f"Several lists are called {args['list']!r}; rename one on the phone first.")
        chosen = matches[0]
    else:
        chosen = next((x for x in lists if x.get("default")), lists[0] if lists else None)
        if not chosen:
            raise SyncError("The phone has no writable Reminders list.")
    known = rt.settings.known_areas()
    areas = [a for a in (args.get("areas") or []) if a in known]
    if not areas:
        return {"needs": "areas", "areas": known, "list": chosen["title"],
                "message": "Ask which areas' tasks to mirror to Reminders (only those are synced)."}
    store = rt.store()
    today = rt.settings.today()
    count = sum(1 for t in store.scan().tasks if t.fm.get("area") in areas and rm.eligible_for_create(t.fm, today)[0])
    st = load(rt)
    old = st["config"]
    broadened = old and (old.get("device_id") != device_id or old.get("list_id") != chosen["id"]
                         or not set(areas) <= set(old.get("areas") or []))
    if not args.get("user_approved") or (broadened and not args.get("user_approved_change")):
        return {"preview": True, "device": next(d.get("name") for d in eligible if d["id"] == device_id),
                "list": chosen["title"], "areas": areas, "would_create": count,
                "message": (f"Mirror open tasks from {', '.join(areas)} into the Reminders list "
                            f"\"{chosen['title']}\": about {count} new reminder(s) at first, with titles, due dates "
                            "and checkboxes kept in sync when you run /task ios. Ask the user to approve, then call "
                            "again with user_approved=true.")}
    st["config"] = {"enabled": True, "device_id": device_id, "list_id": chosen["id"], "list_title": chosen["title"],
                    "areas": areas, "approved_at": time.time()}
    save(rt, st)
    return {"saved": True, "list": chosen["title"], "areas": areas, "would_create": count,
            "message": f"Reminders sync is set up for {', '.join(areas)} → \"{chosen['title']}\". Run it now?"}


def disable(rt: Runtime) -> dict[str, Any]:
    st = load(rt)
    if st["config"]:
        st["config"]["enabled"] = False
        save(rt, st)
    pending = sum(1 for op in st["ops"].values() if op.get("request_id"))
    return {"disabled": True, "message": "Reminders sync is off. Existing reminders stay on the phone."
            + (f" {pending} already-sent change(s) may still apply when the phone next connects." if pending else "")}


def status(rt: Runtime) -> dict[str, Any]:
    st = load(rt)
    cfg = st["config"]
    return {"configured": bool(cfg), "enabled": bool(cfg.get("enabled")), "list": cfg.get("list_title"),
            "areas": cfg.get("areas"), "mirrored": len(st["mappings"]),
            "pending": sum(1 for op in st["ops"].values() if op.get("state") in ("sent", "dispatching")),
            "uncertain": [op["title"] for op in st["ops"].values() if op.get("state") == "uncertain"],
            "conflicts": {tid: c for tid, c in st["conflicts"].items()},
            "last_sync": st.get("last_sync")}


def resolve(rt: Runtime, task: str, choices: dict[str, str]) -> dict[str, Any]:
    """Settle a conflict: per field, 'local' (task file wins) or 'native' (Reminders wins). Applied on next sync."""
    st = load(rt)
    doc = rt.store().resolve(task)
    conflict = st["conflicts"].get(doc.task_id)
    if not conflict:
        raise SyncError("that task has no Reminders conflict")
    m = st["mappings"][doc.task_id]
    for field, choice in choices.items():
        if field not in conflict or field.startswith("_"):
            continue
        if choice == "local":
            m["base"][field] = conflict[field]["native"]  # only the local side now differs -> it is pushed
        elif choice == "native":
            m["base"][field] = conflict[field]["local"]  # only the native side now differs -> it is pulled
        else:
            raise SyncError("choose 'local' or 'native' for each field")
        conflict.pop(field)
    if not [k for k in conflict if not k.startswith("_")]:
        st["conflicts"].pop(doc.task_id)
    save(rt, st)
    return {"resolved": sorted(choices), "message": "Saved. Run /task ios (or say \"sync reminders\") to apply it."}


def confirm_uncertain(rt: Runtime, task: str) -> dict[str, Any]:
    """The user checked the phone: no reminder exists for this task, so it may be created again."""
    st = load(rt)
    doc = rt.store().resolve(task)
    dropped = [k for k, op in st["ops"].items() if op.get("task_id") == doc.task_id and op.get("state") == "uncertain"]
    for k in dropped:
        st["ops"].pop(k)
        st["notes"].setdefault("attempts", {})
        st["notes"]["attempts"][doc.task_id] = st["notes"]["attempts"].get(doc.task_id, 0) + 1
    save(rt, st)
    return {"cleared": len(dropped)}


# ------------------------------------------------------------------ sync

def sync(rt: Runtime, *, budget: float = BUDGET_SECONDS) -> dict[str, Any]:
    with _lease(rt):
        st = load(rt)
        cfg = st["config"]
        if not cfg:
            return {"needs": "setup", "message": "Reminders sync isn't set up yet. Say \"set up iPhone reminders\" "
                    "to choose which tasks go to Reminders."}
        if not cfg.get("enabled"):
            return {"needs": "setup", "message": "Reminders sync is turned off. Say \"set up iPhone reminders\" to "
                    "turn it back on."}
        return _sync(rt, st, cfg, time.monotonic() + budget)


def _sync(rt: Runtime, st: dict[str, Any], cfg: dict[str, Any], deadline: float) -> dict[str, Any]:
    store = rt.store()
    tz = rt.settings.timezone or "UTC"
    today = rt.settings.today()
    rep: dict[str, Any] = {"created": 0, "updated": 0, "pulled": 0, "conflicts": 0, "waiting": 0, "failed": 0,
                           "skipped": [], "problems": []}
    changed_paths: list[str] = []

    def left() -> float:
        return deadline - time.monotonic()

    # Scope: approved areas only; identity must be valid and unique.
    scan = store.scan()
    in_scope = [t for t in scan.tasks if t.fm.get("area") in cfg["areas"]]
    ids: dict[str, list[tf.TaskDoc]] = {}
    for t in in_scope:
        if t.task_id:
            ids.setdefault(t.task_id, []).append(t)
    dupes = {tid for tid, docs in ids.items() if len(docs) > 1}
    for tid in dupes:
        rep["problems"].append(f"task ID {tid[:8]} is used by {len(ids[tid])} files; run \"check my task files\"")
    by_id = {tid: docs[0] for tid, docs in ids.items() if tid not in dupes}
    no_id = [t.title for t in in_scope if not t.task_id]
    if no_id:
        rep["problems"].append(f"{len(no_id)} task(s) have no ID yet and were skipped (say \"fix my task files\")")

    # 1. Resume phone operations sent earlier.
    in_flight = 0
    for key, op in list(st["ops"].items()):
        if op.get("state") == "uncertain":
            continue
        fenced = op["task_id"] not in by_id or op["args"].get("device_id") != cfg["device_id"]
        if op.get("state") == "dispatching" and fenced:  # scope or phone changed: never re-send
            op["state"] = "uncertain" if op["kind"] == "create" else "dropped"
            rep["skipped"].append(f"\"{op.get('title')}\": no longer in sync scope, so an unsent change was dropped")
            continue
        if op.get("state") == "dispatching":  # crashed between recording and learning the request ID
            if time.time() - op["created"] > UNKNOWN_DISPATCH_MAX_AGE:
                op["state"] = "uncertain" if op["kind"] == "create" else "dropped"
                continue
            resp = _call(rt, op["tool"], {**op["args"], "wait_seconds": 0})  # same key: returns the original request
        else:
            resp = _call(rt, "mobile_request_result", {"request_id": op["request_id"], "wait_seconds": 0})
        _settle(rt, st, key, op, resp, rep, by_id, changed_paths, store, tz)
        if op.get("state") in ("sent", "dispatching"):
            in_flight += 1
    st["ops"] = {k: v for k, v in st["ops"].items() if v.get("state") not in ("done", "dropped")}

    # 2. Read the list (incomplete, then completed since the oldest mapping), resuming a pending read.
    remote, complete = _read_list(rt, st, cfg, rep, left)
    if not complete:
        rep["waiting"] += 1
        save(rt, st, keep_disk_config=True)
        return _finish(rt, st, rep, changed_paths, waiting=True)

    # 3. Recover uncertain creates by their marker; never guess from titles.
    by_marker = {rm.marker_task_id(r.get("notes")): r for r in remote.values() if rm.marker_task_id(r.get("notes"))}
    for key, op in list(st["ops"].items()):
        if op.get("state") == "uncertain" and op["kind"] == "create":
            found = by_marker.get(op["task_id"])
            if found and op["task_id"] not in st["mappings"]:
                doc = by_id.get(op["task_id"])
                st["mappings"][op["task_id"]] = _mapping(cfg, found, rm.remote_projection(found, tz)[0], doc)
                st["ops"].pop(key)
            elif found:
                st["ops"].pop(key)
            else:
                rep["problems"].append(f"\"{op['title']}\": a reminder may or may not have been created earlier. "
                                       "Check the phone; if it is not there, say so and it will be created.")

    # 4. Reconcile mapped tasks.
    for tid, m in list(st["mappings"].items()):
        doc = by_id.get(tid)
        if doc is None:
            if tid not in dupes and not any(t.task_id == tid for t in scan.tasks):
                rep["skipped"].append(f"{m.get('title', tid[:8])}: task file not found (left the reminder alone)")
            continue
        rem = remote.get(m["reminder_id"])
        if rem is None:
            rep["skipped"].append(f"{doc.title}: its reminder was not found (deleted or moved?); nothing changed")
            continue
        if rem.get("list_id") != m["list_id"]:
            rep["skipped"].append(f"{doc.title}: its reminder moved to another list; left alone")
            continue
        if doc.status in ("cancelled", "canceled"):
            rep["skipped"].append(f"{doc.title}: cancelled here; its reminder is left as it is")
            continue
        if any(op.get("task_id") == tid for op in st["ops"].values()):
            continue  # a change for this task is still on its way
        local = rm.local_projection(doc.fm)
        native, extras = rm.remote_projection(rem, tz)
        res = rm.reconcile(m["base"], local, native)
        for f, v in res["adopt"].items():
            m["base"][f] = v
        if res["conflicts"]:
            st["conflicts"][tid] = {**st["conflicts"].get(tid, {}), **res["conflicts"], "_title": doc.title}
            rep["conflicts"] += 1
        else:
            st["conflicts"].pop(tid, None)
        if extras.get("native_due"):
            m["native_due"] = extras["native_due"]
        else:
            m.pop("native_due", None)
        if res["pull"]:
            if _pull(rt, store, doc, m, res["pull"], extras, rep, changed_paths, tz):
                rep["pulled"] += 1
        if res["push"] and left() > 2 and in_flight < MAX_IN_FLIGHT and rep["updated"] + rep["created"] < MAX_WRITES:
            if "due" in res["push"] and m.get("native_due"):
                what = "the new date" if res["push"]["due"] else "no date"
                rep["skipped"].append(f"{doc.title}: replaced the reminder's time ({m.pop('native_due')}) with {what}")
            in_flight += _push(rt, st, cfg, tid, m, res["push"], rep, left)

    # 5. Create reminders for open tasks without one.
    pending_creates = {op["task_id"] for op in st["ops"].values() if op["kind"] == "create"}
    for tid, doc in by_id.items():
        if tid in st["mappings"] or tid in pending_creates:
            continue
        ok, why = rm.eligible_for_create(doc.fm, today)
        if not ok:
            continue
        existing = by_marker.get(tid)
        if existing:  # created earlier but our record was lost: adopt it instead of making another
            st["mappings"][tid] = _mapping(cfg, existing, rm.remote_projection(existing, tz)[0], doc)
            rep["skipped"].append(f"{doc.title}: found its existing reminder and linked it again")
            continue
        if left() <= 2 or in_flight >= MAX_IN_FLIGHT or rep["updated"] + rep["created"] >= MAX_WRITES:
            rep["skipped"].append("more reminders to create; run /task ios again")
            break
        fresh = tf.parse_file(doc.path, rt=False)  # recheck status and cutoff right before sending
        if not rm.eligible_for_create(fresh.fm, today)[0]:
            continue
        in_flight += _create(rt, st, cfg, fresh, rep, left)

    return _finish(rt, st, rep, changed_paths)


def _mapping(cfg: dict[str, Any], rem: dict[str, Any], projection: dict[str, Any], doc: Any) -> dict[str, Any]:
    return {"reminder_id": rem["id"], "list_id": rem.get("list_id") or cfg["list_id"], "device_id": cfg["device_id"],
            "base": projection, "title": projection["title"], "created_at": time.time(),
            "prior_status": str(doc.fm.get("status")) if doc is not None else "open"}


def _read_list(rt: Runtime, st: dict[str, Any], cfg: dict[str, Any], rep: dict[str, Any], left) -> tuple[dict, bool]:
    remote: dict[str, dict[str, Any]] = {}
    oldest = min((m.get("created_at", time.time()) for m in st["mappings"].values()), default=time.time())
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(oldest - 86400))
    for phase in ("incomplete", "completed"):
        if phase == "completed" and not st["mappings"] and not st["ops"]:
            continue
        offset = 0
        while True:
            key = f"{phase}:{offset}"
            pending = st["reads"].get(key)
            if pending:
                resp = _call(rt, "mobile_request_result", {"request_id": pending, "wait_seconds": min(20, max(0, left()))})
            else:
                args = _phone_args(cfg, list_ids=[cfg["list_id"]], status=phase, limit=100, offset=offset,
                                   wait_seconds=min(20, max(0, left())))
                if phase == "completed":
                    args["completed_start"] = start
                resp = _call(rt, "mobile_reminders_list", args)
            status = resp.get("status")
            if status in ("pending", "running"):
                st["reads"][key] = resp.get("id")
                return remote, False
            st["reads"].pop(key, None)
            if status != "succeeded":
                rep["problems"].append(f"reading Reminders failed ({status}: {resp.get('error', '')})"[:200])
                return remote, False
            data = _data(resp)
            for r in data.get("reminders") or []:
                if r.get("list_id") == cfg["list_id"]:
                    remote[r["id"]] = r
            nxt = data.get("next_offset")
            if nxt in (None, "") or int(nxt) <= offset:
                break
            offset = int(nxt)
    return remote, True


def _send(rt: Runtime, st: dict[str, Any], op: dict[str, Any], left) -> dict[str, Any]:
    """Record the operation durably, then send it. Returns the phone's response."""
    st["ops"][op["key"]] = op
    save(rt, st, keep_disk_config=True)
    resp = _call(rt, op["tool"], {**op["args"], "wait_seconds": min(10, max(0, left() - 1))})
    if resp.get("id"):
        op["request_id"] = resp["id"]
    op["state"] = "sent" if op.get("request_id") else "dispatching"
    save(rt, st, keep_disk_config=True)
    return resp


def _push(rt, st, cfg, tid, m, push, rep, left) -> int:
    fields, completion = rm.update_args(push)
    sent = 0
    if fields or completion is False:
        args = _phone_args(cfg, id=m["reminder_id"], **fields)
        if completion is False:
            args["completed"] = False
        op = {"kind": "update", "task_id": tid, "tool": "mobile_reminder_update", "created": time.time(),
              "push": push, "title": m.get("title")}
        op["key"] = args["idempotency_key"] = _key("update", tid, m["reminder_id"], fields, completion, uuid.uuid4().hex)
        op["args"] = args
        resp = _send(rt, st, op, left)
        _settle(rt, st, op["key"], op, resp, rep, None, None, None, None)
        sent += op.get("state") == "sent"
    if completion is True:
        args = _phone_args(cfg, id=m["reminder_id"])
        op = {"kind": "complete", "task_id": tid, "tool": "mobile_reminder_complete", "created": time.time(),
              "push": {"completed": True}, "title": m.get("title")}
        op["key"] = args["idempotency_key"] = _key("complete", tid, m["reminder_id"], uuid.uuid4().hex)
        op["args"] = args
        resp = _send(rt, st, op, left)
        _settle(rt, st, op["key"], op, resp, rep, None, None, None, None)
        sent += op.get("state") == "sent"
    st["ops"] = {k: v for k, v in st["ops"].items() if v.get("state") not in ("done", "dropped")}
    return sent


def _create(rt, st, cfg, doc, rep, left) -> int:
    local = rm.local_projection(doc.fm)
    attempt = (st["notes"].get("attempts") or {}).get(doc.task_id, 0)
    args = _phone_args(cfg, title=local["title"], list_id=cfg["list_id"], priority="none",
                       notes=rm.marker(doc.task_id), due_date=local["due"] or None)
    op = {"kind": "create", "task_id": doc.task_id, "tool": "mobile_reminder_create", "created": time.time(),
          "title": local["title"], "projection": local, "prior_status": str(doc.fm.get("status"))}
    op["key"] = args["idempotency_key"] = _key("create", doc.task_id, cfg["list_id"], attempt)
    op["args"] = args
    resp = _send(rt, st, op, left)
    _settle(rt, st, op["key"], op, resp, rep, None, None, None, None)
    st["ops"] = {k: v for k, v in st["ops"].items() if v.get("state") not in ("done", "dropped")}
    return 1 if st["ops"].get(op["key"], {}).get("state") == "sent" else 0


def _settle(rt, st, key, op, resp, rep, by_id, changed_paths, store, tz) -> None:
    """Advance an operation from the phone's answer. Success needs the phone's own readback of the reminder."""
    status = resp.get("status")
    if resp.get("id") and not op.get("request_id"):
        op["request_id"] = resp["id"]
        op["state"] = "sent"
    if not resp.get("id") and not op.get("request_id") and status == "unavailable":
        op["state"] = "dropped"  # refused before it was recorded: no key used, nothing ran
        rep["failed"] += 1
        rep["unavailable"] = str(resp.get("message") or resp.get("error") or "Reminders access is not available")
        return
    if not resp.get("id") and not op.get("request_id") and status != "no_connector":
        # No answer at all: the phone may or may not have it. Keep the same key; re-sending returns the
        # original request instead of making a second one.
        op["state"] = "dispatching"
        rep["waiting"] += 1
        return
    if op.get("request_id") and resp.get("id") != op["request_id"] and "not found" not in str(resp.get("error")):
        rep["waiting"] += 1  # could not read the request's state this time; it may still run. Ask again later.
        rep["problems"].append(f"\"{op.get('title')}\": could not check on the phone right now")
        return
    if status in ("pending", "running"):
        rep["waiting"] += 1
        return
    if status == "no_connector":
        op["state"] = "dropped" if op["kind"] != "create" else "uncertain"
        rep["problems"].append("the mobile connector is not available right now")
        return
    if status != "succeeded":
        if op["kind"] == "create" and status in ("expired", "cancelled") or (status == "failed" and
                                                                            "not found" in str(resp.get("error"))):
            op["state"] = "uncertain" if op["kind"] == "create" else "dropped"
        else:
            op["state"] = "dropped"  # a definite failure: recomputed from fresh state next time
            if op["kind"] == "create":  # a fresh attempt needs a fresh key (the old key returns this failure)
                attempts = st["notes"].setdefault("attempts", {})
                attempts[op["task_id"]] = attempts.get(op["task_id"], 0) + 1
        rep["failed"] += 1
        rep["problems"].append(f"\"{op.get('title')}\": phone reported {status}"
                               + (f" ({str(resp.get('error'))[:120]})" if resp.get("error") else ""))
        return
    data = _data(resp)
    cfg = st["config"]
    if op["kind"] == "create":
        if not data.get("id") or data.get("list_id") != cfg.get("list_id"):
            op["state"] = "uncertain"
            rep["problems"].append(f"\"{op['title']}\": the phone's answer did not match the chosen list")
            return
        projection, _ = rm.remote_projection(data, rt.settings.timezone or "UTC")
        st["mappings"][op["task_id"]] = {"reminder_id": data["id"], "list_id": data["list_id"],
                                         "device_id": cfg["device_id"], "base": projection, "title": op["title"],
                                         "created_at": time.time(), "prior_status": op.get("prior_status", "open")}
        rep["created"] += 1
    else:
        m = st["mappings"].get(op["task_id"])
        if m is not None:
            projection, _ = rm.remote_projection(data, rt.settings.timezone or "UTC")
            verified = {f: v for f, v in op["push"].items() if projection.get(f) == v}
            m["base"].update(verified)  # advance only what the phone confirmed
            if len(verified) < len(op["push"]):
                rep["problems"].append(f"\"{op.get('title')}\": the phone did not confirm every change")
        rep["updated"] += 1
    op["state"] = "done"


def _pull(rt, store, doc, m, pull, extras, rep, changed_paths, tz) -> bool:
    changes: dict[str, Any] = {}
    notes = []
    if "title" in pull and pull["title"]:
        changes["title"] = pull["title"]
        notes.append("title")
    if "due" in pull:
        if pull["due"]:
            changes["due"] = pull["due"]
        else:
            changes["due"], changes["undated"] = "none", True
        notes.append("date")
    if "completed" in pull:
        if pull["completed"]:
            day = rm.completed_date(extras.get("completed_at"), tz)
            if not day:
                rep["problems"].append(f"{doc.title}: checked off in Reminders, but the phone gave no completion "
                                       "date; mark it done yourself to confirm")
                pull = {k: v for k, v in pull.items() if k != "completed"}
            else:
                m["prior_status"] = str(doc.fm.get("status") or "open")
                changes.update(status="done", completed=day)
                notes.append("completion")
        else:
            prior = m.get("prior_status") or "open"
            if prior not in ("open", "in-progress"):
                if prior == "waiting":
                    rep["skipped"].append(f"{doc.title}: reopened as open (it was waiting before; say what it is "
                                          "waiting on to set that again)")
                prior = "open"
            changes.update(status=prior, reopen=True)
            notes.append("reopened")
    if not changes:
        return False
    changes["log"] = "Changed in Apple Reminders: " + ", ".join(notes) + "."
    try:
        _, paths, _ = store.update(doc.task_id, changes, expect_revision=tf.content_hash(doc.raw))
    except tf.ConcurrentEditError:
        rep["skipped"].append(f"{doc.title}: edited here while syncing; will reconcile next time")
        return False
    except NeedsInput as exc:
        rep["problems"].append(f"{doc.title}: {exc.message}")
        return False
    for f in ("title", "due", "completed"):
        if f in pull:
            m["base"][f] = pull[f]
    m["title"] = changes.get("title", m.get("title"))
    changed_paths.extend(paths)
    return True


def _finish(rt: Runtime, st: dict[str, Any], rep: dict[str, Any], changed_paths: list[str], waiting: bool = False):
    if changed_paths:
        rep["git"] = rt.git().deliver(sorted(set(changed_paths)), "task: changes from Apple Reminders")
    st["last_sync"] = {"at": time.time(), "created": rep["created"], "updated": rep["updated"],
                       "pulled": rep["pulled"], "waiting": rep["waiting"]}
    save(rt, st, keep_disk_config=True)
    parts = []
    if rep["created"]:
        parts.append(f"{rep['created']} reminder(s) created")
    if rep["updated"]:
        parts.append(f"{rep['updated']} updated on the phone")
    if rep["pulled"]:
        parts.append(f"{rep['pulled']} task(s) updated from reminder changes")
    if rep["conflicts"]:
        parts.append(f"{rep['conflicts']} conflict(s) need a choice")
    pending = sum(1 for op in st["ops"].values() if op.get("state") in ("sent", "dispatching"))
    git = rep.get("git") or {}
    git_bad = bool(git) and not git.get("pushed") and git.get("state") not in ("local_only", "no_git")
    if git_bad:
        done = "saved and committed" if git.get("committed") else "saved"
        parts.append(f"task changes {done} but not pushed ({git.get('error') or git.get('state')})")
    uncertain = [op["title"] for op in st["ops"].values() if op.get("state") == "uncertain"]
    if rep.get("unavailable"):
        parts.append(f"the iPhone refused: {rep['unavailable']}")
    if waiting or pending:
        parts.append(WAITING)
    elif not parts and not rep["problems"] and not uncertain:
        parts.append("Everything already matches")
    elif not parts:
        parts.append("nothing changed, but see the notes below")
    rep["pending"] = pending
    rep["message"] = "Reminders: " + "; ".join(parts) + "."
    rep["synced"] = not waiting and not pending and not rep["failed"] and not git_bad and not uncertain \
        and not rep["conflicts"]
    return rep
