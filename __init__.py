"""Alchemy Task: turns messy operator work into tracked, researched, finished tasks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import discovery, handoff, research_agent, runtime, worksession
from .commands import task_command
from .core.config import Settings
from .task_tools import register_tools

_HERE = Path(__file__).resolve().parent


# Hermes skips (does not truncate) a section over its max_chars, so tests keep both texts under this limit.
PROMPT_SECTION_MAX = 800


def _prompt_section(_info: Any = None) -> str:
    try:
        s = Settings.load(runtime._ctx.get_config) if runtime._ctx is not None else Settings()
    except Exception:  # noqa: BLE001
        s = Settings()
    if not s.configured:
        return ("Alchemy Task (task plugin) is installed but not set up. When the user talks about tasks, offer "
                "to set it up. To set it up, load the skill alchemy-task:setup and follow it.")
    return ("Alchemy Task manages the user's tasks as Markdown files. Create, change and look up tasks only "
            "with task_create, task_update and task_find; do not edit task files with file tools. Ask for a due "
            "date when the user gives none. Users speak plainly instead of using /task commands: \"is everything "
            "working\", \"sync my tasks\", \"check my task files\", \"work on X\", \"set up a daily digest\" all map "
            "to the plugin's tools. For the full mapping and conventions load the skill alchemy-task:tasks. When "
            "work for later comes up in a chat with the user, ask once if they want a task for it (rules in that "
            "skill).")


def register(ctx: Any) -> None:
    runtime.bind(ctx)
    research_agent.reload_children(ctx)
    register_tools(ctx)
    research_agent.register(ctx)
    worksession.register(ctx)
    discovery.register(ctx)
    from . import discovery_integration
    discovery_integration.register(ctx)
    handoff.register(ctx)
    ctx.register_skill("discovery", _HERE / "skills" / "discovery" / "SKILL.md",
                       description="Use when setting up or running Alchemy Task discovery streams, or when the user "
                                   "replies to a discovery digest.")
    if research_agent.on_task_created not in runtime.research_listeners:
        runtime.research_listeners.append(research_agent.on_task_created)
    ctx.register_skill("tasks", _HERE / "skills" / "tasks" / "SKILL.md",
                       description="Use when creating, updating or finding the user's tasks with Alchemy Task.")
    ctx.register_skill("setup", _HERE / "skills" / "setup" / "SKILL.md",
                       description="Use when the user wants to set up or change Alchemy Task (\"set up my tasks\").")
    ctx.register_command("task", handler=task_command, description="Alchemy Task: status, validate, push, setup",
                         args_hint="[status|validate|push|setup]")
    ctx.register_system_prompt_section("alchemy-task", _prompt_section, max_chars=PROMPT_SECTION_MAX)
