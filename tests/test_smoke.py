"""Light smoke tests: does the core still work end to end?

Keep this suite small. Test outcomes a user would notice (a task is created, a date
resolves, a proposal becomes a task), never exact wording, field order or other
details that change on purpose.
"""
from __future__ import annotations

import json

import pytest

from alchemy_task.core import taskfile as tf
from alchemy_task.core.store import NeedsInput, TaskStore
from fakes import FakeCtx
from helpers import FIXTURES


def test_plugin_registers_tools_skills_and_hooks(data_dir):
    import alchemy_task
    ctx = FakeCtx({}, data_dir)
    alchemy_task.register(ctx)
    names = {(a[0] if a else k.get("name")) for n, a, k in ctx.calls if n == "register_tool"}
    assert {"task_create", "task_update", "task_find", "task_setup", "discovery_start", "discovery_decide"} <= names
    assert {a[0] for n, a, _ in ctx.calls if n == "register_skill"} == {"tasks", "setup", "discovery"}
    assert any(n == "register_hook" for n, _, _ in ctx.calls)


def test_task_lifecycle(settings, data_dir):
    store = TaskStore(settings, data_dir)
    with pytest.raises(NeedsInput):
        store.create(title="Call the plumber", area="home")  # no date
    doc = store.create(title="Call the plumber", area="home", due="2026-11-09", research=False)
    assert doc.fm["due"] == "2026-11-09" and doc.fm["status"] == "open"
    assert [t.task_id for t in store.find(query="plumber")] == [doc.task_id]
    done, _, _ = store.update(doc.task_id, {"status": "done"})
    assert done.fm["status"] == "done" and done.fm["completed"]
    assert store.find(query="plumber") == []  # closed tasks are hidden by default


def test_date_words_and_agenda(settings, data_dir):
    sunday = "2026-11-08"
    assert tf.parse_date_words("Friday", sunday) == "2026-11-13"
    assert tf.parse_date_words("tomorrow", sunday) == "2026-11-09"
    with pytest.raises(tf.TaskFormatError):
        tf.parse_date_words("someday", sunday)
    store = TaskStore(settings, data_dir)
    store.create(title="Pay the electric bill", area="home", due="2026-11-09", research=False)
    store.create(title="Call the landlord", area="home", due="2026-11-01", research=False)
    store.create(title="Plan next quarter", area="work", due="2026-12-15", research=False)
    titles = {t.title for t, _ in store.agenda("2026-11-09", "2026-11-09", today="2026-11-09")}
    assert {"Pay the electric bill", "Call the landlord"} <= titles  # due today, and overdue
    assert "Plan next quarter" not in titles


def test_task_tools_through_the_runtime(settings, data_dir):
    from alchemy_task import runtime, task_tools
    ctx = FakeCtx({"workspace_root": settings.workspace_root, "timezone": settings.timezone}, data_dir)
    runtime.bind(ctx)
    made = json.loads(task_tools.task_create({"title": "Order new filters", "area": "home", "due": "2026-11-20",
                                              "research": False}))
    assert made["ok"], made
    task_id = made["task"]["task_id"]
    found = json.loads(task_tools.task_find({"query": "filters"}))
    assert [t["task_id"] for t in found["tasks"]] == [task_id]
    updated = json.loads(task_tools.task_update({"task": task_id, "due": "2026-11-23"}))
    assert updated["ok"] and updated["task"]["due"] == "2026-11-23"


def test_setup_creates_workspace_and_jobs(tmp_path, data_dir, monkeypatch):
    from alchemy_task import runtime, setup_flow as sf, task_tools
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setattr(sf, "_hermes_home", lambda: home)
    monkeypatch.setattr(sf, "_hermes_timezone", lambda: "UTC")
    monkeypatch.setattr(sf, "_set_hermes_timezone", lambda name: True)
    ctx = FakeCtx({}, data_dir)
    runtime.bind(ctx)
    call = lambda **a: json.loads(task_tools.task_setup(a, session_id="chat"))  # noqa: E731
    assert call(action="save", timezone="America/New_York")["ok"]
    ws = tmp_path / "tasks"
    out = call(action="save", workspace_root=str(ws), create_workspace=True, areas=["work", "home"], default_area="work")
    assert out["ok"] and (ws / "areas" / "home" / "tasks").is_dir()
    assert call(action="jobs_create", user_approved=True)["ok"] and ctx.cron
    assert call(action="status")["receipt"]["jobs"]["ready"]


def test_research_bundle_validation():
    from alchemy_task.core import discovery_research as research
    bundle = json.loads((FIXTURES / "discovery" / "bundle.json").read_text())
    sources = ["slack:T1:C1:171.1"]
    assert research.validate_bundle(bundle, bundle["candidate_id"], sources)
    bundle["workstreams"][0]["suggested_due"] = "2026-11-23"
    assert research.validate_bundle(bundle, bundle["candidate_id"], sources)[0][1]["suggested_due"] == "2026-11-23"
    bundle["workstreams"][0]["user_role"] = "waiting_on"
    assert research.validate_bundle(bundle, bundle["candidate_id"], sources)[0][1]["user_role"] == "waiting_on"
    for bad in ({"title": None}, {"suggested_due": "Monday"}, {"user_role": "someone"}):
        broken = json.loads(json.dumps(bundle))
        broken["workstreams"][0].update(bad)
        with pytest.raises(research.UserError):
            research.validate_bundle(broken, broken["candidate_id"], sources)


def _accepted_run(data_dir, *, suggested_due=None, extra=None):
    """One discovery run whose single item has accepted research, as a parent agent would leave it."""
    import hashlib
    from alchemy_task.core.discovery_state import DiscoveryStore
    store = DiscoveryStore(data_dir / "discovery")
    run = store.init_run(stream="work", business_date="2030-01-01", config={"sources": ["work"], "mode": "production"})
    item = store.add_candidates(run, [{"title": "Ask", "source_ids": [{"type": "slack", "workspace_id": "T1", "channel_id": "C1",
                                                                      "thread_root_ts": "171.1", "message_ts": "171.2"}]}])[0]
    store.freeze_index(run, rubric="Read complete sources.")

    def read_all(name, reader):
        rev, cursor = store.resource_info(run, name)["sha256"], None
        while True:
            page = store.fetch_resource(run, name, revision=rev, reader=reader, cursor=cursor, limit=4000)
            assert hashlib.sha256(page["content"].encode()).hexdigest() == page["page_sha256"]
            if not page["has_more"]:
                return
            cursor = page["next_cursor"]

    with store._lock(store._run_lock_name(run)):
        ledger = store.get_run(run)
        ledger["origin"] = {"session_id": "parent"}
        store._save(run, ledger)
    attempt = store.reserve_attempt(run, item["candidate_id"], owner_session="parent", daily_limit=1000)
    token = attempt["token"]
    store.record_start(run, parent_session="parent", child_session="child-" + token, subagent_id="sa-" + token)
    store.bind_attempt(run, token, {"subagent_id": "sa-" + token}, owner_session="parent")
    for name in attempt["required_resources"]:
        read_all(name, token)
    bundle = json.loads((FIXTURES / "discovery" / "bundle.json").read_text())
    bundle["candidate_id"] = item["candidate_id"]
    if suggested_due:
        bundle["workstreams"][0]["suggested_due"] = suggested_due
    bundle["workstreams"][0].update(extra or {})
    receipt = store.spool_payload(run, token, bundle)
    store.observe_terminal(run, token, state="SUCCEEDED", receipt={"state": "SUCCEEDED"})
    read_all(receipt["resource"], "parent")
    store.accept_attempt(run, token, payload_sha256=receipt["payload_sha256"],
                         assessment={"accepted": True, "reason": "Complete research."}, reader="parent")
    store.put_resource(run, "join-record", {"joined": True, "accepted": [item["candidate_id"]], "failures": []})
    return store, run


def test_discovery_proposal_becomes_a_task(settings, data_dir, tmp_path):
    from alchemy_task import runtime
    from alchemy_task.discovery_integration import DiscoveryIntegration
    ctx = FakeCtx({"workspace_root": settings.workspace_root, "timezone": settings.timezone}, data_dir)
    rt = runtime.Runtime(ctx, settings, data_dir)
    ctx.state.set("streams", {"work": {"name": "work", "mode": "production", "areas": ["work"], "research_cap": 50,
                                       "sources": [{"name": "Feed", "scope": ["board"], "method": "reader"}],
                                       "deliver": "origin", "origin_session": "parent", "label": ""}})
    store, run = _accepted_run(data_dir, suggested_due="2030-01-07")
    integration = DiscoveryIntegration(rt, profile_home=tmp_path / "profile")
    for c in store.get_run(run)["candidates"]:
        if c.get("parent_candidate_id"):
            integration.record_decision(run, c["candidate_id"], decision="propose", reason="New action.", session_id="parent")
    digest = integration.finalize(run, session_id="parent")
    assert len(digest["items"]) == 1 and digest["text"]
    before = len(rt.store().scan().tasks)
    # "1, create" with no date: the task takes the date research found in the source.
    result = integration.decide({"approve": ["1"], "day": "2030-01-01", "edits": {"1": {"area": "work"}}},
                                session_id="parent", today="2030-01-02")
    tasks = rt.store().scan().tasks
    assert len(tasks) == before + 1
    task = next(t for t in tasks if t.task_id == result["results"][0]["task_id"])
    assert str(task.fm["due"]) == "2030-01-07"


def test_someone_elses_action_is_not_proposed(settings, data_dir, tmp_path):
    from alchemy_task import runtime
    from alchemy_task.core.attention import NOT_PROPOSED, sort_failures
    from alchemy_task.discovery_integration import DiscoveryIntegration
    ctx = FakeCtx({"workspace_root": settings.workspace_root, "timezone": settings.timezone}, data_dir)
    rt = runtime.Runtime(ctx, settings, data_dir)
    ctx.state.set("streams", {"work": {"name": "work", "mode": "production", "areas": ["work"], "research_cap": 50,
                                       "sources": [{"name": "Feed", "scope": ["board"], "method": "reader"}],
                                       "deliver": "origin", "origin_session": "parent", "label": ""}})
    store, run = _accepted_run(data_dir, extra={"user_role": "none", "owner_and_collaborators": [{"name": "Doug", "role": "owner"}]})
    integration = DiscoveryIntegration(rt, profile_home=tmp_path / "profile")
    for c in store.get_run(run)["candidates"]:
        if c.get("parent_candidate_id"):
            integration.record_decision(run, c["candidate_id"], decision="propose", reason="New action.", session_id="parent")
    digest = integration.finalize(run, session_id="parent")
    attention, _, not_proposed = sort_failures(digest["failures"])
    assert digest["items"] == [] and attention == []
    assert [f["group"] for f in not_proposed] == [NOT_PROPOSED] and "Doug" in not_proposed[0]["text"]


def test_resolved_runs_leave_the_discovery_list(settings, data_dir, tmp_path):
    """The badge counts pending proposals from the saved summaries; once every item of a run is
    resolved, the run drops out of the default Discovery list."""
    from alchemy_task import runtime
    from alchemy_task.discovery_integration import DiscoveryIntegration
    ctx = FakeCtx({"workspace_root": settings.workspace_root, "timezone": settings.timezone}, data_dir)
    rt = runtime.Runtime(ctx, settings, data_dir)
    ctx.state.set("streams", {"work": {"name": "work", "mode": "production", "areas": ["work"], "research_cap": 50,
                                       "sources": [{"name": "Feed", "scope": ["board"], "method": "reader"}],
                                       "deliver": "origin", "origin_session": "parent", "label": ""}})
    store, run = _accepted_run(data_dir, suggested_due="2030-01-07")
    integration = DiscoveryIntegration(rt, profile_home=tmp_path / "profile")
    for c in store.get_run(run)["candidates"]:
        if c.get("parent_candidate_id"):
            integration.record_decision(run, c["candidate_id"], decision="propose", reason="New action.", session_id="parent")
    integration.finalize(run, session_id="parent")
    before = integration.badge()
    assert before["pending"] == 1 and before["has_runs"]
    assert [v["run_id"] for v in integration.summary_views() if v["needs_attention"]] == [run]
    integration.decide({"dismiss": ["1"], "day": "2030-01-01"}, session_id="parent", today="2030-01-02")
    after = integration.badge()
    assert after["pending"] == 0 and after["version"] > before["version"]
    assert not [v for v in integration.summary_views() if v["needs_attention"]]
    # A rebuild from the detailed records gives the same answer.
    integration.summaries.invalidate()
    assert integration.badge()["pending"] == 0


def test_task_edits_after_indexing_change_exact_matches(settings, data_dir):
    """Matching sees task edits made after the index was built, and closed tasks are never targets."""
    from alchemy_task import runtime
    from alchemy_task.core import task_index
    from alchemy_task.discovery_conversion import DiscoveryConversion
    rt = runtime.Runtime(FakeCtx({"workspace_root": settings.workspace_root, "timezone": settings.timezone}, data_dir), settings, data_dir)
    store, run = _accepted_run(data_dir)
    unit = next(c["candidate_id"] for c in store.get_run(run)["candidates"] if c.get("parent_candidate_id"))
    conversion = DiscoveryConversion(rt, store)
    assert conversion.match(run, unit)["kind"] == "new"
    folder = settings.root() / "areas" / "work" / "tasks"
    newsletter, venue = folder / "2026-11-01-draft-the-spring-newsletter.md", folder / "2026-11-05-book-venue-for-the-offsite.md"
    action = store.get_candidate(run, unit).get("action_id")
    for path in (newsletter, venue):
        text = path.read_text().replace("tags:", "discovery_action_ids: [%s]\ntags:" % (action or "none"), 1)
        path.write_text(text + "\nFrom the thread slack:T1:C1:171.1:171.2\n")
    found = conversion.match(run, unit)
    assert found["kind"] == "conflict" and len(found["targets"]) == 2
    newsletter.write_text(newsletter.read_text().replace("status: open", "status: cancelled", 1))
    task_index._memory.clear()  # a restarted process reads the saved index
    found = conversion.match(run, unit)
    assert found["kind"] == "exact" and [t["path"] for t in found["targets"]] == ["areas/work/tasks/" + venue.name]


def test_research_children_cannot_write_or_read_credentials():
    from alchemy_task.core.research_guard import is_write_like, refuse_file_read
    assert is_write_like("mcp__gmail__send_email") and is_write_like("write_file") and is_write_like("terminal")
    assert not is_write_like("mcp__gmail__list_messages") and not is_write_like("read_file")
    assert refuse_file_read("read_file", {"path": "/home/u/.hermes/.env"})
    assert refuse_file_read("read_file", {"path": "/home/u/project/README.md"}) is None


def test_only_lost_items_raise_an_alarm():
    from alchemy_task.core.attention import ATTENTION, MOVED, NOT_PROPOSED, classify
    group = lambda **f: classify(f)["group"]  # noqa: E731
    assert group(reason="not finished within this run's research time: no callback") == MOVED
    assert group(reason="lifecycle terminal FAILED", retry_pending=True) == MOVED
    assert group(reason="The sole action duplicates accepted w_" + "a" * 20 + ".") == NOT_PROPOSED
    assert group(reason="not reviewed in this run") == NOT_PROPOSED
    assert group(kind="covered", reason="Same ask as M6.") == NOT_PROPOSED
    assert group(reason="lifecycle terminal FAILED", retry_pending=False) == ATTENTION
    assert group(reason="could not be matched to your tasks: bad file") == ATTENTION
    unreadable = classify({"reason": "The email's four image attachments can't be read here; open it to check them."})
    assert unreadable["group"] == ATTENTION and "image" in unreadable["text"]


def test_resources_are_stored_once_and_survive_migration_and_prune(data_dir):
    import hashlib, os
    from alchemy_task.core.discovery_state import DiscoveryStore
    store = DiscoveryStore(data_dir / "discovery")
    a, b = store.init_run("run-a"), store.init_run("run-b")
    shared = store.put_resource(a, "task-body-x", "same body")["sha256"]
    assert store.put_resource(b, "task-body-x", "same body")["sha256"] == shared
    only_a = store.put_resource(a, "task-body-y", "only in a")["sha256"]
    blobs = [p for p in (store.state_root / "blobs").rglob("*") if p.is_file()]
    assert sorted(p.name for p in blobs) == sorted({shared, only_a})
    # A run written before the shared store: its copy lives in runs/<id>/resources.
    legacy_data = b"legacy bytes"
    legacy_sha = hashlib.sha256(legacy_data).hexdigest()
    ledger_path = store.run_dir(b) / "ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["resources"]["old"] = {"name": "old", "sha256": legacy_sha, "total_bytes": len(legacy_data), "entry_count": None}
    ledger_path.write_text(json.dumps(ledger))
    (store.run_dir(b) / "resources").mkdir()
    (store.run_dir(b) / "resources" / legacy_sha).write_bytes(legacy_data)
    assert store.read_resource_bytes(b, legacy_sha) == legacy_data
    before = ledger_path.read_bytes()
    assert store.migrate_resources(dry_run=True)["blobs_created"] == 1
    assert (store.run_dir(b) / "resources" / legacy_sha).exists()
    done = store.migrate_resources(dry_run=False)
    assert done["legacy_files_removed"] == 1 and not done["problems"]
    assert not (store.run_dir(b) / "resources").exists() and ledger_path.read_bytes() == before
    assert store.read_resource_bytes(b, legacy_sha) == legacy_data
    assert store.migrate_resources(dry_run=False)["files"] == 0
    # Pruning run A drops its unique blob but keeps the one run B still names.
    path_a = store.run_dir(a) / "ledger.json"
    ledger_a = json.loads(path_a.read_text()); ledger_a["status"] = "finalized"; path_a.write_text(json.dumps(ledger_a))
    old = 1_000_000_000
    for p in [path_a, *(store.state_root / "blobs").rglob("*")]:
        os.utime(p, (old, old))
    result = store.prune(days=0)
    assert result["deleted_runs"] == [a] and result["blobs_removed"] == 1
    assert store.read_resource_bytes(b, shared) == b"same body"
    assert not store.blob_path(only_a).exists()
