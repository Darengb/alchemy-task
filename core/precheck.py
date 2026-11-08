"""Free pre-checks for scheduled jobs. Runs under Hermes's Python from a cron stub."""
from __future__ import annotations

from typing import Any

from . import research as rs
from .config import Settings
from .store import TaskStore


def _settings() -> Settings:
    from hermes_cli.config import load_config_readonly  # public Hermes module
    cfg = load_config_readonly() or {}
    entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("alchemy-task") or {}
    settings = entry.get("settings") or {}

    def get(key: str, default: Any = None) -> Any:
        return settings.get(key, default)

    return Settings.load(get, str(cfg.get("timezone") or ""))


def research_wake(settings: Settings | None = None) -> dict[str, Any]:
    """``{"wakeAgent": false}`` unless some task is waiting for research."""
    try:
        s = settings or _settings()
        if not s.configured:
            return {"wakeAgent": False}
        from pathlib import Path
        store = TaskStore(s, Path("/nonexistent-precheck"))  # read-only scan; never locks or writes
        waiting = [t.title for t in store.scan().tasks if rs.eligibility(t.fm) == "eligible"]
    except Exception:  # noqa: BLE001 - a broken pre-check must not wake the model every tick
        return {"wakeAgent": False}
    if not waiting:
        return {"wakeAgent": False}
    return {"wakeAgent": True, "waiting": len(waiting), "examples": waiting[:3]}
