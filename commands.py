"""The /task slash command."""
from __future__ import annotations

from typing import Any

from .core import validator
from .core.config import ConfigError
from .runtime import Runtime

HELP = """Alchemy Task
/task status      workspace, Git delivery and task counts
/task validate    check task files (add `apply` to assign missing IDs)
/task push        retry pushing committed task changes
/task setup       set up your task workspace (or say "set up my tasks")
Everyday use needs no commands: tell your agent what to do and it uses the task tools."""


def task_command(raw_args: str = "", **_: Any) -> str:
    parts = (raw_args or "").split()
    sub = parts[0].lower() if parts else "help"
    try:
        if sub in ("help", "-h", "--help"):
            return HELP
        if sub == "setup":
            return ("Setup runs as a conversation with your agent. Say \"set up my tasks\" and it will walk you "
                    "through the workspace, areas, Git delivery and schedules.")
        rt = Runtime()
        if sub == "status":
            return _status(rt)
        if sub == "validate":
            apply = len(parts) > 1 and parts[1].lower() in ("apply", "--apply", "fix")
            report = validator.validate(rt.store(), apply=apply)
            text = validator.summarize(report)
            if apply and report["changed_paths"]:
                receipt = rt.git().deliver(report["changed_paths"], "task: assign missing task IDs")
                text += f" Git: {receipt.get('state', 'committed')}."
            return text
        if sub == "push":
            r = rt.git().retry()
            if r.get("pushed"):
                return "Pushed: the remote is up to date."
            return f"Not pushed ({r.get('state')}): {r.get('error') or r.get('note') or 'no details'}"
        return HELP
    except ConfigError as exc:
        return str(exc)


def _status(rt: Runtime) -> str:
    s = rt.settings
    if not s.configured:
        return "Alchemy Task is installed but not set up. Say \"set up my tasks\" to start."
    store = rt.store()
    scan = store.scan()
    open_n = sum(1 for t in scan.tasks if not t.is_closed)
    areas = s.known_areas()
    git = rt.git().status()
    lines = [
        f"Workspace: {s.root()}",
        f"Areas: {', '.join(areas) or 'none yet'}",
        f"Tasks: {len(scan.tasks)} ({open_n} open)",
        f"Timezone: {s.timezone or 'UTC (not set)'}; today is {s.today()}",
    ]
    receipt = git.get("last_receipt") or {}
    if git.get("state") == "no_git":
        lines.append("Git: workspace is not a Git repository")
    else:
        push = "up to date" if not git.get("needs_push") else f"push pending ({receipt.get('last_error') or 'not pushed yet'})"
        lines.append(f"Git: {git.get('transport')} → {git.get('remote') or 'no remote'} on {git.get('branch')}; {push}")
    if scan.errors:
        lines.append(f"{len(scan.errors)} task file(s) could not be parsed; run /task validate")
    return "\n".join(lines)
