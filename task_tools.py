"""Agent-facing task tools: task_create, task_update, task_find."""
from __future__ import annotations

import json
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
)


def register_tools(ctx: Any) -> None:
    for schema, handler, emoji in TOOLS:
        ctx.register_tool(name=schema["name"], toolset=TOOLSET, schema=schema, handler=handler,
                          description=schema["description"], emoji=emoji)
