"""Setup: deterministic steps behind the conversational setup skill.

The user's own agent holds the conversation (skill ``alchemy-task:setup``) and
calls ``task_setup`` to inspect, validate, save and check each decision. Every
saved setting goes through here, and ``status`` returns a per-subsystem
readiness receipt. Setup state is the saved settings themselves, so setup can
stop and resume at any point.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import jobs
from .core import taskfile as tf
from .core.config import TRANSPORTS, ConfigError, Settings, validate_area_name
from .core.gitops import GitDelivery
from .core.store import TaskStore
from .runtime import Runtime

SAVABLE = {"workspace_root": str, "task_dir": str, "areas": list, "default_area": str, "timezone": str,
           "research_by_default": bool, "git_transport": str, "git_remote": str, "git_branch": str,
           "git_run_hooks": bool}
DEFAULT_AREAS = ["work", "personal"]


class SetupError(ValueError):
    pass


# ------------------------------------------------------------------ helpers

def _hermes_timezone() -> str:
    try:
        from hermes_cli.config import load_config_readonly
        return str((load_config_readonly() or {}).get("timezone") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _set_hermes_timezone(name: str) -> bool:
    try:
        from hermes_cli.config import save_config
        save_config({"timezone": name}, merge_existing=True)
        return True
    except Exception:  # noqa: BLE001 - the plugin setting still applies to every Alchemy Task date and job
        return False


def _hermes_home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def _plugin_dir() -> Path:
    return Path(__file__).resolve().parent


def _timezone_state(rt: Runtime) -> dict[str, Any]:
    plugin_tz = str(rt.ctx.get_config("timezone", "") or "").strip()
    hermes_tz = _hermes_timezone()
    effective = plugin_tz or hermes_tz
    confirmed = bool(rt.ctx.state.get("timezone_confirmed", default=False))
    likely_unset = (not effective or effective.upper() in ("UTC", "ETC/UTC", "GMT")) and not confirmed
    now = dt.datetime.now(ZoneInfo(effective)) if effective and _valid_tz(effective) else None
    return {"timezone": effective or None, "hermes_timezone": hermes_tz or None, "confirmed": confirmed or
            bool(plugin_tz and not likely_unset), "likely_unset": likely_unset,
            "local_time": now.strftime("%-I:%M %p, %A %B %-d") if now else None}


def _valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True, timeout=30,
                          stdin=subprocess.DEVNULL, env={"PATH": "/usr/local/bin:/usr/bin:/bin",
                                                         "HOME": str(Path.home()), "GIT_TERMINAL_PROMPT": "0"})


# ------------------------------------------------------------------ inspect

def inspect_workspace(path: str, task_dir: str = "") -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise SetupError("give an absolute path")
    out: dict[str, Any] = {"path": str(p), "exists": p.is_dir()}
    if not p.is_dir():
        out["suggestion"] = "Folder does not exist. Use create_workspace=true with save to make a new task workspace here."
        return out
    top = _git(p, "rev-parse", "--show-toplevel")
    out["git_repo"] = top.returncode == 0 and Path(top.stdout.strip()).resolve() == p.resolve()
    if top.returncode == 0 and not out["git_repo"]:
        out["inside_repo"] = top.stdout.strip()
    if out["git_repo"]:
        remote = _git(p, "remote", "get-url", "origin")
        out["remote"] = remote.stdout.strip() if remote.returncode == 0 else None
        out["branch"] = _git(p, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() or None
        dirty = _git(p, "status", "--porcelain", "--untracked-files=no").stdout.strip().splitlines()
        out["uncommitted_tracked_files"] = len(dirty)
    s = Settings(workspace_root=str(p), task_dir=task_dir or "areas/{area}/tasks")
    try:
        areas = s.known_areas()
    except ConfigError:
        areas = []
    out["areas_found"] = areas
    store = TaskStore(s, Path("/nonexistent-inspect"))
    scan = store.scan()
    out["tasks_found"] = len(scan.tasks)
    out["unparseable"] = len(scan.errors)
    if not areas:
        # look for task-tagged notes elsewhere to suggest the right task_dir
        hits: dict[str, int] = {}
        for md in list(p.rglob("*.md"))[:3000]:
            if any(part.startswith(".") for part in md.relative_to(p).parts):
                continue
            try:
                head = md.read_text(errors="ignore")[:1500]
            except OSError:
                continue
            if head.startswith("---\n") and ("- task\n" in head or "tags: [task" in head or "tags: task" in head):
                rel = md.parent.relative_to(p)
                hits[str(rel)] = hits.get(str(rel), 0) + 1
        out["task_folders_elsewhere"] = dict(sorted(hits.items(), key=lambda x: -x[1])[:8])
    out["preset"] = "existing" if scan.tasks else ("empty" if not any(p.iterdir()) else "folder")
    return out


# ------------------------------------------------------------------ save

def _create_workspace(path: Path, areas: list[str], task_dir: str) -> list[str]:
    path.mkdir(parents=True, exist_ok=True)
    made = []
    top = _git(path, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != path.resolve():
        _git(path, "init", "-q", "-b", "main")
        made.append("git repository")
    for area in areas:
        folder = path / task_dir.replace("{area}", area)
        folder.mkdir(parents=True, exist_ok=True)
        keep = folder / ".gitkeep"
        if not any(folder.iterdir()):
            keep.write_text("")
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text("# Tasks\n\nManaged by Alchemy Task. One Markdown file per task, grouped by area.\n")
        made.append("README.md")
    return made


def save(rt: Runtime, args: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key, kind in SAVABLE.items():
        if key not in args or args[key] is None:
            continue
        value = args[key]
        if kind is list:
            if isinstance(value, str):
                value = [v.strip() for v in value.split(",") if v.strip()]
            value = [validate_area_name(v) for v in value]
        elif kind is bool:
            value = value if isinstance(value, bool) else str(value).strip().lower() in ("true", "yes", "1", "on")
        else:
            value = str(value).strip()
        changes[key] = value
    if "timezone" in changes:
        if not _valid_tz(changes["timezone"]):
            raise SetupError(f"unknown timezone {changes['timezone']!r}; use an IANA name like America/New_York")
    if "git_transport" in changes and changes["git_transport"] not in TRANSPORTS:
        raise SetupError(f"git_transport must be one of {', '.join(TRANSPORTS)}")
    if "task_dir" in changes and "{area}" not in changes["task_dir"]:
        raise SetupError("task_dir must contain {area}, for example areas/{area}/tasks")
    if "default_area" in changes and changes["default_area"]:
        changes["default_area"] = validate_area_name(changes["default_area"])
    notes = []
    if "workspace_root" in changes:
        p = Path(changes["workspace_root"]).expanduser()
        if not p.is_absolute():
            raise SetupError("workspace_root must be an absolute path")
        if args.get("create_workspace"):
            areas = changes.get("areas") or rt.settings.areas or DEFAULT_AREAS
            changes.setdefault("areas", areas)
            made = _create_workspace(p, areas, changes.get("task_dir") or rt.settings.task_dir)
            if made:
                notes.append("Created " + ", ".join(made) + ".")
        elif not p.is_dir():
            raise SetupError("that folder does not exist; pass create_workspace=true to create a new workspace")
        changes["workspace_root"] = str(p.resolve())
        _guard_shared_workspace(rt, changes["workspace_root"], allow_shared=bool(args.get("allow_shared")))
    for key, value in changes.items():
        rt.ctx.set_config(key, value)
    if "timezone" in changes:
        rt.ctx.state.set("timezone_confirmed", True)
        if args.get("set_hermes_timezone"):
            notes.append("Hermes timezone updated." if _set_hermes_timezone(changes["timezone"])
                         else "Could not update Hermes's own timezone; Alchemy Task uses the saved one.")
    if changes.get("workspace_root"):
        rt.ctx.state.set("workspace_registered", {"path": changes["workspace_root"], "at": time.time()})
    return {"saved": sorted(changes), "notes": notes}


OWNER_FILE = ".alchemy-task-owner"


def _guard_shared_workspace(rt: Runtime, path: str, *, allow_shared: bool = False) -> None:
    """Each install is self-contained: refuse a workspace another Alchemy Task install already claimed.
    The claim is a small marker file inside the workspace; no other profile's files are read."""
    marker = Path(path) / OWNER_FILE
    me = str(_hermes_home().resolve())
    if marker.exists():
        owner = marker.read_text(errors="ignore").strip()
        if owner and owner != me and not allow_shared:
            raise SetupError("another Hermes install or profile already uses this workspace with Alchemy Task. "
                             "Give this one its own workspace, or pass allow_shared=true if the user wants both to "
                             "share it (commits stay path-scoped, but the two installs do not coordinate locks).")
    marker.write_text(me + "\n")
    exclude = Path(path) / ".git" / "info" / "exclude"
    if exclude.parent.is_dir():
        text = exclude.read_text() if exclude.exists() else ""
        if OWNER_FILE not in text:
            exclude.write_text(text + ("" if text.endswith("\n") or not text else "\n") + OWNER_FILE + "\n")


# ------------------------------------------------------------------ git

def git_check(rt: Runtime, args: dict[str, Any]) -> dict[str, Any]:
    s = rt.settings
    gd = rt.git()
    out: dict[str, Any] = {"transport": s.git_transport}
    root = s.root()
    if not gd.is_repo():
        raise SetupError("the workspace is not a Git repository")
    if args.get("remote_url"):
        url = str(args["remote_url"]).strip()
        current = _git(root, "remote", "get-url", s.git_remote)
        if current.returncode == 0 and current.stdout.strip() != url and not args.get("replace_remote"):
            raise SetupError(f"the workspace already pushes to {current.stdout.strip()}. Only change it if the user "
                             "asked to (pass replace_remote=true).")
        if current.returncode == 0:
            _git(root, "remote", "set-url", s.git_remote, url)
        else:
            _git(root, "remote", "add", s.git_remote, url)
        out["remote_set"] = url
    if s.git_transport == "none":
        out.update(ready=True, note="Local commits only. Tasks are not backed up off this machine.")
        return out
    if s.git_transport == "deploy_key":
        out["public_key"] = gd.ensure_deploy_key(f"alchemy-task@{rt.ctx.profile_name if hasattr(rt.ctx, 'profile_name') else 'hermes'}")
        remote = _git(root, "remote", "get-url", s.git_remote).stdout.strip()
        repo = _github_repo(remote)
        if repo:
            out["add_key_at"] = f"https://github.com/{repo}/settings/keys/new"
        out["instructions"] = ("Add this public key as a deploy key with 'Allow write access' checked, then run "
                               "git_check again.")
    if s.git_transport == "token" and not gd.token:
        out.update(ready=False, problem="No token saved. Enter ALCHEMY_TASK_GIT_TOKEN in the plugin settings (Desktop "
                   "or dashboard). Never paste it into chat.")
        return out
    if not gd.has_remote():
        out.update(ready=False, problem="No Git remote. Create an empty private repository and give its URL as "
                   "remote_url.")
        return out
    if not _git(root, "rev-parse", "--verify", "HEAD").returncode == 0:
        if not (root / "README.md").exists():
            (root / "README.md").write_text("# Tasks\n")
        receipt = gd.deliver(["README.md"], "Alchemy Task workspace")
    else:
        receipt = gd.retry()
    out["push"] = receipt
    out["ready"] = bool(receipt.get("pushed"))
    if not out["ready"] and s.git_transport == "deploy_key":
        out["problem"] = "The key is not accepted yet (add it on GitHub, with write access)."
    elif not out["ready"]:
        out["problem"] = receipt.get("error") or receipt.get("state")
    return out


def _github_repo(remote: str) -> str:
    import re
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote or "")
    return m.group(1) if m else ""


# ------------------------------------------------------------------ jobs

def jobs_preview(rt: Runtime) -> dict[str, Any]:
    tz = _timezone_state(rt)["timezone"] or "UTC"
    registry = rt.ctx.state.get("jobs", default={}) or {}
    items = jobs.inventory(tz)
    for item in items:
        reg = registry.get(item["key"])
        stub = _hermes_home() / "scripts" / jobs.JOBS[item["key"]]["stub"]
        current = reg and reg.get("job_id") and reg.get("hash") == jobs.spec_hash(item["key"]) and stub.exists() \
            and str(_plugin_dir()) in stub.read_text(errors="ignore")
        item["status"] = "created" if current else ("needs update" if reg and reg.get("job_id") else "not created")
    return {"jobs": items, "approval_needed": any(i["status"] != "created" for i in items),
            "instructions": "Show these jobs to the user and ask once whether to create them. Only call "
                            "action=jobs_create with user_approved=true after they say yes."}


def jobs_create(rt: Runtime, *, user_approved: bool, session_id: str = "") -> dict[str, Any]:
    if not user_approved:
        raise SetupError("ask the user to approve the job list first, then call again with user_approved=true")
    tz = _timezone_state(rt)
    if tz["likely_unset"]:
        raise SetupError("confirm the user's timezone first (it is unset or UTC), so schedules run at their local time")
    scripts = _hermes_home() / "scripts"
    registry = rt.ctx.state.get("jobs", default={}) or {}
    known_ids = {r.get("job_id") for r in registry.values()}
    for job in _list_jobs(rt):  # adopt-or-clean jobs left by an earlier install whose registry was lost
        jid = str(job.get("job_id") or job.get("id") or "")
        if str(job.get("name") or "") in {jobs.job_name(k) for k in jobs.JOBS} and jid not in known_ids:
            _remove_job(rt, jid)
    results = []
    for key in jobs.JOBS:
        jobs.write_stub(scripts, key, plugin_dir=str(_plugin_dir()), data_dir=str(rt.data_dir))
        reg = registry.get(key) or {}
        if reg.get("job_id") and reg.get("hash") == jobs.spec_hash(key) and _job_exists(rt, reg["job_id"]):
            results.append({"job": key, "status": "already created", "job_id": reg["job_id"]})
            continue
        if reg.get("job_id"):
            _remove_job(rt, reg["job_id"])
        raw = rt.ctx.dispatch_tool("cronjob_manage", jobs.create_args(key, timezone=tz["timezone"] or "UTC"))
        job_id = jobs.parse_job_id(raw)
        if not job_id:
            results.append({"job": key, "status": "failed", "error": str(raw)[:300]})
            continue
        registry[key] = {"job_id": job_id, "hash": jobs.spec_hash(key), "created_at": time.time(),
                         "origin_session": session_id}
        results.append({"job": key, "status": "created", "job_id": job_id})
    rt.ctx.state.set("jobs", registry)
    rt.ctx.state.set("jobs_approval", {"at": time.time(), "session": session_id,
                                       "hashes": {k: jobs.spec_hash(k) for k in jobs.JOBS}})
    return {"results": results}


def _list_jobs(rt: Runtime) -> list[dict[str, Any]]:
    raw = rt.ctx.dispatch_tool("cronjob_manage", {"action": "list"})
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return []
    items = data.get("jobs") if isinstance(data, dict) else data
    return [j for j in items or [] if isinstance(j, dict)]


def _job_exists(rt: Runtime, job_id: str) -> bool:
    return any(str(j.get("job_id") or j.get("id")) == job_id for j in _list_jobs(rt))


def _remove_job(rt: Runtime, job_id: str) -> str:
    return str(rt.ctx.dispatch_tool("cronjob_manage", {"action": "remove", "job_id": job_id}))[:200]


def teardown(rt: Runtime) -> dict[str, Any]:
    registry = rt.ctx.state.get("jobs", default={}) or {}
    removed = []
    for key, reg in registry.items():
        if reg.get("job_id"):
            _remove_job(rt, reg["job_id"])
            removed.append(key)
    # also catch jobs whose registry entry was lost, by reserved name prefix
    for job in _list_jobs(rt):
        if str(job.get("name") or "").startswith(jobs.PREFIX + ":"):
            _remove_job(rt, str(job.get("job_id") or job.get("id")))
            removed.append(str(job.get("name")))
    stubs = []
    try:
        scripts = _hermes_home() / "scripts"
        for spec in jobs.JOBS.values():
            path = scripts / spec["stub"]
            if path.exists():
                path.unlink()
                stubs.append(path.name)
    except Exception:  # noqa: BLE001
        pass
    rt.ctx.state.set("jobs", {})
    try:
        from . import discovery
        streams = discovery.teardown_streams(rt)
    except Exception:  # noqa: BLE001 - discovery may not be set up
        streams = []
    return {"removed_jobs": sorted(set(removed)), "removed_scripts": stubs, "removed_streams": streams,
            "note": "Task files and settings are kept. Remove the plugin with `hermes plugins remove alchemy-task`."}


# ------------------------------------------------------------------ receipt

def status(rt: Runtime) -> dict[str, Any]:
    s = rt.settings
    out: dict[str, Any] = {}
    tz = _timezone_state(rt)
    out["timezone"] = {"ready": not tz["likely_unset"], **tz}
    if not s.configured:
        out["workspace"] = {"ready": False, "problem": "no workspace yet"}
        out["next"] = ("Confirm the timezone" if tz["likely_unset"] else "Choose a workspace") + \
            ": use an existing notes repo, or create a new task workspace."
        return out
    try:
        root = s.root()
        store = TaskStore(s, rt.data_dir)
        scan = store.scan()
        out["workspace"] = {"ready": True, "path": str(root), "tasks": len(scan.tasks),
                            "open": sum(1 for t in scan.tasks if not t.is_closed), "unparseable": len(scan.errors)}
        out["areas"] = {"ready": bool(s.known_areas()), "areas": s.known_areas(), "default": s.default_area or None}
    except ConfigError as exc:
        out["workspace"] = {"ready": False, "problem": str(exc)}
        out["next"] = "Fix the workspace path."
        return out
    git = rt.git().status()
    receipt = git.get("last_receipt") or {}
    out["git"] = {"ready": git.get("state") != "no_git" and (s.git_transport == "none" or
                                                             receipt.get("state") == "pushed"),
                  "transport": s.git_transport, "remote": git.get("remote"), "branch": git.get("branch"),
                  "last_push": receipt.get("last_push_at"), "pending": git.get("needs_push"),
                  "problem": receipt.get("last_error")}
    if s.git_transport == "none":
        out["git"]["note"] = "local history only, not backed up"
    out["research"] = {"ready": True, "automatic": s.research_by_default}
    out["checkpoints"] = {"ready": True}
    preview = jobs_preview(rt)
    out["jobs"] = {"ready": not preview["approval_needed"],
                   "jobs": {j["key"]: j["status"] for j in preview["jobs"]}}
    try:
        from . import discovery
        out["discovery"] = discovery.status_summary(rt)
    except Exception:  # noqa: BLE001
        out["discovery"] = {"ready": False, "streams": 0}
    order = ("timezone", "workspace", "areas", "git", "jobs")  # discovery streams are optional
    pending = [k for k in order if k in out and not out[k].get("ready")]
    out["next"] = pending[0] if pending else "all set"
    return out


def receipt_text(rep: dict[str, Any]) -> str:
    icon = lambda ok: "✅" if ok else "⬜"  # noqa: E731
    lines = ["**Alchemy Task setup**"]
    tz = rep.get("timezone") or {}
    lines.append(f"{icon(tz.get('ready'))} Timezone: {tz.get('timezone') or 'not set'}"
                 + (f" ({tz['local_time']})" if tz.get("local_time") else ""))
    ws = rep.get("workspace") or {}
    lines.append(f"{icon(ws.get('ready'))} Workspace: " + (f"{ws['path']} ({ws['tasks']} tasks, {ws['open']} open)"
                                                            if ws.get("ready") else ws.get("problem", "not set")))
    if "areas" in rep:
        lines.append(f"{icon(rep['areas']['ready'])} Areas: {', '.join(rep['areas']['areas']) or 'none'}")
    if "git" in rep:
        g = rep["git"]
        detail = f"{g['transport']} → {g.get('remote') or 'no remote'}"
        detail += "; pushed and verified" if g["ready"] and g["transport"] != "none" else \
            (f"; {g.get('note')}" if g.get("note") else f"; not verified ({g.get('problem') or 'no push yet'})")
        lines.append(f"{icon(g['ready'])} Git: {detail}")
    if "research" in rep:
        lines.append(f"✅ Research: {'automatic for every new task' if rep['research']['automatic'] else 'only on request'}")
        lines.append("✅ Work sessions and checkpoints: on")
    if "jobs" in rep:
        j = rep["jobs"]
        lines.append(f"{icon(j['ready'])} Scheduled jobs: " + ", ".join(f"{k} {v}" for k, v in j["jobs"].items()))
    if "discovery" in rep:
        d = rep["discovery"]
        lines.append(f"{icon(d.get('ready'))} Discovery streams: {d.get('streams', 0)}")
    lines.append(f"Next: {rep.get('next')}")
    return "\n".join(lines)
