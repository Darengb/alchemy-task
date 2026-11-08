"""Scheduled jobs Alchemy Task asks to create during setup.

Setup (``/task setup``) shows this inventory, asks once, copies each stub into
``$HERMES_HOME/scripts/`` (cron only runs scripts from there) and creates the
jobs with ``ctx.dispatch_tool("cronjob_manage", ...)``. Stubs are thin: they
add the plugin folder to ``sys.path`` and call plugin code, so plugin updates
change behaviour without touching the copied files. A stub prints
``{"wakeAgent": false}`` when there is nothing to do, so idle ticks cost no
model call, and stays silent if the plugin has been removed.
"""
from __future__ import annotations

PREFIX = "alchemy-task"

STUB = """\
# Alchemy Task {name} pre-check (copied by /task setup; safe to delete with /task teardown).
import json, os, sys
from pathlib import Path
plugin = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "plugins" / "alchemy-task"
if not (plugin / "jobs.py").exists():
    print(json.dumps({{"wakeAgent": False}}))
    sys.exit(0)
sys.path.insert(0, str(plugin.parent))
import importlib.util
spec = importlib.util.spec_from_file_location("alchemy_task", plugin / "__init__.py",
                                              submodule_search_locations=[str(plugin)])
mod = importlib.util.module_from_spec(spec); sys.modules["alchemy_task"] = mod
from alchemy_task.core import precheck  # noqa: E402  (core has no Hermes imports)
print(json.dumps(precheck.{func}()))
"""

JOBS = {
    "research-recovery": {
        "schedule": "every 30m",
        "mode": "agent, behind a free pre-check",
        "stub": "alchemy_task_research_precheck.py",
        "func": "research_wake",
        "toolsets": ["alchemy-task", "alchemy-task-research", "web"],
        "prompt": ("Alchemy Task research sweep. Call task_research with no task argument to research tasks "
                   "that are still waiting or whose research stalled. Then reply with one short line: how many "
                   "were started and finished. Do nothing else."),
        "why": "Retries research that could not start or stopped early (for example after a restart).",
        "cost": "No model call when nothing is waiting; otherwise one short turn plus the research itself.",
    },
}


def stub_text(job: str) -> str:
    spec = JOBS[job]
    return STUB.format(name=job, func=spec["func"])
