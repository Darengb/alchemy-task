from __future__ import annotations

import dataclasses
import json
import subprocess

import pytest

from alchemy_task import jobs, runtime, task_tools
from alchemy_task import setup_flow as sf
from alchemy_task.core.config import Settings

from test_research_agent import FakeState


class SetupCtx:
    def __init__(self, settings: dict, data_dir):
        self._s = dict(settings)
        self.state = FakeState(data_dir)
        self.cron: dict[str, dict] = {}
        self.profile_name = "test"

    def get_config(self, key, default=None):
        return self._s.get(key, default)

    def set_config(self, key, value):
        self._s[key] = value

    def dispatch_tool(self, name, args):
        assert name == "cronjob_manage"
        if args["action"] == "create":
            jid = f"job{len(self.cron) + 1}"
            self.cron[jid] = dict(args)
            return json.dumps({"success": True, "job_id": jid})
        if args["action"] == "list":
            return json.dumps({"jobs": [{**v, "job_id": k, "name": v["name"]} for k, v in self.cron.items()]})
        if args["action"] == "update":
            self.cron[args["job_id"]].update({k: v for k, v in args.items() if k not in ("action", "job_id")})
            return json.dumps({"success": True, "job_id": args["job_id"]})
        if args["action"] == "remove":
            self.cron.pop(args["job_id"], None)
            return json.dumps({"success": True})
        raise AssertionError(args)


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "hermes-home"
    h.mkdir()
    monkeypatch.setattr(sf, "_hermes_home", lambda: h)
    monkeypatch.setattr(sf, "_hermes_timezone", lambda: "UTC")
    monkeypatch.setattr(sf, "_set_hermes_timezone", lambda name: True)
    return h


def make_ctx(data_dir, **settings):
    c = SetupCtx(settings, data_dir)
    runtime.bind(c)
    return c


def call(**args):
    return json.loads(task_tools.task_setup(args, session_id="setup-chat"))


def test_fresh_setup_flow(home, tmp_path, data_dir):
    ctx = make_ctx(data_dir)
    st = call(action="status")
    assert st["receipt"]["timezone"]["likely_unset"] and "Confirm the timezone" in st["receipt"]["next"]
    # jobs refuse until the timezone is confirmed
    assert call(action="save", timezone="Mars/Olympus")["needs"] == "setup"
    out = call(action="save", timezone="America/New_York", set_hermes_timezone=True)
    assert out["ok"] and "Hermes timezone updated." in out["notes"]
    ws = tmp_path / "newtasks"
    assert call(action="save", workspace_root=str(ws))["needs"] == "setup"  # missing folder without create
    out = call(action="save", workspace_root=str(ws), create_workspace=True, areas=["work", "home"],
               default_area="work")
    assert out["ok"] and (ws / ".git").is_dir() and (ws / "areas/home/tasks").is_dir()
    assert (ws / sf.OWNER_FILE).read_text().strip() == str(home.resolve())
    rep = out["receipt"]
    assert rep["workspace"]["ready"] and rep["areas"]["areas"] == ["work", "home"]
    assert not rep["git"]["ready"]
    # git: local remote, first push verified
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    g = call(action="git_check", remote_url=str(remote))
    assert g["ok"] and g["ready"], g
    # jobs: preview, refuse without approval, create, idempotent
    prev = call(action="jobs_preview")
    assert prev["approval_needed"] and {j["key"] for j in prev["jobs"]} == set(jobs.JOBS)
    assert "(America/New_York)" in prev["jobs"][0]["when"]
    assert call(action="jobs_create")["needs"] == "setup"
    made = call(action="jobs_create", user_approved=True)
    assert [r["status"] for r in made["results"]] == ["created", "created"]
    assert all(a["timezone"] == "America/New_York" for a in ctx.cron.values())
    stubs = {p.name for p in (home / "scripts").iterdir()}
    assert stubs == {spec["stub"] for spec in jobs.JOBS.values()}
    again = call(action="jobs_create", user_approved=True)
    assert [r["status"] for r in again["results"]] == ["already created"] * 2 and len(ctx.cron) == 2
    final = call(action="status")
    assert final["receipt"]["jobs"]["ready"] and final["receipt"]["git"]["ready"]
    assert "✅ Git:" in final["text"]
    # teardown removes jobs and stubs, keeps tasks and settings
    assert call(action="teardown")["needs"] == "confirm" and len(ctx.cron) == 2
    td = call(action="teardown", user_confirmed=True)
    assert ctx.cron == {} and not any((home / "scripts").iterdir()) and len(td["removed_jobs"]) == 2
    assert ctx.get_config("workspace_root") == str(ws.resolve())


@pytest.mark.parametrize("areas", [None, ["work"], ["job", "music", "app", "personal"]])
def test_fresh_workspace_area_choices(home, tmp_path, data_dir, areas):
    ctx = make_ctx(data_dir)
    ws = tmp_path / "newtasks"
    args = {"action": "save", "workspace_root": str(ws), "create_workspace": True}
    if areas is not None:
        args["areas"] = areas
    out = call(**args)
    expected = areas if areas is not None else ["general"]
    assert out["ok"], out
    assert out["receipt"]["areas"]["areas"] == expected
    assert sorted(p.name for p in (ws / "areas").iterdir()) == sorted(expected)
    if len(expected) == 1:
        assert ctx.get_config("default_area") == expected[0]
        created = json.loads(task_tools.task_create({"title": "Read the setup guide", "due": "2026-12-01",
                                                    "research": False}, session_id="setup-chat"))
        assert created["ok"], created
    else:
        assert not ctx.get_config("default_area")


def test_check_files_and_push_actions(home, workspace, data_dir, settings):
    make_ctx(data_dir, workspace_root=str(workspace), timezone="America/New_York")
    out = call(action="check_files")
    assert out["ok"] and "need an ID" in out["summary"] and out["problems"]["unsupported"]
    fixed = call(action="check_files", fix=True)
    assert "Assigned IDs to 1" in fixed["summary"] and fixed["git"]["pushed"]
    assert call(action="push")["message"].startswith("Everything is pushed")


def test_add_and_remove_areas(home, workspace, data_dir):
    ctx = make_ctx(data_dir, workspace_root=str(workspace), timezone="America/New_York")
    out = call(action="save", add_areas=["garden"])
    assert out["ok"] and ctx.get_config("areas") == ["home", "work", "garden"] and (workspace / "areas/garden/tasks").is_dir()
    assert call(action="save", remove_areas=["work"])["needs"] == "setup"  # has open tasks
    out = call(action="save", remove_areas=["garden"])
    assert out["ok"] and "garden" not in out["receipt"]["areas"]["areas"]


def test_existing_vault_inspect(home, workspace, data_dir):
    make_ctx(data_dir)
    out = call(action="inspect", path=str(workspace))
    assert out["git_repo"] and set(out["areas_found"]) == {"home", "work"} and out["tasks_found"] == 4
    assert out["preset"] == "existing"


def test_inspect_suggests_task_dir(home, tmp_path, data_dir):
    make_ctx(data_dir)
    vault = tmp_path / "vault"
    (vault / "Projects" / "Tasks").mkdir(parents=True)
    (vault / "Projects" / "Tasks" / "a.md").write_text("---\ntitle: A\ntags:\n- task\n---\n")
    out = call(action="inspect", path=str(vault))
    assert out["areas_found"] == [] and out["task_folders_elsewhere"] == {"Projects/Tasks": 1}


def test_shared_workspace_refused(home, workspace, data_dir):
    (workspace / sf.OWNER_FILE).write_text("/some/other/hermes\n")
    make_ctx(data_dir)
    out = call(action="save", workspace_root=str(workspace))
    assert out["needs"] == "setup" and "another Hermes install" in out["message"]
    assert call(action="save", workspace_root=str(workspace), allow_shared=True)["ok"]


def test_git_check_with_a_legacy_key_setting_pushes_with_system_git(home, workspace, data_dir, tmp_path):
    make_ctx(data_dir, workspace_root=str(workspace), git_transport="deploy_key", timezone="Europe/Lisbon")
    out = call(action="git_check")
    assert out["ready"], out
    assert "public_key" not in out and "add_key_at" not in out


def test_maintenance_reports_push_failure_once(home, settings, data_dir, workspace, tmp_path):
    import os
    from alchemy_task.core import precheck
    from alchemy_task.core.store import TaskStore
    from alchemy_task.core.gitops import GitDelivery
    precheck.maintenance(str(data_dir), settings=settings)  # baseline (assigns the fixture's missing ID)
    os.rename(tmp_path / "remote.git", tmp_path / "away.git")
    doc = TaskStore(settings, data_dir).create(title="Water the plants", area="home", due="2026-12-01", research=False)
    GitDelivery(settings, data_dir).deliver([TaskStore(settings, data_dir).rel(doc.path)], "x")
    first = precheck.maintenance(str(data_dir), settings=settings)
    assert "not pushed" in first
    assert precheck.maintenance(str(data_dir), settings=settings) == ""  # same failure: silent
    os.rename(tmp_path / "away.git", tmp_path / "remote.git")
    fixed = precheck.maintenance(str(data_dir), settings=settings)
    assert "Pushed task changes" in fixed
    assert precheck.maintenance(str(data_dir), settings=settings) == ""
    broken = dataclasses.replace(settings, workspace_root=str(tmp_path / "gone"))
    assert "hourly check failed" in precheck.maintenance(str(data_dir), settings=broken)
    assert precheck.maintenance(str(data_dir), settings=broken) == ""


def test_remote_not_replaced_without_permission(home, workspace, data_dir):
    make_ctx(data_dir, workspace_root=str(workspace))
    out = call(action="git_check", remote_url="git@github.com:else/where.git")
    assert out["needs"] == "setup" and "already pushes" in out["message"]


def test_stubs_run_silently_and_report(home, settings, data_dir, workspace, tmp_path):
    from pathlib import Path
    plugin = Path(sf.__file__).resolve().parent
    stub = jobs.write_stub(tmp_path / "scripts", "maintenance", plugin_dir=str(plugin), data_dir=str(data_dir))
    text = stub.read_text()
    compile(text, "stub", "exec")
    assert str(plugin) in text and str(data_dir) in text
    # call the function the stub calls: hand-made task gets an ID, then the next run is silent
    from alchemy_task.core import precheck
    first = precheck.maintenance(str(data_dir), settings=settings)
    assert "Assigned IDs to 1 task(s)" in first and "Task file check" in first
    assert precheck.maintenance(str(data_dir), settings=settings) == ""
    gone = jobs.stub_text("research-sweep", plugin_dir="/nonexistent", data_dir=str(data_dir))
    out = subprocess.run(["python3", "-c", gone], capture_output=True, text=True)
    assert out.stdout.strip() == '{"wakeAgent": false}'
