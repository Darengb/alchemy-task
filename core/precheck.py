"""Code run by scheduled-job stubs under Hermes's Python (no plugin context).

- ``research_wake``: free pre-check for the research sweep (``wakeAgent``).
- ``maintenance``: validator (assign missing IDs) plus push retry. Prints only
  when something changed or a new problem appeared, so quiet runs are silent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import research as rs
from . import validator
from .config import Settings
from .gitops import GitDelivery
from .store import TaskStore


def _settings() -> Settings:
    from hermes_cli.config import load_config_readonly  # public Hermes module
    cfg = load_config_readonly() or {}
    entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("alchemy-task") or {}
    settings = entry.get("settings") or {}

    def get(key: str, default: Any = None) -> Any:
        return settings.get(key, default)

    return Settings.load(get, str(cfg.get("timezone") or ""))


def research_wake(settings: Settings | None = None, data_dir: str = "") -> dict[str, Any]:
    """``{"wakeAgent": false}`` unless some task is waiting for research."""
    try:
        s = settings or _settings()
        if not s.configured:
            return {"wakeAgent": False}
        store = TaskStore(s, Path(data_dir or "/nonexistent-precheck"))  # read-only scan
        waiting = [t.title for t in store.scan().tasks if rs.eligibility(t.fm) == "eligible"]
    except Exception:  # noqa: BLE001 - a broken pre-check must not wake the model every tick
        return {"wakeAgent": False}
    if not waiting:
        return {"wakeAgent": False}
    return {"wakeAgent": True, "waiting": len(waiting), "examples": waiting[:3]}


def _token(s: Settings) -> str | None:
    if s.git_transport != "token":
        return None
    try:
        from agent.secret_scope import get_secret  # public Hermes module
        from .config import TOKEN_ENV
        return get_secret(TOKEN_ENV)
    except Exception:  # noqa: BLE001
        return None


def maintenance(data_dir: str, settings: Settings | None = None, token: str | None = None) -> str:
    """Assign missing IDs, retry unpushed commits. Returns text to deliver, or "" when nothing changed.

    Every reportable condition (file problems, push state, errors) goes into one digest; a message is
    sent only when that digest changes, so a lasting problem is reported once, and again when it clears.
    """
    data = Path(data_dir)
    lines: list[str] = []
    condition: dict[str, Any] = {}
    try:
        s = settings or _settings()
        if not s.configured:
            return ""
        store = TaskStore(s, data)
        report = validator.validate(store, apply=True)
        git = GitDelivery(s, data, token=token if token is not None else _token(s))
        if report["changed_paths"]:
            receipt = git.deliver(report["changed_paths"], "task: assign missing task IDs")
            lines.append(f"Assigned IDs to {len(report['changed_paths'])} task(s).")
        push_state = "ok"
        if s.git_transport != "none" and git.status().get("needs_push"):
            if s.git_transport == "token" and not git.token:
                push_state = "no token: enter ALCHEMY_TASK_GIT_TOKEN in the plugin settings"
            else:
                r = git.retry()
                if r.get("pushed"):
                    lines.append("Pushed task changes that were waiting.")
                else:
                    err = str(r.get("error") or r.get("state") or "")
                    push_state = err.split(":")[0][:80] or "not pushed"
        condition["push"] = push_state
        condition["problems"] = {k: report[k] for k in ("unsupported", "malformed", "unknown_status",
                                                         "done_without_completed", "area_mismatch",
                                                         "duplicate_task_ids")}
        summary = validator.summarize(report) if report["problems"] else ""
    except Exception as exc:  # noqa: BLE001 - report once, never fail every hour
        condition = {"error": f"{exc.__class__.__name__}: {str(exc)[:120]}"}
        summary = ""
    digest = hashlib.sha256(json.dumps(condition, sort_keys=True, default=str).encode()).hexdigest()
    marker = data / "maintenance-state.sha"
    previous = marker.read_text().strip() if marker.exists() else ""
    if digest != previous:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest)
        if "error" in condition:
            lines.append(f"The hourly check failed: {condition['error']}. Run /task status.")
        else:
            push_ok = condition["push"] == "ok"
            if not push_ok:
                lines.append(f"Task changes are committed but not pushed ({condition['push']}). Retrying hourly; "
                             "run /task push after fixing it.")
            if summary:
                lines.append("Task file check: " + summary + " Run /task validate for details.")
            if previous and push_ok and not summary and not lines:
                lines.append("Earlier problems are resolved.")
    if lines:
        return "Alchemy Task: " + " ".join(lines)
    return ""
