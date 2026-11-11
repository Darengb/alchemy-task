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


def _next_runs(rt: Any) -> dict[str, str]:
    """Each job's next run time from the public cron list ({} when it cannot be read)."""
    try:
        raw = rt.ctx.dispatch_tool("cronjob_manage", {"action": "list", "include_disabled": True})
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return {str(j.get("job_id") or j.get("id")): j.get("next_run_at") for j in data.get("jobs", [])
                if j.get("next_run_at") and j.get("enabled", True) is not False and j.get("state") != "paused"}
    except Exception:  # noqa: BLE001 - next run is display only
        return {}


def _streams(rt: Any) -> list[dict[str, Any]]:
    from .. import discovery
    out = []
    streams = sorted(discovery._streams(rt).items())
    nexts = _next_runs(rt) if any(s.get("job_id") for _, s in streams) else {}
    for name, s in streams:
        pub = discovery._public(s)
        pub["frequency"] = s.get("frequency") or "daily"
        pub["time"] = s.get("time") or ""
        pub["sources"] = [{"name": x.get("name"), "type": x.get("type"), "scope": x.get("scope")} for x in s.get("sources") or []]
        pub["next_run_at"] = nexts.get(str(s.get("job_id"))) if s.get("job_id") else None
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
                          "research_model": s.research_model or None,
                          "research_provider": s.research_provider or None,
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
        from .tasks_api import _background, _sweep_job_state
        state = _sweep_job_state(rt, stream["job_id"])
        if state == "missing":
            raise UIError("invalid_request", "This stream's scheduled job is missing. Ask Hermes in chat to repair the stream.")
        job_id = stream["job_id"]

        def fire() -> None:
            # From a dashboard request the host runs the job inline for minutes, so fire it off the request.
            try:
                rt.ctx.dispatch_tool("cronjob_manage", {"action": "run", "job_id": job_id})
            except Exception:  # noqa: BLE001 - the run's own result posts to the stream's chat
                pass
        _background(fire)
        return {"ok": True, "message": f"The {stream['name']} discovery run has started. Its digest will post to the "
                                       "stream's chat, and its proposals will appear here."}
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
        for key in ("research_model", "research_provider"):
            if key in body:
                value = body[key] if body[key] is not None else ""
                limit = 64 if key == "research_provider" else 200  # Hermes rejects a longer launch provider
                if not isinstance(value, str) or len(value.strip()) > limit:
                    raise UIError("invalid_request", f"{key} must be text of at most {limit} characters")
                rt.ctx.set_config(key, value.strip())  # empty: research uses the main model
        return {"ok": True, "plugin": PLUGIN}
    return await handle(request, run, {"default_area", "research_by_default", "research_model", "research_provider"})
