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


def maintenance(data_dir: str, settings: Settings | None = None, token: str | None = None) -> str:
    """Assign missing IDs, retry unpushed commits. Returns text to deliver, or "" when nothing new."""
    s = settings or _settings()
    if not s.configured:
        return ""
    data = Path(data_dir)
    store = TaskStore(s, data)
    report = validator.validate(store, apply=True)
    git = GitDelivery(s, data, token=token)
    lines = []
    if report["changed_paths"]:
        receipt = git.deliver(report["changed_paths"], "task: assign missing task IDs")
        lines.append(f"Assigned IDs to {len(report['changed_paths'])} task(s); Git: {receipt.get('state')}.")
    status = git.status()
    if status.get("needs_push") and s.git_transport != "none":
        r = git.retry()
        if r.get("pushed"):
            lines.append("Pushed task changes that were waiting.")
        else:
            lines.append(f"Task changes are committed but not pushed: {r.get('error') or r.get('state')}.")
    problems = {k: report[k] for k in ("unsupported", "malformed", "unknown_status", "done_without_completed",
                                       "area_mismatch", "duplicate_task_ids")}
    digest = hashlib.sha256(json.dumps(problems, sort_keys=True, default=str).encode()).hexdigest()
    marker = data / "maintenance-problems.sha"
    previous = marker.read_text().strip() if marker.exists() else ""
    if digest != previous:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest)
        if report["problems"]:
            lines.append("Task file check: " + validator.summarize(report) + " Run /task validate for details.")
        elif previous:
            lines.append("Task file check: earlier problems are resolved.")
    if lines:
        return "Alchemy Task maintenance: " + " ".join(lines)
    return ""
