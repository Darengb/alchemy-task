"""Settings resolution. Plugin settings live under
``plugins.entries.alchemy-task.settings`` in the active profile's config.yaml."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TASK_DIR = "areas/{area}/tasks"
TRANSPORTS = ("system", "deploy_key", "token", "none")
TOKEN_ENV = "ALCHEMY_TASK_GIT_TOKEN"
_AREA_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class ConfigError(ValueError):
    pass


@dataclass
class Settings:
    workspace_root: str = ""
    task_dir: str = DEFAULT_TASK_DIR
    areas: list[str] = field(default_factory=list)
    default_area: str = ""
    timezone: str = ""
    research_by_default: bool = True
    git_transport: str = "system"
    git_remote: str = "origin"
    git_branch: str = ""
    git_run_hooks: bool = True
    git_allow_repo_programs: bool = False

    @classmethod
    def load(cls, get: Callable[[str, Any], Any], hermes_timezone: str = "") -> "Settings":
        def g(key: str, default: Any) -> Any:
            value = get(key, default)
            return default if value is None else value

        areas = g("areas", [])
        if isinstance(areas, str):
            areas = [a.strip() for a in areas.split(",") if a.strip()]
        return cls(
            workspace_root=str(g("workspace_root", "")).strip(),
            task_dir=str(g("task_dir", DEFAULT_TASK_DIR)).strip() or DEFAULT_TASK_DIR,
            areas=[str(a).strip().lower() for a in areas if str(a).strip()],
            default_area=str(g("default_area", "")).strip().lower(),
            timezone=str(g("timezone", "")).strip() or hermes_timezone,
            research_by_default=bool(g("research_by_default", True)),
            git_transport=str(g("git_transport", "system")).strip() or "system",
            git_remote=str(g("git_remote", "origin")).strip() or "origin",
            git_branch=str(g("git_branch", "")).strip(),
            git_run_hooks=bool(g("git_run_hooks", True)),
            git_allow_repo_programs=bool(g("git_allow_repo_programs", False)),
        )

    # ---------------------------------------------------------------- derived

    @property
    def configured(self) -> bool:
        return bool(self.workspace_root)

    def root(self) -> Path:
        if not self.workspace_root:
            raise ConfigError("Alchemy Task has no workspace yet. Run `/task setup` or say \"set up my tasks\".")
        root = Path(self.workspace_root).expanduser()
        if not root.is_absolute():
            raise ConfigError(f"workspace_root must be an absolute path, got {self.workspace_root!r}")
        if not root.is_dir():
            raise ConfigError(f"workspace folder does not exist: {root}")
        return root.resolve()

    def tz(self) -> ZoneInfo:
        name = self.timezone or "UTC"
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    def today(self) -> str:
        return dt.datetime.now(self.tz()).date().isoformat()

    def now_utc_iso(self) -> str:
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    def area_dir(self, area: str) -> Path:
        area = validate_area_name(area)
        if "{area}" not in self.task_dir:
            raise ConfigError("task_dir must contain {area}")
        rel = Path(self.task_dir.replace("{area}", area))
        if rel.is_absolute() or ".." in rel.parts:
            raise ConfigError("task_dir must be a relative path inside the workspace")
        return self.root() / rel

    def known_areas(self) -> list[str]:
        """Configured areas plus any area folders that already exist on disk."""
        found: list[str] = list(self.areas)
        prefix, _, suffix = self.task_dir.partition("{area}")
        base = self.root() / prefix
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_dir() and _AREA_RE.match(child.name):
                    if (child / suffix.lstrip("/")).is_dir() if suffix.strip("/") else True:
                        found.append(child.name)
        return list(dict.fromkeys(found))


def validate_area_name(area: str) -> str:
    area = str(area or "").strip().lower()
    if not _AREA_RE.match(area):
        raise ConfigError(f"invalid area name {area!r}: use lowercase letters, digits and hyphens")
    return area
