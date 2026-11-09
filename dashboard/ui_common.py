"""Shared plumbing for the task and settings routes behind the Tasks UI.

The dashboard (and the desktop app through ``ctx.rest``) imports ``plugin_api.py`` by file path, so these
modules run inside a private copy of the plugin package. They never rely on the model-side runtime binding:
each request builds a fresh Runtime for the profile the host resolved for that request.
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


class _HostContext:
    """The public PluginContext for this profile, plus ``dispatch_tool`` through the tool registry (the
    discovery code updates and runs its cron job that way). A dashboard request has no agent attached."""

    def __init__(self) -> None:
        from hermes_cli.plugins import PluginContext, PluginManifest
        self._ctx = PluginContext(PluginManifest(name=PLUGIN), manager=None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx, name)

    def dispatch_tool(self, tool_name: str, args: dict, **kwargs: Any) -> Any:
        from tools.registry import discover_builtin_tools, registry
        if not registry.get_entry(tool_name):
            discover_builtin_tools()
        return registry.dispatch(tool_name, args, **kwargs)


def runtime() -> Runtime:
    return Runtime(_HostContext())


def admit(request: Request) -> None:
    """Same guard the dashboard uses for its own sensitive routes (session, loopback token, native grant)."""
    from hermes_cli.web_deps import late
    late("_require_token")(request)


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
    """Admit the caller, parse the JSON body (when ``allowed`` names its fields), run the blocking work off
    the event loop, and map every failure to ``{ok: false, error: {code, message}}``."""
    try:
        admit(request)
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
