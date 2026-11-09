"""Create a synthetic demo workspace (a Git repo of TaskNotes) from the preview harness's demo data.

Usage: python ui/dev/seed_workspace.py <workspace-dir> <demo.json>
where demo.json comes from: node ui/dev/dump-demo.mjs > demo.json
Dates in the demo data are relative to the day the dump ran. Nothing here touches a real workspace.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("alchemy_task", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
pkg = importlib.util.module_from_spec(spec)
sys.modules["alchemy_task"] = pkg
spec.loader.exec_module(pkg)

from alchemy_task.core.config import Settings  # noqa: E402
from alchemy_task.core.store import TaskStore  # noqa: E402


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def main(ws: Path, demo: Path) -> None:
    data = json.loads(demo.read_text())
    if ws.exists() and any(ws.iterdir()):
        raise SystemExit(f"{ws} is not empty")
    ws.mkdir(parents=True, exist_ok=True)
    git(ws, "init", "-q", "-b", "main")
    for area in data["areas"]:
        (ws / "areas" / area / "tasks").mkdir(parents=True, exist_ok=True)
    settings = Settings(workspace_root=str(ws), areas=data["areas"], default_area=data["areas"][0],
                        timezone="America/New_York", research_by_default=False)
    data_dir = ws.parent / "plugin-data"
    data_dir.mkdir(exist_ok=True)
    store = TaskStore(settings, data_dir)
    for t in data["tasks"]:
        doc = store.create(title=t["title"], area=t["area"], due=t["due"] or "", undated=not t["due"],
                           scheduled=t["scheduled"] or "", priority=t.get("priority") or "normal",
                           summary=t.get("summary") or "", research=False, research_skip_reason="demo data",
                           confirm_new=True, source="demo")
        if t.get("body"):
            doc, _ = store.replace_body(doc.task_id, t["body"], expect_revision=None, log="")
        if t.get("status") and t["status"] != "open":
            reason = "Waiting on the designer" if t["status"] == "waiting" else ""
            store.update(doc.task_id, {"status": t["status"], "reason": reason, "completed": t.get("completed") or "",
                                       "log": "Demo status."})
    git(ws, "add", "-A")
    git(ws, "-c", "user.name=Demo", "-c", "user.email=demo@example.com", "commit", "-q", "-m", "Demo tasks")
    print(f"Seeded {len(data['tasks'])} tasks in {ws}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser().resolve(), Path(sys.argv[2]))
