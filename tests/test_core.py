from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from alchemy_task.core import taskfile as tf
from alchemy_task.core import validator
from alchemy_task.core.store import NeedsInput, TaskStore

from helpers import FIXTURES, git

NEWSLETTER = "3f2b8c1e-5d4a-4b6f-9e21-7a8c9d0e1f23"
LICENSES = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"


def fm_block(text: str, key: str) -> str:
    """Raw YAML lines of one top-level key (to prove bytes are untouched)."""
    lines = text.split("---\n", 2)[1].split("\n")
    out, on = [], False
    for line in lines:
        if line.startswith(f"{key}:"):
            on = True
        elif on and line and not line.startswith(" "):
            break
        if on:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- format

def test_canonical_fixture_rerenders_byte_identical():
    doc = tf.parse_file(FIXTURES / "2026-11-01-draft-the-spring-newsletter.md")
    assert tf.is_canonical(doc)


def test_append_log_stops_before_managed_block():
    body = (FIXTURES / "2026-11-01-draft-the-spring-newsletter.md").read_text().split("---\n\n", 1)[1]
    out = tf.append_log(body, "Sent draft to Priya", "2026-11-08")
    log_part = out.split("## Log", 1)[1].split("<!-- task-research-dossier:start", 1)[0]
    assert "- 2026-11-01: Created from chat.\n- 2026-11-08: Sent draft to Priya\n" in log_part
    # The dossier block and the legacy trailing log line stay byte-identical.
    assert body.split("<!-- task-research-dossier:start")[1] == out.split("<!-- task-research-dossier:start")[1]


def test_append_log_after_template_comment_and_creates_missing_section():
    body = "## Notes\n\nx\n\n## Log\n\n<!-- Append-only progress notes: - YYYY-MM-DD: <note> -->\n"
    assert tf.append_log(body, "first", "2026-11-08").endswith("<note> -->\n- 2026-11-08: first\n")
    assert tf.append_log("## Notes\n\nx\n", "hi", "2026-11-08") == "## Notes\n\nx\n\n## Log\n\n- 2026-11-08: hi\n"


def test_append_log_before_next_heading():
    body = "## Log\n\n- 2026-11-01: a\n\n## Extra\n\ntext\n"
    assert tf.append_log(body, "b", "2026-11-02") == "## Log\n\n- 2026-11-01: a\n- 2026-11-02: b\n\n## Extra\n\ntext\n"


def test_fill_identity_is_one_line_edit_keeping_comments():
    text = (FIXTURES / "2026-11-05-book-venue-for-the-offsite.md").read_text()
    new, tid = tf.fill_identity_text(text)
    assert tf.valid_task_id(tid)
    old_lines, new_lines = text.split("\n"), new.split("\n")
    assert len(old_lines) == len(new_lines)
    diff = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
    assert diff == [("task_id:              # leave blank; assigned automatically", f"task_id: {tid}")]


def test_slugify_and_similarity():
    assert tf.slugify("Book venue: offsite (Q1) — Café!") == "book-venue-offsite-q1-cafe"
    assert tf.slugify("Confirm Saturday's load-in") == "confirm-saturdays-load-in"
    assert tf.title_similarity("Draft the spring newsletter", "draft spring newsletter") == 1.0
    assert tf.title_similarity("Draft newsletter", "Book venue") == 0.0


# ---------------------------------------------------------------- store

def test_scan_ignores_untagged_and_reports(settings, data_dir):
    scan = TaskStore(settings, data_dir).scan()
    titles = {t.title for t in scan.tasks}
    assert "Meeting notes" not in titles and "Draft the spring newsletter" in titles
    assert any(p.name == "meeting-notes.md" for p in scan.untagged)


def test_create_requires_due_and_area(settings, data_dir):
    store = TaskStore(settings, data_dir)
    with pytest.raises(NeedsInput) as e:
        store.create(title="Call the plumber", area="home")
    assert e.value.kind == "due"
    with pytest.raises(NeedsInput) as e:
        store.create(title="Call the plumber", due="2026-11-09")
    assert e.value.kind == "area" and set(e.value.data["known_areas"]) == {"home", "work"}
    with pytest.raises(NeedsInput) as e:
        store.create(title="Call the plumber", area="garden", due="2026-11-09")
    assert e.value.kind == "area"
    with pytest.raises(tf.TaskFormatError):
        store.create(title="Call the plumber", area="home", due="2026-02-30")


def test_create_writes_expected_task(settings, data_dir):
    store = TaskStore(settings, data_dir)
    doc = store.create(title="  Call the   plumber about the leak ", area="home", due="2026-11-09",
                       notes="Kitchen sink.", subtasks=["Find the warranty"], contexts=["phone"], source="Telegram")
    assert re.match(r"areas/home/tasks/\d{4}-\d{2}-\d{2}-call-the-plumber-about-the-leak\.md$", store.rel(doc.path))
    fm = doc.fm
    assert list(fm)[:4] == ["title", "task_id", "schema_version", "status"]
    assert fm["title"] == "Call the plumber about the leak" and tf.valid_task_id(fm["task_id"])
    assert fm["schema_version"] == 1 and fm["tags"] == ["task"] and fm["contexts"] == ["@phone"]
    assert fm["due"] == "2026-11-09" and fm["enrichment"]["status"] == "pending"
    assert tf.is_canonical(doc)
    assert "- [ ] Find the warranty" in doc.body
    assert re.search(r"- \d{4}-\d{2}-\d{2}: Created from Telegram\. Research queued\.", doc.body)
    assert "due: '2026-11-09'" in doc.raw.decode()
    bare = store.create(title="Pay the water bill", area="home", due="2026-11-09", research=False,
                        research_skip_reason="User said no research needed.")
    assert bare.body.startswith("## Notes\n\n## Log\n\n- ")
    assert bare.body.rstrip().endswith("Research skipped: User said no research needed.")


def test_create_duplicate_check_and_confirm(settings, data_dir):
    store = TaskStore(settings, data_dir)
    with pytest.raises(NeedsInput) as e:
        store.create(title="Draft spring newsletter", area="work", due="2026-11-12")
    assert e.value.kind == "duplicate_check"
    assert e.value.data["candidates"][0]["task_id"] == NEWSLETTER
    # Closed tasks do not block.
    store.create(title="Renew the team software licenses", area="work", due="2027-10-30")
    doc = store.create(title="Draft spring newsletter", area="work", due="2026-11-12", confirm_new=True,
                       research=False, research_skip_reason="user said no research")
    assert doc.fm["enrichment"]["status"] == "skipped"


def test_update_done_sets_completed_and_preserves_owned_blocks(settings, data_dir):
    store = TaskStore(settings, data_dir)
    path = settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md"
    before = path.read_text()
    doc, paths, notes = store.update(NEWSLETTER, {"status": "done", "log": "Sent to the list"})
    after = path.read_text()
    assert doc.fm["status"] == "done" and doc.fm["completed"] == settings.today()
    for key in ("google_tasks", "enrichment", "tags", "contexts", "project"):
        assert fm_block(before, key) == fm_block(after, key)
    assert before.split("<!-- task-research-dossier:start")[1] == after.split("<!-- task-research-dossier:start")[1]
    assert f"- {settings.today()}: Sent to the list (status: open → done; completed: none → {settings.today()})" in after
    assert paths == ["areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md"]


def test_update_rules(settings, data_dir):
    store = TaskStore(settings, data_dir)
    with pytest.raises(NeedsInput) as e:
        store.update(LICENSES, {"status": "open"})
    assert e.value.kind == "reopen"
    doc, _, _ = store.update(LICENSES, {"status": "open", "reopen": True, "log": "Need a fourth seat"})
    assert doc.fm["status"] == "open" and doc.fm["completed"] is None
    with pytest.raises(NeedsInput) as e:
        store.update(LICENSES, {"status": "waiting"})
    assert e.value.kind == "reason"
    doc, _, _ = store.update(LICENSES, {"status": "waiting", "reason": "Finance approval"})
    assert "Reason: Finance approval" in doc.body
    with pytest.raises(NeedsInput) as e:
        store.update(LICENSES, {"due": "none"})
    assert e.value.kind == "due"
    doc, paths, _ = store.update(LICENSES, {"due": "2026-11-09"})
    assert paths and doc.fm["due"] == "2026-11-09"
    doc, paths, _ = store.update(LICENSES, {"due": "2026-11-09"})
    assert paths == []  # no-op


def test_update_rename_and_move_keep_identity(settings, data_dir):
    store = TaskStore(settings, data_dir)
    doc, paths, _ = store.update(LICENSES, {"title": "Renew design software licenses", "rename_file": True,
                                            "area": "home"})
    assert doc.task_id == LICENSES
    assert store.rel(doc.path) == "areas/home/tasks/2026-10-20-renew-design-software-licenses.md"
    assert paths[0] == "areas/work/tasks/2026-10-20-renew-the-team-software-licenses.md"
    assert not (settings.root() / paths[0]).exists()
    assert store.resolve(LICENSES).path == doc.path


def test_update_keeps_hand_written_comments(settings, data_dir):
    store = TaskStore(settings, data_dir)
    validator.validate(store, apply=True)  # give the hand-made task its ID
    p = settings.root() / "areas/work/tasks/2026-11-05-book-venue-for-the-offsite.md"
    before = p.read_text()
    store.update("Book venue for the offsite", {"priority": "high", "log": "Two quotes in"})
    after = p.read_text()
    fm_before, fm_after = before.split("\n---\n")[0].split("\n"), after.split("\n---\n")[0].split("\n")
    changed = [(a, b) for a, b in zip(fm_before, fm_after) if a != b]
    assert changed == [("priority: normal", "priority: high")] and len(fm_before) == len(fm_after)
    assert "# quote @ contexts" in after and "  # - '@computer'" in after


def test_update_refuses_newer_schema(settings, data_dir):
    store = TaskStore(settings, data_dir)
    with pytest.raises(NeedsInput) as e:
        store.update("0b1c2d3e-4f50-4a1b-8c2d-3e4f5a6b7c8d", {"priority": "high"})
    assert e.value.kind == "unsupported"


def test_concurrent_edit_detected(settings, data_dir, monkeypatch):
    store = TaskStore(settings, data_dir)
    real = tf.render

    def racing_render(fm, body, **kw):
        out = real(fm, body, **kw)
        p = settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md"
        p.write_text(p.read_text() + "\nedited elsewhere\n")
        return out

    monkeypatch.setattr(tf, "render", racing_render)
    with pytest.raises(tf.ConcurrentEditError):
        store.update(NEWSLETTER, {"priority": "low"})


def test_find(settings, data_dir):
    store = TaskStore(settings, data_dir)
    assert [t.task_id for t in store.find(query="newsletter")] == [NEWSLETTER]
    assert store.find(query="licenses") == []  # closed by default
    assert [t.task_id for t in store.find(query="licenses", status="any")] == [LICENSES]
    assert {t.title for t in store.find(due_before="2026-11-15")} == {"Draft the spring newsletter"}
    with pytest.raises(NeedsInput) as e:
        store.resolve("spring newslettr draft")
    assert e.value.data["candidates"][0]["task_id"] == NEWSLETTER


def test_triple_dash_inside_values(settings, data_dir):
    store = TaskStore(settings, data_dir)
    doc = store.create(title="Q3 --- budget review", area="work", due="2026-11-30", research=False,
                       research_skip_reason="err --- detail")
    assert doc.task_id and doc.title == "Q3 --- budget review"
    assert [t.task_id for t in store.find(task_id=doc.task_id)] == [doc.task_id]
    p = settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md"
    text = p.read_text().replace("  last_error: null", "  last_error: parse --- error")
    assert "parse --- error" in text
    p.write_text(text)
    store.update(NEWSLETTER, {"priority": "low"})
    fm, _ = tf.split_text(p.read_text())
    assert fm["google_tasks"]["work"]["task_id"] == "FAKETASK1"
    assert fm["enrichment"]["last_error"] == "parse --- error"


def test_create_area_is_visible_when_areas_configured(settings, data_dir):
    import dataclasses
    s = dataclasses.replace(settings, areas=["work", "home"])
    store = TaskStore(s, data_dir)
    doc = store.create(title="Plan garden beds", area="garden", due="2026-12-01", create_area=True, research=False)
    assert [t.task_id for t in store.find(task_id=doc.task_id)] == [doc.task_id]
    assert store.update(doc.task_id, {"priority": "high"})[1]


def test_same_date_on_unquoted_file_is_noop(settings, data_dir):
    store = TaskStore(settings, data_dir)
    p = settings.root() / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md"
    p.write_text(p.read_text().replace("due: '2026-11-12'", "due: 2026-11-12"))
    assert store.update(NEWSLETTER, {"due": "2026-11-12"})[1] == []


def test_agenda_scheduled_due_overdue(settings, data_dir):
    store = TaskStore(settings, data_dir)
    a = store.create(title="Pay the electric bill", area="home", due="2026-11-09", research=False)
    b = store.create(title="Draft the grant summary", area="work", due="2026-11-20", scheduled="2026-11-09",
                     research=False)
    store.create(title="Call the landlord", area="home", due="2026-11-01", research=False)
    store.create(title="Plan next quarter", area="work", due="2026-12-15", research=False)
    items = store.agenda("2026-11-09", "2026-11-09", today="2026-11-09")
    got = {t.title: why for t, why in items}
    assert got["Pay the electric bill"] == "due 2026-11-09"
    assert got["Draft the grant summary"] == "scheduled 2026-11-09"
    assert got["Call the landlord"] == "overdue (was due 2026-11-01)"
    assert "Plan next quarter" not in got and "Renew the team software licenses" not in got  # closed
    assert [t.title for t, _ in items][0] == "Call the landlord"  # overdue first
    week = {t.title for t, _ in store.agenda("2026-11-09", "2026-11-15", include_overdue=False, today="2026-11-09")}
    assert week == {"Pay the electric bill", "Draft the grant summary", "Draft the spring newsletter"}
    assert {t.title for t, _ in store.agenda("2026-11-09", "2026-11-15", area="home", today="2026-11-09")} == \
        {"Pay the electric bill", "Call the landlord"}


def test_date_words():
    sun = "2026-11-08"
    p = lambda v: tf.parse_date_words(v, sun)  # noqa: E731
    assert p("Friday") == "2026-11-13" and p("fri") == "2026-11-13" and p("sunday") == sun
    assert p("next sunday") == "2026-11-15" and p("tomorrow") == "2026-11-09" and p("next week") == "2026-11-09"
    assert p("Nov 13") == "2026-11-13" and p("13 November") == "2026-11-13" and p("November 13th, 2026") == "2026-11-13"
    assert p("Jan 5") == "2027-01-05" and p("in 3 days") == "2026-11-11" and p("2026-12-01") == "2026-12-01"
    for bad in ("11/13", "someday", "Feb 30"):
        with pytest.raises(tf.TaskFormatError):
            p(bad)


def test_overdue_follows_google_and_reschedule_by_words(settings, data_dir):
    store = TaskStore(settings, data_dir)
    t = store.create(title="Fix the gate latch", area="home", due="2026-10-01", research=False)
    today = settings.today()
    assert any(d.task_id == t.task_id and w.startswith("overdue") for d, w in store.agenda(today, today))
    store.update(t.task_id, {"scheduled": "tomorrow", "log": "Rescheduled"})
    assert not any(d.task_id == t.task_id and w.startswith("overdue") for d, w in store.agenda(today, today))
    tomorrow = tf.parse_date_words("tomorrow", today)
    why = dict((d.task_id, w) for d, w in store.agenda(tomorrow, tomorrow))[t.task_id]
    assert why == f"scheduled {tomorrow} (deadline 2026-10-01 passed)"
    doc, _, _ = store.update(t.task_id, {"due": "Nov 30"})
    assert doc.fm["due"].endswith("-11-30")


def test_period_ranges(settings, data_dir):
    store = TaskStore(settings, data_dir)
    sunday, wednesday = "2026-11-08", "2026-11-11"
    assert store.period_range("today", sunday) == (sunday, sunday)
    assert store.period_range("this_week", sunday) == (sunday, "2026-11-15")  # weekend: the coming week
    assert store.period_range("this_week", wednesday) == (wednesday, "2026-11-15")
    assert store.period_range("next_week", wednesday) == ("2026-11-16", "2026-11-22")
    assert store.period_range("monday", sunday) == ("2026-11-09", "2026-11-09")
    assert store.period_range("wednesday", wednesday) == (wednesday, wednesday)
    assert store.period_range("tomorrow", sunday) == ("2026-11-09", "2026-11-09")


# ---------------------------------------------------------------- validator

def test_validator_dry_run_and_apply(settings, data_dir):
    store = TaskStore(settings, data_dir)
    report = validator.validate(store)
    assert report["needs_identity"] == ["areas/work/tasks/2026-11-05-book-venue-for-the-offsite.md"]
    assert report["unsupported"][0]["path"].endswith("future-format-task.md")
    venue = settings.root() / "areas/work/tasks/2026-11-05-book-venue-for-the-offsite.md"
    before = venue.read_text()
    report = validator.validate(store, apply=True)
    assert len(report["fixed_identity"]) == 1 and report["changed_paths"] == [store.rel(venue)]
    assert "# quote @ contexts" in venue.read_text()  # comments survive
    assert len(before.split("\n")) == len(venue.read_text().split("\n"))
    assert validator.validate(store)["needs_identity"] == []


def test_validator_reports_duplicate_ids(settings, data_dir):
    root = settings.root()
    src = root / "areas/work/tasks/2026-11-01-draft-the-spring-newsletter.md"
    (root / "areas/home/tasks/copy.md").write_bytes(src.read_bytes())
    report = validator.validate(TaskStore(settings, data_dir))
    assert NEWSLETTER in report["duplicate_task_ids"]
    assert report["area_mismatch"]  # the copy says area work but sits in home
