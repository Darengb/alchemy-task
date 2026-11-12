"""Shared plumbing for the task and settings routes behind the Tasks UI.

The dashboard (and the desktop app through ``ctx.rest``) imports ``plugin_api.py`` by file path, so these
modules run inside a private copy of the plugin package. They never rely on the model-side runtime binding:
each request builds a fresh Runtime for the profile the host resolved for that request. The routes rely on
the dashboard's own auth: Hermes admits a request before it reaches a plugin route.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..core import taskfile as tf
from ..core.config import ConfigError
from ..core.locks import LockTimeout
from ..core.store import NeedsInput
from ..runtime import Runtime

PLUGIN = "alchemy-task"


class UIError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class HostContext:
    """The plugin context a dashboard request needs, built only from Hermes's published plugin APIs.

    A dashboard request has no PluginContext of its own, so this facade supplies the four things the
    plugin's Runtime and discovery code use: ``state`` (``PluginState``), ``get_config``/``set_config``
    (``plugins.entries.alchemy-task.settings`` through ``hermes_cli.config``), ``dispatch_tool`` (the
    public ``tools.registry``; the settings page reads and runs its cron jobs that way) and
    ``profile_name``. Everything resolves the profile home the host bound for this request.
    """

    @staticmethod
    def current_cron_execution() -> None:
        return None  # a dashboard request is never a cron run

    @property
    def state(self) -> Any:
        from hermes_cli.plugins_state import PluginState
        return PluginState(PLUGIN)

    @property
    def profile_name(self) -> str:
        from hermes_constants import get_hermes_home, profile_name_for_home
        return profile_name_for_home(get_hermes_home()) or "custom"

    @staticmethod
    def _segments(key: str) -> list[str]:
        parts = str(key).split(".")
        if not key or any(not p or p.startswith("_") for p in parts):
            raise ValueError(f"Invalid setting key: {key!r}")
        return parts

    def get_config(self, key: str, default: Any = None) -> Any:
        from hermes_cli.config import load_config_readonly
        entry = (((load_config_readonly() or {}).get("plugins") or {}).get("entries") or {}).get(PLUGIN)
        if not isinstance(entry, dict):
            return default
        missing = object()
        for subtree in ("settings", "config"):  # ``config`` is the legacy subtree PluginContext also reads
            node: Any = entry.get(subtree)
            for part in self._segments(key):
                node = node.get(part, missing) if isinstance(node, dict) else missing
            if node is not missing:
                return node
        return default

    def set_config(self, key: str, value: Any) -> None:
        from hermes_cli import config as hconfig
        if hconfig.is_managed():
            raise PermissionError("Plugin settings cannot be changed in a managed install")
        path = ("plugins", "entries", PLUGIN, "settings", *self._segments(key))
        partial: Any = value
        for part in reversed(path):
            partial = {part: partial}
        hconfig.save_config(partial, preserve_keys={path}, merge_existing=True)

    def dispatch_tool(self, tool_name: str, args: dict, **kwargs: Any) -> Any:
        from tools.registry import discover_builtin_tools, registry
        if not registry.get_entry(tool_name):
            discover_builtin_tools()
        return registry.dispatch(tool_name, args, **kwargs)


def runtime() -> Runtime:
    return Runtime(HostContext())


def error_response(exc: BaseException) -> JSONResponse:
    if isinstance(exc, UIError):
        code, status, message = exc.code, exc.status, exc.message
    elif isinstance(exc, HTTPException):
        code = "unauthorized" if exc.status_code == 401 else "forbidden"
        status, message = exc.status_code, str(exc.detail)
    elif isinstance(exc, NeedsInput):
        code, status, message = exc.kind, 400, exc.message
        if exc.kind == "not_found":
            status = 404
    elif isinstance(exc, tf.ConcurrentEditError):
        code, status, message = "stale_revision", 409, "The task changed since it was read."
    elif isinstance(exc, LockTimeout):
        code, status, message = "retry", 409, "The task is busy. Try again in a moment."
    elif isinstance(exc, ConfigError):
        code, status, message = "setup", 400, str(exc)
    elif isinstance(exc, (tf.TaskFormatError, ValueError, TypeError, KeyError)):
        code, status, message = "invalid_request", 400, str(exc)
    else:
        code, status, message = "error", 500, f"{exc.__class__.__name__}: {exc}"
    return JSONResponse({"ok": False, "error": {"code": code, "message": message}}, status_code=status)


async def handle(request: Request, fn: Callable[..., Any], allowed: set[str] | None = None) -> Any:
    """Parse the JSON body (when ``allowed`` names its fields), run the blocking work off
    the event loop, and map every failure to ``{ok: false, error: {code, message}}``."""
    try:
        if allowed is None:
            return await asyncio.to_thread(fn)
        body = await body_of(request, allowed)
        return await asyncio.to_thread(fn, body)
    except Exception as exc:  # noqa: BLE001 - every failure becomes a JSON error the UI can show
        return error_response(exc)


async def body_of(request: Request, allowed: set[str]) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    data = await request.json()
    if not isinstance(data, dict):
        raise UIError("invalid_request", "Expected a JSON object")
    extra = set(data) - allowed
    if extra:
        raise UIError("invalid_request", "Unsupported fields: " + ", ".join(sorted(extra)))
    return data
