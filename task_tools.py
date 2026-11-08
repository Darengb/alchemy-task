"""Agent-facing task tools: task_create, task_update, task_find."""
from __future__ import annotations

import json
import time
from typing import Any

from .core import taskfile as tf
from .core.config import ConfigError
from .core.locks import LockTimeout
from .core.store import NeedsInput
from .runtime import Runtime

TOOLSET = "alchemy-task"

_STR = {"type": "string"}
_DATE = {"type": "string", "description": "YYYY-MM-DD"}
_LIST = {"type": "array", "items": {"type": "string"}}

CREATE_SCHEMA = {
    "name": "task_create",
    "description": (
        "Create a task in the user's Alchemy Task workspace. Use this for every new task instead of writing "
        "files. It checks for duplicates, files the task in its area, commits and pushes it, and queues "
        "background research. If the result has ok=false with a 'needs' field, ask the user or fix the call "
        "as the message says, then call again."),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short imperative title, cleaned up from the user's wording."},
            "summary": {"type": "string", "description": "One or two plain sentences: what this is and why it matters "
                                                        "(who asked, what done looks like). Shown in Reminders and lists."},
            "area": {"type": "string", "description": "Area slug. Infer from context when clear; omit to get the list."},
            "due": {"type": "string", "description": "Deadline: YYYY-MM-DD, or words like 'Friday', 'tomorrow', 'Nov 13'. Required unless undated."},
            "undated": {"type": "boolean", "description": "True only if the user explicitly said this task has no due date."},
            "scheduled": {"type": "string", "description": "Only if the user names a different work day than the due date; otherwise it equals due."},
            "priority": {"type": "string", "enum": list(tf.PRIORITIES)},
            "project": {"type": "string", "description": "Optional project link or slug."},
            "notes": {"type": "string", "description": "Context: why it matters, links, what the user said. Markdown."},
            "plan": {"type": "string", "description": "Optional work breakdown (Markdown) for multi-step work."},
            "subtasks": {**_LIST, "description": "Optional real child steps (never repeat the task title)."},
            "contexts": {**_LIST, "description": "Optional contexts such as @computer."},
            "estimate": {"type": "string", "description": "Optional estimate such as 30m or 2h."},
            "tags": {**_LIST, "description": "Optional extra tags."},
            "research": {"type": "boolean", "description": "Default true. False only when the user says no research is needed."},
            "research_skip_reason": _STR,
            "confirm_new": {"type": "boolean", "description": "True only after a duplicate check, when the user confirmed this is different work."},
            "create_area": {"type": "boolean", "description": "True only when the user confirmed creating a new area."},
            "status": {"type": "string", "enum": ["open", "in-progress", "waiting"]},
            "source": {"type": "string", "description": "Where the request came from, e.g. 'Telegram' or 'email from Sam'."},
        },
        "required": ["title"],
    },
}

UPDATE_SCHEMA = {
    "name": "task_update",
    "description": (
        "Change an existing task: status, dates, priority, title, area, notes. Dates: due and scheduled are one "
        "date unless the user asks for different ones, so 'move X to Friday' or 'X is now due Friday' sets both; "
        "pass both (or keep_separate) only for 'due Friday, I'll do it Tuesday'. Changes only the fields you pass "
        "and appends a dated log line. Marking done sets the completed date. Reopening a done or cancelled task "
        "needs reopen=true. Cancelled and waiting need a reason. Use this instead of editing task files."),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "task_id (preferred, from task_find), workspace path or exact title."},
            "status": {"type": "string", "enum": list(tf.STATUSES)},
            "reason": {"type": "string", "description": "Why cancelled, or what/whom it is waiting on."},
            "reopen": {"type": "boolean"},
            "completed": {**_DATE, "description": "Completion date if not today."},
            "title": _STR,
            "summary": {"type": "string", "description": "Replace the one- or two-sentence summary."},
            "rename_file": {"type": "boolean", "description": "Also rename the file to match a new title."},
            "due": {"type": "string", "description": "New deadline: YYYY-MM-DD or words ('Friday', 'Nov 13'); 'none' clears it (needs undated=true)."},
            "undated": {"type": "boolean"},
            "keep_separate": {"type": "boolean", "description": "Only when the user explicitly wants the due date and "
                                                               "the work day to differ; otherwise one change moves both."},
            "scheduled": {"type": "string", "description": "New planned day: YYYY-MM-DD or words ('tomorrow', 'next Monday'); 'none' clears it."},
            "priority": {"type": "string", "enum": list(tf.PRIORITIES)},
            "project": _STR,
            "estimate": _STR,
            "area": {"type": "string", "description": "Move the task to another known area."},
            "contexts": _LIST,
            "tags_add": _LIST,
            "tags_remove": _LIST,
            "notes_append": {"type": "string", "description": "Text to add at the end of the Notes section."},
            "log": {"type": "string", "description": "What changed and why, in one sentence (recommended)."},
        },
        "required": ["task"],
    },
}

FIND_SCHEMA = {
    "name": "task_find",
    "description": (
        "Look up tasks in the user's Alchemy Task workspace by title words, task_id, area, status or due "
        "date. Use it before creating a task (to avoid duplicates) and to get the task_id for task_update. "
        "Set include_body=true for one task to read its notes, research and current state. For \"today's "
        "tasks\", \"this week\", \"tasks for Monday\", \"what's overdue\": pass period (today, this_week, monday, ...) "
        "to get open tasks scheduled or due then, plus overdue ones, each with the reason. For other ranges pass "
        "agenda_from and agenda_to."),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words from the title."},
            "task_id": _STR,
            "area": _STR,
            "status": {"type": "string", "description": "open (default: not done/cancelled), closed, any, or one status."},
            "due_before": _DATE,
            "due_after": _DATE,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "include_body": {"type": "boolean"},
            "period": {"type": "string", "enum": ["today", "tomorrow", "this_week", "next_week", "overdue", "monday",
                                                   "tuesday", "wednesday", "thursday", "friday", "saturday",
                                                   "sunday"],
                       "description": "Agenda for a spoken period, computed in the user's timezone (preferred over "
                                      "agenda_from/agenda_to). A weekday means the next one, or today."},
            "agenda_from": {**_DATE, "description": "Agenda: first day (YYYY-MM-DD)."},
            "agenda_to": {**_DATE, "description": "Agenda: last day; omit for a single day."},
            "include_overdue": {"type": "boolean", "description": "Agenda: also list overdue tasks (default true)."},
        },
        "required": [],
    },
}


def _ok(**data: Any) -> str:
    return json.dumps({"ok": True, **data}, ensure_ascii=False, default=str)


def _fail(kind: str, message: str, **data: Any) -> str:
    return json.dumps({"ok": False, "needs": kind, "message": message, **data}, ensure_ascii=False, default=str)


def _guard(fn):
    def wrapper(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
        try:
            if fn.__name__ != 'task_find' and kwargs.get('session_id'):
                from .discovery_integration import get_service
                service = get_service(Runtime())
                if service.runner._child_for(kwargs.get('session_id', ''), kwargs.get('task_id', '')):
                    return _fail('discovery', 'Discovery research is read-only; no task or integration mutations.')
            return fn(dict(args or {}), **kwargs)
        except NeedsInput as exc:
            return _fail(exc.kind, exc.message, **exc.data)
        except (ConfigError, tf.TaskFormatError) as exc:
            return _fail("fix_call" if isinstance(exc, tf.TaskFormatError) else "setup", str(exc))
        except tf.ConcurrentEditError as exc:
            return _fail("retry", f"{exc}. Read it again with task_find and retry.")
        except LockTimeout as exc:
            return _fail("retry", f"The task is busy ({exc}). Retry in a moment.")
        except (ValueError, TypeError) as exc:
            return _fail("fix_call", f"Invalid argument: {exc}")
        except OSError as exc:
            return _fail("retry", f"File system error: {exc.__class__.__name__}: {exc}")
    wrapper.__name__ = fn.__name__
    return wrapper


def _git_note(receipt: dict[str, Any]) -> str:
    if receipt.get("pushed"):
        return "Saved, committed and pushed."
    state = receipt.get("state")
    if state == "local_only":
        return "Saved and committed locally (no Git remote configured)."
    if state == "no_git":
        return "Saved (the workspace is not a Git repository)."
    if receipt.get("committed") or state in ("push_pending", "diverged", "blocked"):
        return f"Saved and committed; push pending: {receipt.get('error', 'will retry')}."
    return f"Saved; Git delivery problem: {receipt.get('error', 'unknown')}."


@_guard
def task_create(args: dict[str, Any], session_id: str = "", **_: Any) -> str:
    rt = Runtime()
    store = rt.store()
    doc = store.create(
        title=args.get("title", ""), area=args.get("area", ""), due=args.get("due", ""),
        undated=bool(args.get("undated")), scheduled=args.get("scheduled", ""),
        priority=args.get("priority", "normal"), project=args.get("project", ""), notes=args.get("notes", ""),
        plan=args.get("plan", ""), subtasks=args.get("subtasks"), contexts=args.get("contexts"),
        estimate=args.get("estimate", ""), tags=args.get("tags"), research=args.get("research"),
        summary=args.get("summary", ""),
        research_skip_reason=args.get("research_skip_reason", ""), confirm_new=bool(args.get("confirm_new")),
        create_area=bool(args.get("create_area")), status=args.get("status", "open"),
        source=args.get("source", ""))
    receipt = rt.git().deliver([store.rel(doc.path)], f"task: create {doc.title[:72]}")
    research = (doc.fm.get("enrichment") or {}).get("status")
    research_errors = rt.notify_research(doc, session_id or "") if research == "pending" else []
    summary = store.summary(doc)
    msg = f"Created \"{doc.title}\" in {summary['area']}, due {summary['due'] or 'undated'}. {_git_note(receipt)}"
    others = [a for a in rt.settings.known_areas() if a != summary["area"]]
    if not args.get("area") and others:
        msg += (f" No area was given, so it went to the default area ({summary['area']}). If it fits "
                f"{', '.join(others)} better, move it with task_update area=... and tell the user.")
    if research == "pending" and not research_errors:
        msg += " Background research has started; results are added to the task and you will hear when it is done."
    elif research == "pending":
        msg += " Research is queued and will start on the next research sweep."
    return _ok(task=summary, git=receipt, research=research, research_errors=research_errors or None, message=msg)


_UPDATE_KEYS = ("status", "reason", "reopen", "completed", "title", "summary", "rename_file", "due", "undated", "scheduled",
                "keep_separate",
                "priority", "project", "estimate", "area", "contexts", "tags_add", "tags_remove", "notes_append", "log")


@_guard
def task_update(args: dict[str, Any], **_: Any) -> str:
    rt = Runtime()
    store = rt.store()
    changes = {k: args[k] for k in _UPDATE_KEYS if k in args}
    doc, paths, notes = store.update(args.get("task", ""), changes)
    if not paths:
        return _ok(task=store.summary(doc), changed=False, message="Nothing changed: the task already had those values.")
    receipt = rt.git().deliver(paths, f"task: update {doc.title[:72]}")
    return _ok(task=store.summary(doc), changed=True, changes=notes, git=receipt,
               message=f"Updated \"{doc.title}\": {'; '.join(notes) or 'log added'}. {_git_note(receipt)}")


@_guard
def task_find(args: dict[str, Any], **_: Any) -> str:
    rt = Runtime()
    store = rt.store()
    if args.get("period") or args.get("agenda_from"):
        period = str(args.get("period") or "").lower()
        if period:
            start, end = store.period_range(period)
        else:
            start, end = args["agenda_from"], args.get("agenda_to") or args["agenda_from"]
        items = store.agenda(start, end, area=args.get("area", ""),
                             include_overdue=args.get("include_overdue", True))
        if period == "overdue":
            items = [(d, why) for d, why in items if why.startswith("overdue")]
        overdue = [(d, w) for d, w in items if w.startswith("overdue")]
        current = [(d, w) for d, w in items if not w.startswith("overdue")]
        cap = 50 if period == "overdue" else 10
        recent_overdue = sorted(overdue, key=lambda x: str(tf.norm_date(x[0].fm.get("due"))), reverse=True)[:cap]
        tasks = [{**store.summary(d), "why": w} for d, w in recent_overdue + current[:150]]
        note = ("Answer briefly: the period's tasks by day (say scheduled or due), then overdue ones. "
                + (f"Only the {cap} most recent of {len(overdue)} overdue tasks are listed; mention the total."
                   if len(overdue) > cap else "")) if tasks else "Nothing scheduled or due then."
        return _ok(period=period or None, start=start, end=end, count=len(current), overdue_total=len(overdue),
                   tasks=tasks, today=rt.settings.today(),
                   weekday=__import__("datetime").date.fromisoformat(rt.settings.today()).strftime("%A"), note=note)
    docs = store.find(query=args.get("query", ""), task_id=args.get("task_id", ""), area=args.get("area", ""),
                      status=args.get("status", "open"), due_before=args.get("due_before", ""),
                      due_after=args.get("due_after", ""), limit=args.get("limit", 20))
    include_body = bool(args.get("include_body")) and len(docs) <= 3
    return _ok(count=len(docs), tasks=[store.summary(d, include_body=include_body) for d in docs],
               today=rt.settings.today(),
               weekday=__import__("datetime").date.fromisoformat(rt.settings.today()).strftime("%A"))


WORK_SCHEMA = {
    "name": "task_work_start",
    "description": (
        "Start or continue working on a task in this chat (the user says \"work on X\", \"continue X\", \"let's "
        "do X\"). Links this chat to the task, marks it in progress and returns everything needed to continue: "
        "notes, research dossier, access plan and the current state with its next step. Then do the work. When it "
        "is finished, needs the user, waits on someone or is blocked, call task_checkpoint."),
    "parameters": {"type": "object", "properties": {
        "task": {"type": "string", "description": "task_id (preferred), path or exact title."}}, "required": ["task"]},
}

CHECKPOINT_SCHEMA = {
    "name": "task_checkpoint",
    "description": (
        "Record where the work on a task stands. Call it when the work is finished, when you need the user, when "
        "it waits on someone else, when it is blocked, or before stopping partway. It rewrites the task's Current "
        "state section, sets the status and logs the step. Marking done requires evidence of what you checked."),
    "parameters": {"type": "object", "properties": {
        "task": {"type": "string", "description": "Optional: defaults to the task this chat is working on."},
        "state": {"type": "string", "enum": ["done", "waiting_user", "waiting_other", "blocked", "in_progress"]},
        "done": {"type": "string", "description": "What was done in this session, concretely."},
        "next_step": {"type": "string", "description": "The next concrete step (required unless done)."},
        "needs_from": {"type": "string", "description": "What is needed and from whom (for waiting or blocked)."},
        "evidence": {"type": "string", "description": "Required for done: what you checked and how (readback, "
                                                      "link, test result)."}},
        "required": ["state", "done"]},
}


@_guard
def task_work_start(args: dict[str, Any], session_id: str = "", **_: Any) -> str:
    from . import worksession
    rt = Runtime()
    out = worksession.start_work(rt, args.get("task", ""), session_id or "")
    t = out["task"]
    state = t.get("current_state")
    msg = (f"{'Continuing' if out['resumed'] else 'Starting'} \"{t['title']}\". "
           + (f"Current state: {state}" if state else "No checkpoint yet; read the notes and research below.")
           + " Do the work now; checkpoint with task_checkpoint when it finishes, needs the user or is blocked.")
    return _ok(**out, message=msg)


@_guard
def task_checkpoint(args: dict[str, Any], session_id: str = "", **_: Any) -> str:
    from . import worksession
    from .core.checkpoint import CheckpointError
    rt = Runtime()
    ref = args.get("task") or worksession.linked_task(rt, session_id or "")
    if not ref:
        return _fail("task", "Which task is this for? Pass task (this chat is not linked to a task; use "
                     "task_work_start to link it).")
    fields = {k: args.get(k) for k in ("state", "done", "next_step", "needs_from", "evidence")}
    try:
        out = worksession.write_checkpoint(rt, ref, fields, session_id=session_id or "")
    except CheckpointError as exc:
        return _fail("checkpoint", str(exc))
    if session_id and not worksession.linked_task(rt, session_id) and out["state"] != "done":
        worksession._update_link(rt, session_id, task_id=out["task"]["task_id"], title=out["task"]["title"],
                                 started=time.time(), last_activity=time.time(),
                                 last_checkpoint=time.time())
    return _ok(**out, message=f"Checkpoint saved: {out['task']['title']} is now {out['task']['status']}. "
               + _git_note(out["git"]))


SETUP_SCHEMA = {
    "name": "task_setup",
    "description": (
        "Set up, check and maintain Alchemy Task (the user never needs slash commands). Actions: status (is "
        "everything working? what is set up? readiness of each part), check_files (check task files for problems; "
        "fix=true also gives hand-made tasks their ID), push (sync now / push waiting changes), inspect, save "
        "(change a setting), git_check, jobs_preview, jobs_create (only after the user approved), teardown "
        "(stop/remove the scheduled jobs; only after the user confirmed). For first-time setup load the skill "
        "alchemy-task:setup."),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["status", "check_files", "push", "inspect", "save", "git_check",
                                              "jobs_preview", "jobs_create", "teardown"]},
        "fix": {"type": "boolean", "description": "check_files: also assign missing task IDs."},
        "user_confirmed": {"type": "boolean", "description": "teardown: true only after the user confirmed."},
        "path": {"type": "string", "description": "inspect: absolute folder path."},
        "workspace_root": {"type": "string"},
        "create_workspace": {"type": "boolean", "description": "save: create a new workspace folder and Git repo."},
        "allow_shared": {"type": "boolean"},
        "task_dir": {"type": "string", "description": "Folder pattern with {area}, default areas/{area}/tasks."},
        "areas": {"type": "array", "items": {"type": "string"}, "description": "Full list (setup). To change one, "
                                                                              "use add_areas / remove_areas."},
        "add_areas": {"type": "array", "items": {"type": "string"}},
        "remove_areas": {"type": "array", "items": {"type": "string"}},
        "default_area": {"type": "string"},
        "timezone": {"type": "string", "description": "IANA name the user confirmed, e.g. America/New_York."},
        "set_hermes_timezone": {"type": "boolean", "description": "Also set Hermes's own timezone (when it was unset)."},
        "research_by_default": {"type": "boolean"},
        "git_transport": {"type": "string", "enum": ["system", "deploy_key", "token", "none"]},
        "git_remote": {"type": "string"},
        "git_branch": {"type": "string"},
        "remote_url": {"type": "string", "description": "git_check: set the remote URL (an empty private repo)."},
        "replace_remote": {"type": "boolean", "description": "git_check: change an existing remote (user asked)."},
        "user_approved": {"type": "boolean", "description": "jobs_create: true only after the user said yes."}},
        "required": ["action"]},
}


@_guard
def task_setup(args: dict[str, Any], session_id: str = "", **_: Any) -> str:
    from . import setup_flow as sf
    rt = Runtime()
    action = args.get("action")
    try:
        if action == "status":
            rep = sf.status(rt)
            return _ok(receipt=rep, text=sf.receipt_text(rep))
        if action == "inspect":
            return _ok(**sf.inspect_workspace(args.get("path", ""), args.get("task_dir", "")))
        if action == "save":
            out = sf.save(rt, args)
            rep = sf.status(Runtime())
            return _ok(**out, receipt=rep, text=sf.receipt_text(rep))
        if action == "git_check":
            return _ok(**sf.git_check(rt, args))
        if action == "jobs_preview":
            return _ok(**sf.jobs_preview(rt))
        if action == "jobs_create":
            return _ok(**sf.jobs_create(rt, user_approved=bool(args.get("user_approved")), session_id=session_id))
        if action == "check_files":
            from .core import validator
            report = validator.validate(rt.store(), apply=bool(args.get("fix")))
            receipt = rt.git().deliver(report["changed_paths"], "task: assign missing task IDs") \
                if report["changed_paths"] else None
            details = {k: report[k][:20] for k in ("unsupported", "malformed", "unknown_status",
                                                   "done_without_completed", "area_mismatch", "needs_identity")
                       if report[k]}
            return _ok(summary=validator.summarize(report), problems=details,
                       duplicate_task_ids=report["duplicate_task_ids"] or None, git=receipt)
        if action == "push":
            r = rt.git().retry()
            msg = "Everything is pushed; the remote is up to date." if r.get("pushed") else \
                f"Not pushed ({r.get('state')}): {r.get('error') or r.get('note') or 'no details'}"
            return _ok(**r, message=msg)
        if action == "teardown":
            if not args.get("user_confirmed"):
                return _fail("confirm", "Removing the scheduled jobs stops the research sweep, the hourly check and "
                             "every discovery stream (task files and settings stay). Ask the user to confirm, then call "
                             "again with user_confirmed=true.")
            return _ok(**sf.teardown(rt))
    except sf.SetupError as exc:
        return _fail("setup", str(exc))
    return _fail("fix_call", "unknown action")


_SOURCE = {"type": "object", "properties": {
    "name": {"type": "string", "description": "Short label, e.g. 'Work email' or 'Team Slack'."},
    "type": {"type": "string", "enum": ["email", "chat", "transcript", "meeting_notes", "document", "tracker", "other"]},
    "scope": {"type": "string", "description": "Exactly what to read: label, channels, sender filter, folder."},
    "toolsets": {"type": "array", "items": {"type": "string"}, "description": "Actual currently available toolsets exposing this approved reader; inherited by research children."},
    "method": {"type": "string", "description": "Which tool or skill reads it (e.g. gmail MCP, slack skill)."}},
    "required": ["name", "type", "scope", "method"]}

DISCOVERY_STREAM_SCHEMA = {
    "name": "discovery_stream",
    "description": (
        "Manage discovery streams (load skill alchemy-task:discovery first). A stream reads approved sources on a "
        "schedule and posts numbered task suggestions into the chat it was created in. Actions: list, create "
        "(call from the chat that should receive the digest, after the user approved), update (change one thing: "
        "frequency, time, areas, research_cap, add_sources, remove_sources; the rest stays), remove, "
        "run_now (start the stream's job immediately)."),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["list", "create", "update", "remove", "run_now"]},
        "name": {"type": "string", "description": "Stream name, e.g. 'work'."},
        "areas": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": _SOURCE, "description": "create: all sources. update: replaces the "
                                                                       "whole list; prefer add_sources/remove_sources."},
        "add_sources": {"type": "array", "items": _SOURCE, "description": "update: add (or replace by name) sources, "
                                                                          "keeping the others."},
        "remove_sources": {"type": "array", "items": {"type": "string"}, "description": "update: source names to drop."},
        "frequency": {"type": "string", "enum": ["daily", "weekdays", "hourly", "every 2 hours", "every 3 hours",
                                                 "every 4 hours"]},
        "time": {"type": "string", "description": "Local time for daily/weekdays, e.g. '6 PM'."},
        "deliver": {"type": "string", "description": "Default origin (this chat). For a Telegram topic: "
                                                     "telegram:<chat_id>:<thread_id>."},
        "research_cap": {"type": "integer", "description": "Candidates researched per day (default 50)."},
        "user_approved": {"type": "boolean"}},
        "required": ["action"]},
}

DISCOVERY_START_SCHEMA = {
    "name": "discovery_start",
    "description": "Discovery runs only: get a stream's approved sources, time window, research budget, already "
                   "proposed source IDs and open tasks, before reading the sources.",
    "parameters": {"type": "object", "properties": {"stream": {"type": "string"}}, "required": ["stream"]},
}

DISCOVERY_SUBMIT_SCHEMA = {
    "name": "discovery_submit",
    "description": "Compatibility alias for immutable discovery_digest preparation. Requires full research/global join and post-join decisions; freeform candidates/research_notes are rejected.",
    "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}, "stream": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
}

DISCOVERY_DECIDE_SCHEMA = {
    "name": "discovery_decide",
    "description": (
        "Act on a discovery digest reply: approve the numbers the user wants as tasks. Users usually name only "
        "the ones they want; the rest need no action. Example: \"1 and 3, 3 for Friday\" -> approve [\"1\",\"3\"] "
        "with edits {\"3\": {\"due\": \"YYYY-MM-DD\"}}. Numbers restart each day; pass day for an earlier digest."),
    "parameters": {"type": "object", "properties": {
        "stream": {"type": "string", "description": "Optional when only one stream has recent digests."},
        "day": {"type": "string", "description": "Which day's numbering: omit for today's (or the latest digest), "
                                                 "'yesterday', or YYYY-MM-DD."},
        "approve": {"type": "array", "items": {"type": "string"}},
        "dismiss": {"type": "array", "items": {"type": "string"}},
        "edits": {"type": "object", "description": "{\"1\": {\"due\": \"2026-11-20\", \"area\": \"work\", "
                                                   "\"title\": \"...\", \"undated\": false}}"}},
        "required": []},
}


def _discovery(fn):
    @_guard
    def wrapper(args: dict[str, Any], session_id: str = "", **_: Any) -> str:
        from .discovery import DiscoveryError
        from .core.discovery_identity import UserError
        try:
            return fn(args, session_id)
        except (DiscoveryError, UserError) as exc:
            return _fail("discovery", str(exc))
    wrapper.__name__ = fn.__name__
    return wrapper


@_discovery
def discovery_stream(args: dict[str, Any], session_id: str) -> str:
    from . import discovery as dv
    rt = Runtime()
    action = args.get("action")
    if action == "list":
        return _ok(streams=[dv._public(s) for s in dv._streams(rt).values()])
    if action == "create":
        return _ok(**dv.create_stream(rt, args, session_id))
    if action == "update":
        return _ok(**dv.update_stream(rt, args, session_id))
    if action == "remove":
        return _ok(**dv.remove_stream(rt, args.get("name", "")))
    if action == "run_now":
        s = dv._get(rt, args.get("name", ""))
        out = rt.ctx.dispatch_tool("cronjob_manage", {"action": "run", "job_id": s["job_id"]})
        return _ok(started=True, detail=str(out)[:300], message="Started; the digest arrives in its chat shortly.")
    return _fail("fix_call", "unknown action")


@_discovery
def discovery_start(args: dict[str, Any], session_id: str) -> str:
    from . import discovery as dv
    return _ok(**dv.start(Runtime(), args.get("stream", ""), session_id=session_id))


@_discovery
def discovery_submit(args: dict[str, Any], session_id: str) -> str:
    from . import discovery as dv
    out = dv.submit(Runtime(), args.get("stream", ""), args.get("candidates"), args.get("coverage"),
                    run_id=args.get("run_id", ""), session_id=session_id)
    return _ok(**out)


@_discovery
def discovery_decide(args: dict[str, Any], session_id: str) -> str:
    from . import discovery as dv
    # Discovery promotes EXACT accepted research; never launch generic research.
    return _ok(**dv.decide(Runtime(), args, session_id))


IOS_SCHEMA = {
    "name": "task_ios",
    "description": (
        "Optional Apple Reminders sync through the Hermes mobile app (beta). Use for /task ios, \"sync reminders\", "
        "\"sync iOS\", \"sync my iPhone\". Actions: sync (default: runs or resumes the sync; works only while the "
        "Hermes app is open on the phone), setup (choose areas and list; preview first, then user_approved=true), "
        "status, disable, resolve (settle a conflict: choices {field: local|native}), confirm_missing (the user "
        "checked the phone and a task's reminder is not there, so it may be created). Report what the tool says; "
        "never say synced while it says waiting."),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["sync", "setup", "status", "disable", "resolve", "confirm_missing"]},
        "areas": {"type": "array", "items": {"type": "string"}, "description": "setup: areas whose tasks to mirror."},
        "list": {"type": "string", "description": "setup: an existing Reminders list by name (default: the phone's "
                                                  "default list)."},
        "device_id": {"type": "string"},
        "user_approved": {"type": "boolean"},
        "user_approved_change": {"type": "boolean", "description": "setup: the user approved changing device, list "
                                                                  "or adding areas."},
        "task": {"type": "string"},
        "choices": {"type": "object", "description": "resolve: {\"title\": \"local\", \"due\": \"native\"}"}},
        "required": []},
}


@_guard
def task_ios(args: dict[str, Any], **_: Any) -> str:
    from . import ios_sync as ios
    rt = Runtime()
    action = args.get("action") or "sync"
    try:
        if action == "sync":
            return _ok(**ios.sync(rt))
        if action == "setup":
            return _ok(**ios.setup(rt, args))
        if action == "status":
            return _ok(**ios.status(rt))
        if action == "disable":
            return _ok(**ios.disable(rt))
        if action == "resolve":
            return _ok(**ios.resolve(rt, args.get("task", ""), args.get("choices") or {}))
        if action == "confirm_missing":
            return _ok(**ios.confirm_uncertain(rt, args.get("task", "")))
    except ios.SyncError as exc:
        return _fail("ios", str(exc))
    return _fail("fix_call", "unknown action")


RESEARCH_SCHEMA = {
    "name": "task_research",
    "description": (
        "Start or retry background research. With a task: research that task again (use when the user asks, or "
        "after its plan changed a lot). Without a task: run the research queue (tasks still waiting for research "
        "or whose research stalled) and wait for the results. New tasks are researched automatically; do not "
        "call this right after task_create."),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "task_id, path or exact title. Omit to run the queue."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 8, "description": "Queue mode: tasks to start."},
            "wait_seconds": {"type": "integer", "minimum": 0, "maximum": 360},
        },
        "required": [],
    },
}


@_guard
def task_research(args: dict[str, Any], session_id: str = "", **_: Any) -> str:
    from . import research_agent
    from .core.research import ResearchError
    rt = Runtime()
    try:
        if args.get("task"):
            result = research_agent.request_again(rt, args["task"], origin_session=session_id or "")
            result.pop("handle", None)
            if not result.get("started"):
                return _fail("retry", f"Research could not start: {result.get('error')}. It stays queued.")
            return _ok(**result, message="Research started; results are added to the task.")
        result = research_agent.recover(rt, limit=int(args.get("limit") or 3),
                                        wait_seconds=float(args.get("wait_seconds", 300)))
    except ResearchError as exc:
        return _fail("research", str(exc))
    done = sum(1 for s in result["started"] if s.get("research") == "complete")
    return _ok(**result, message=f"{result['queued']} task(s) waiting; started {len(result['started'])}, "
               f"{done} finished.")


TOOLS = (
    (CREATE_SCHEMA, task_create, "🜂"),
    (UPDATE_SCHEMA, task_update, "🜄"),
    (FIND_SCHEMA, task_find, "🔎"),
    (RESEARCH_SCHEMA, task_research, "⚗️"),
    (WORK_SCHEMA, task_work_start, "🜁"),
    (CHECKPOINT_SCHEMA, task_checkpoint, "🜃"),
    (SETUP_SCHEMA, task_setup, "⚙️"),
    (IOS_SCHEMA, task_ios, "📱"),
    (DISCOVERY_STREAM_SCHEMA, discovery_stream, "🜍"),
    (DISCOVERY_START_SCHEMA, discovery_start, "🜍"),
    (DISCOVERY_SUBMIT_SCHEMA, discovery_submit, "🜍"),
    (DISCOVERY_DECIDE_SCHEMA, discovery_decide, "🜍"),
)


SWEEP_SCHEMA = {
    "name": "task_research_sweep",
    "description": "Alchemy Task scheduled sweep only: research tasks that are waiting or whose research stalled, "
                   "and wait for the results.",
    "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 8}}},
}


@_guard
def task_research_sweep(args: dict[str, Any], **_: Any) -> str:
    from . import research_agent
    result = research_agent.recover(Runtime(), limit=int(args.get("limit") or 3), wait_seconds=300)
    done = sum(1 for s in result["started"] if s.get("research") == "complete")
    return _ok(**result, message=f"{result['queued']} waiting; started {len(result['started'])}, {done} finished.")


def register_tools(ctx: Any) -> None:
    for schema, handler, emoji in TOOLS:
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema, handler=handler,
                          description=schema["description"], emoji=emoji)
    # The scheduled sweep gets only this tool (plus research tools), not setup or teardown.
    ctx.register_tool(name="task_research_sweep", toolset="alchemy-task-sweep", schema=SWEEP_SCHEMA,
                      handler=task_research_sweep, description=SWEEP_SCHEMA["description"], emoji="⚗️")
