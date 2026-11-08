"""Alchemy Task: turns messy operator work into tracked, researched, finished tasks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import runtime
from .commands import task_command
from .core.config import Settings
from .task_tools import register_tools

_HERE = Path(__file__).resolve().parent


def _prompt_section(_info: Any = None) -> str:
    try:
        s = Settings.load(runtime._ctx.get_config) if runtime._ctx is not None else Settings()
    except Exception:  # noqa: BLE001
        s = Settings()
    if not s.configured:
        return ("Alchemy Task (task plugin) is installed but not set up. When the user talks about tasks, "
                "offer to set it up; the user can say \"set up my tasks\".")
    return ("Alchemy Task manages the user's tasks as Markdown files. Create, change and look up tasks only "
            "with task_create, task_update and task_find; do not edit task files with file tools. Ask for a due "
            "date when the user gives none. For conventions load the skill alchemy-task:tasks.")


def register(ctx: Any) -> None:
    runtime.bind(ctx)
    register_tools(ctx)
    ctx.register_skill("tasks", _HERE / "skills" / "tasks" / "SKILL.md",
                       description="Use when creating, updating or finding the user's tasks with Alchemy Task.")
    ctx.register_command("task", handler=task_command, description="Alchemy Task: status, validate, push, setup",
                         args_hint="[status|validate|push|setup]")
    ctx.register_system_prompt_section("alchemy-task", _prompt_section, max_chars=600)
