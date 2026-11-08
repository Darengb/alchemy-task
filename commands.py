"""The /task slash command."""
from __future__ import annotations

from typing import Any

from .core import validator
from .core.config import ConfigError
from .runtime import Runtime

HELP = """Alchemy Task
/task status      setup and readiness of each part
/task setup       how to set up (say "set up my tasks")
/task validate    check task files (add `apply` to assign missing IDs)
/task push        retry pushing committed task changes
/task teardown    remove Alchemy Task's scheduled jobs (task files are kept)
/task ios         sync with Apple Reminders (optional; keep the Hermes app open on your iPhone)
Everyday use needs no commands: tell your agent what to do and it uses the task tools."""


def task_command(raw_args: str = "", **_: Any) -> str:
    parts = (raw_args or "").split()
    sub = parts[0].lower() if parts else "help"
    try:
        if sub in ("help", "-h", "--help"):
            return HELP
        rt = Runtime()
        from . import setup_flow as sf
        if sub == "setup":
            return (sf.receipt_text(sf.status(rt)) + "\n\nSetup is a short conversation with your agent: say "
                    "\"set up my tasks\" and it walks you through the rest.")
        if sub == "status":
            text = sf.receipt_text(sf.status(rt))
            return text if not rt.settings.configured else text + "\n\n" + _status(rt)
        if sub == "ios":
            from . import ios_sync
            try:
                out = ios_sync.sync(rt)
            except ios_sync.SyncError as exc:
                return str(exc)
            lines = [out["message"]] + [f"• {p}" for p in out.get("problems", [])[:5]]
            return "\n".join(lines)
        if sub == "teardown":
            out = sf.teardown(rt)
            return (f"Removed {len(out['removed_jobs'])} scheduled job(s) and {len(out['removed_scripts'])} "
                    f"script(s). {out['note']}")
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
