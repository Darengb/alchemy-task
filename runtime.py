"""Per-call runtime: resolves settings, state dir and helpers from the plugin context."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .core.config import TOKEN_ENV, Settings
from .core.gitops import GitDelivery
from .core.store import TaskStore

_ctx: Any = None
# Callbacks run after a task is created with research pending: fn(runtime, doc).
research_listeners: list[Callable[["Runtime", Any], None]] = []


def bind(ctx: Any) -> None:
    global _ctx
    _ctx = ctx


def _hermes_timezone() -> str:
    try:
        from hermes_cli.config import load_config_readonly
        return str((load_config_readonly() or {}).get("timezone") or "").strip()
    except Exception:  # noqa: BLE001 - optional fallback
        return ""


class Runtime:
    def __init__(self, ctx: Any = None, settings: Settings | None = None, data_dir: Path | None = None) -> None:
        self.ctx = ctx if ctx is not None else _ctx
        if settings is None:
            if self.ctx is None:
                raise RuntimeError("Alchemy Task is not loaded")
            settings = Settings.load(self.ctx.get_config, _hermes_timezone())
        self.settings = settings
        if data_dir is None:
            data_dir = Path(self.ctx.state.data_dir)
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def store(self) -> TaskStore:
        return TaskStore(self.settings, self.data_dir)

    def git(self) -> GitDelivery:
        token = None
        if self.settings.git_transport == "token":
            try:
                from agent.secret_scope import get_secret
                token = get_secret(TOKEN_ENV)
            except Exception:  # noqa: BLE001 - missing token is reported by the push receipt
                token = None
        return GitDelivery(self.settings, self.data_dir, token=token)

    def notify_research(self, doc: Any) -> list[str]:
        errors = []
        for fn in list(research_listeners):
            try:
                fn(self, doc)
            except Exception as exc:  # noqa: BLE001 - research recovery picks it up later
                errors.append(f"{exc.__class__.__name__}: {exc}")
        return errors
