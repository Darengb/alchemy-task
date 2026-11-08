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
            "area": {"type": "string", "description": "Area slug. Infer from context when clear; omit to get the list."},
            "due": {**_DATE, "description": "Due date YYYY-MM-DD in the user's timezone. Required unless undated."},
            "undated": {"type": "boolean", "description": "True only if the user explicitly said this task has no due date."},
            "scheduled": {**_DATE, "description": "Date the user plans to work on it (optional, differs from due)."},
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
        "Change an existing task: status, dates, priority, title, area, notes. Changes only the fields you pass "
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
            "rename_file": {"type": "boolean", "description": "Also rename the file to match a new title."},
            "due": {"type": "string", "description": "YYYY-MM-DD, or 'none' to clear (needs undated=true)."},
            "undated": {"type": "boolean"},
            "scheduled": {"type": "string", "description": "YYYY-MM-DD, or 'none' to clear."},
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
        "Set include_body=true for one task to read its notes, research and current state."),
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
        research_skip_reason=args.get("research_skip_reason", ""), confirm_new=bool(args.get("confirm_new")),
        create_area=bool(args.get("create_area")), status=args.get("status", "open"),
        source=args.get("source", ""))
    receipt = rt.git().deliver([store.rel(doc.path)], f"task: create {doc.title[:72]}")
    research = (doc.fm.get("enrichment") or {}).get("status")
    research_errors = rt.notify_research(doc, session_id or "") if research == "pending" else []
    summary = store.summary(doc)
    msg = f"Created \"{doc.title}\" in {summary['area']}, due {summary['due'] or 'undated'}. {_git_note(receipt)}"
    if research == "pending" and not research_errors:
        msg += " Background research has started; results are added to the task and you will hear when it is done."
    elif research == "pending":
        msg += " Research is queued and will start on the next research sweep."
    return _ok(task=summary, git=receipt, research=research, research_errors=research_errors or None, message=msg)


_UPDATE_KEYS = ("status", "reason", "reopen", "completed", "title", "rename_file", "due", "undated", "scheduled",
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
    docs = store.find(query=args.get("query", ""), task_id=args.get("task_id", ""), area=args.get("area", ""),
                      status=args.get("status", "open"), due_before=args.get("due_before", ""),
                      due_after=args.get("due_after", ""), limit=args.get("limit", 20))
    include_body = bool(args.get("include_body")) and len(docs) <= 3
    return _ok(count=len(docs), tasks=[store.summary(d, include_body=include_body) for d in docs],
               today=rt.settings.today())


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
        "Set up Alchemy Task with the user (load the skill alchemy-task:setup first). Actions: status (readiness "
        "receipt and what is next), inspect (look at a folder before using it), save (validate and save "
        "settings), git_check (verify Git push, or create a deploy key), jobs_preview (list the scheduled jobs to "
        "ask the user about), jobs_create (create them, only after the user approved), teardown (remove jobs)."),
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["status", "inspect", "save", "git_check", "jobs_preview",
                                              "jobs_create", "teardown"]},
        "path": {"type": "string", "description": "inspect: absolute folder path."},
        "workspace_root": {"type": "string"},
        "create_workspace": {"type": "boolean", "description": "save: create a new workspace folder and Git repo."},
        "allow_shared": {"type": "boolean"},
        "task_dir": {"type": "string", "description": "Folder pattern with {area}, default areas/{area}/tasks."},
        "areas": {"type": "array", "items": {"type": "string"}},
        "default_area": {"type": "string"},
        "timezone": {"type": "string", "description": "IANA name the user confirmed, e.g. America/New_York."},
        "set_hermes_timezone": {"type": "boolean", "description": "Also set Hermes's own timezone (when it was unset)."},
        "research_by_default": {"type": "boolean"},
        "git_transport": {"type": "string", "enum": ["system", "deploy_key", "token", "none"]},
        "git_remote": {"type": "string"},
        "git_branch": {"type": "string"},
        "remote_url": {"type": "string", "description": "git_check: set the remote URL (an empty private repo)."},
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
        if action == "teardown":
            return _ok(**sf.teardown(rt))
    except sf.SetupError as exc:
        return _fail("setup", str(exc))
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
)


def register_tools(ctx: Any) -> None:
    for schema, handler, emoji in TOOLS:
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema, handler=handler,
                          description=schema["description"], emoji=emoji)
