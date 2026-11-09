"""Advanced settings routes: discovery stream schedules (and run now) plus a few task defaults.

Stream changes go through ``discovery.update_stream`` so the cron job is updated in place, exactly as when
the user asks in chat. The request comes from the profile owner's authenticated UI, which is the approval.
Sources, accounts and areas stay chat-only because they need a conversation to set up safely.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request

from .ui_common import PLUGIN, UIError, handle, runtime

router = APIRouter()

FREQUENCIES = ("daily", "weekdays", "hourly", "every 2 hours", "every 3 hours", "every 4 hours")


def _streams(rt: Any) -> list[dict[str, Any]]:
    from .. import discovery
    out = []
    for name, s in sorted(discovery._streams(rt).items()):
        pub = discovery._public(s)
        pub["frequency"] = s.get("frequency") or "daily"
        pub["time"] = s.get("time") or ""
        pub["sources"] = [{"name": x.get("name"), "type": x.get("type"), "scope": x.get("scope")} for x in s.get("sources") or []]
        out.append(pub)
    return out


def _git_status(rt: Any) -> str:
    try:
        g = rt.git()
        if not g.is_repo():
            return "Not a Git repository"
        return f"Git, pushing to {rt.settings.git_remote}" if rt.settings.git_transport != "none" else "Git, local only"
    except Exception:  # noqa: BLE001
        return "Unknown"


@router.get("/settings")
async def settings(request: Request):
    def run() -> dict[str, Any]:
        rt = runtime()
        s = rt.settings
        try:
            streams = _streams(rt)
        except Exception:  # noqa: BLE001 - discovery is optional
            streams = []
        return {"ok": True, "streams": streams,
                "tasks": {"default_area": s.default_area or None, "research_by_default": bool(s.research_by_default),
                          "timezone": s.timezone or None, "workspace_root": s.workspace_root or None,
                          "areas": s.known_areas() if s.configured else []},
                "sync": {"git": _git_status(rt)}}
    return await handle(request, run)


@router.patch("/settings/streams/{name}")
async def patch_stream(request: Request, name: str):
    def run(body: dict[str, Any]) -> dict[str, Any]:
        freq = str(body.get("frequency") or "").strip().lower()
        if freq and freq not in FREQUENCIES:
            raise UIError("invalid_request", "Unknown frequency")
        args: dict[str, Any] = {"name": name, "user_approved": True}
        if freq:
            args["frequency"] = freq
        if body.get("time"):
            args["time"] = str(body["time"]).strip()
        if len(args) == 2:
            raise UIError("invalid_request", "Nothing to change")
        rt = runtime()
        from .. import discovery
        try:
            out = discovery.update_stream(rt, args, "")
        except discovery.DiscoveryError as exc:
            raise UIError("invalid_request", str(exc)) from exc
        return {"ok": True, "stream": out.get("stream"), "message": out.get("message")}
    return await handle(request, run, {"frequency", "time"})


@router.post("/settings/streams/{name}/run")
async def run_stream(request: Request, name: str):
    def run(_: dict[str, Any]) -> dict[str, Any]:
        rt = runtime()
        from .. import discovery
        try:
            stream = discovery._get(rt, name)
        except discovery.DiscoveryError as exc:
            raise UIError("not_found", str(exc), 404) from exc
        if not stream.get("job_id"):
            raise UIError("invalid_request", "This stream has no scheduled job yet. Finish its setup in chat.")
        raw = rt.ctx.dispatch_tool("cronjob_manage", {"action": "run", "job_id": stream["job_id"]})
        try:
            result = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (TypeError, ValueError):
            result = {}
        if result.get("success") is False or result.get("error"):
            raise UIError("error", f"Could not start the run: {str(result.get('error') or raw)[:300]}", 502)
        return {"ok": True, "message": f"The {stream['name']} discovery run has started. Its proposals will appear in Discovery."}
    return await handle(request, run, set())


@router.patch("/settings/tasks")
async def patch_tasks(request: Request):
    def run(body: dict[str, Any]) -> dict[str, Any]:
        rt = runtime()
        if "default_area" in body:
            area = str(body["default_area"] or "").strip().lower()
            if area and area not in rt.settings.known_areas():
                raise UIError("area", f"{area!r} is not a known area.")
            rt.ctx.set_config("default_area", area)
        if "research_by_default" in body:
            if not isinstance(body["research_by_default"], bool):
                raise UIError("invalid_request", "research_by_default must be true or false")
            rt.ctx.set_config("research_by_default", body["research_by_default"])
        return {"ok": True, "plugin": PLUGIN}
    return await handle(request, run, {"default_area", "research_by_default"})
