"""Research fills the task's blank sections (summary, Notes, Plan, Subtasks) and never overwrites user content."""
from __future__ import annotations

import json

from alchemy_task import research_agent as ra
from alchemy_task import runtime
from alchemy_task.core import research as rs
from alchemy_task.core import taskfile as tf
from alchemy_task.core.store import TaskStore

from test_research_agent import PAYLOAD, ctx  # noqa: F401 - shared fixture

FILL = {"summary": "Buy twelve chairs for the cafe before the reopening.",
        "notes": "The cafe reopens in December. The old chairs were rented and go back next month.",
        "plan": ["Measure the floor", "Pick a supplier", "Order the chairs", "Confirm delivery"],
        "subtasks": ["Measure the floor", "Get three quotes", "Place the order"]}


def make(settings, data_dir, **kw):
    kw.setdefault("title", "Order cafe chairs")
    return TaskStore(settings, data_dir).create(area="work", due="2026-12-01", **kw)


def run(ctx, doc, fill=FILL, edit=None, again=False):
    rt = runtime.Runtime()
    out = (ra.request_again if again else ra.launch)(rt, doc.task_id)
    req = ctx.subagent_lifecycle.launched[-1]
    if edit:
        edit(doc)
    payload = {"run_id": out["run_id"], **PAYLOAD}
    if fill is not None:
        payload["fill"] = fill
    res = json.loads(ra.t_submit(payload, task_id=req.correlation_id and f"sa-{ctx.subagent_lifecycle.n}"))
    assert res["ok"], res
    return tf.parse_file(doc.path), req


def section(body, heading):
    lines = body.split("\n")
    b = tf._section_bounds(lines, heading)
    return None if b is None else "\n".join(lines[b[0] + 1:b[1]]).strip()


def mark(settings):
    return f"*(from research, {rs.day_label(settings.today())})*"


def log_lines(body):
    return [ln for ln in (section(body, "Log") or "").split("\n") if ln.startswith("- ")]


def test_blank_task_gets_all_four_with_markers_and_log(ctx, settings, data_dir):
    doc = make(settings, data_dir)
    final, req = run(ctx, doc)
    # the worker is told what is blank, and to research first
    assert "fill" in req.goal and "notes" in req.context.lower()
    assert final.fm["summary"] == FILL["summary"]
    notes, plan, subs = section(final.body, "Notes"), section(final.body, "Plan"), section(final.body, "Subtasks")
    assert notes.startswith("The cafe reopens") and notes.endswith(mark(settings))
    assert "1. Measure the floor" in plan and plan.endswith(mark(settings))
    assert "- [ ] Get three quotes" in subs and subs.endswith(mark(settings))
    # standard order, before the Log and the dossier
    order = [final.body.index(h) for h in ("## Notes", "## Plan", "## Subtasks", "## Log", rs.START)]
    assert order == sorted(order)
    fill_log = [ln for ln in log_lines(final.body) if "filled" in ln.lower()]
    assert fill_log and all(w in fill_log[0].lower() for w in ("summary", "notes", "plan", "subtasks"))
    fp = final.fm["enrichment"]["fill"]
    assert set(fp) == {"summary", "notes", "plan", "subtasks"} and all(v.startswith("sha256:") for v in fp.values())


def test_user_notes_kept_only_plan_and_subtasks_filled(ctx, settings, data_dir):
    doc = make(settings, data_dir, notes="My own notes about the chairs.", summary="Chairs for the cafe.")
    final, req = run(ctx, doc)
    assert section(final.body, "Notes") == "My own notes about the chairs."
    assert final.fm["summary"] == "Chairs for the cafe."
    assert mark(settings) in section(final.body, "Plan") and mark(settings) in section(final.body, "Subtasks")
    assert "summary" not in final.fm["enrichment"]["fill"] and "notes" not in final.fm["enrichment"]["fill"]


def test_user_edits_between_launch_and_submit_are_respected(ctx, settings, data_dir):
    doc = make(settings, data_dir)

    def edit(d):  # the user types a plan into the file while research runs
        cur = tf.parse_file(d.path)
        d.path.write_text(tf.render(cur.fm, tf.append_to_section(cur.body, "Plan", "My plan: call the supplier."),
                                    seq_offset=cur.seq_offset, keep_blank=cur.blank_keys))

    final, _ = run(ctx, doc, edit=edit)
    plan = section(final.body, "Plan")
    assert "My plan: call the supplier." in plan and mark(settings) not in plan
    assert mark(settings) in section(final.body, "Notes")


def test_re_research_refreshes_unedited_and_keeps_edited(ctx, settings, data_dir):
    doc = make(settings, data_dir)
    first, _ = run(ctx, doc)
    # the user edits the plan research wrote; the notes stay as research wrote them
    text = doc.path.read_text().replace("1. Measure the floor", "1. Measure the floor twice")
    doc.path.write_text(text)
    second_fill = {"notes": "Updated context from the second run.", "plan": ["A", "B", "C"],
                   "subtasks": ["X", "Y"], "summary": "New summary"}
    final, req = run(ctx, doc, fill=second_fill, again=True)
    assert "Updated context from the second run." in section(final.body, "Notes")
    assert "The cafe reopens" not in section(final.body, "Notes")
    assert "Measure the floor twice" in section(final.body, "Plan") and "1. A" not in section(final.body, "Plan")
    assert "- [ ] X" in section(final.body, "Subtasks")
    assert final.fm["summary"] == "New summary"  # research wrote it and nobody changed it
    assert any("refreshed" in ln.lower() for ln in log_lines(final.body))
    assert section(final.body, "Notes").count(mark(settings)) == 1


def test_user_written_summary_never_refreshed(ctx, settings, data_dir):
    doc = make(settings, data_dir)
    run(ctx, doc)
    TaskStore(settings, data_dir).update(doc.task_id, {"summary": "Mine now."})
    final, _ = run(ctx, doc, fill={**FILL, "summary": "Research again"}, again=True)
    assert final.fm["summary"] == "Mine now."


def test_simple_task_skips_subtasks_with_reason(ctx, settings, data_dir):
    doc = make(settings, data_dir, title="Call the plumber")
    fill = {"notes": "Leak under the sink.", "plan": ["Find the number", "Call", "Book a slot"],
            "subtasks_skipped_reason": "one phone call in one sitting"}
    final, _ = run(ctx, doc, fill=fill)
    assert section(final.body, "Subtasks") is None
    assert any("one phone call in one sitting" in ln for ln in log_lines(final.body))


def test_malformed_fill_does_not_break_the_dossier(ctx, settings, data_dir):
    for bad in ("just a string", {"plan": "not a list", "subtasks": 7, "notes": ["x"]}, {"plan": ["only one"]}):
        doc = make(settings, data_dir, title=f"Task {len(str(bad))}")
        final, _ = run(ctx, doc, fill=bad)
        assert rs.START in final.body and final.fm["enrichment"]["status"] == "complete"
        assert mark(settings) not in final.body
        assert any("fill" in ln.lower() and ("dropped" in ln.lower() or "ignored" in ln.lower())
                   for ln in log_lines(final.body)), final.body


def test_no_fill_keeps_old_behaviour(ctx, settings, data_dir):
    doc = make(settings, data_dir)
    final, _ = run(ctx, doc, fill=None)
    assert rs.START in final.body and mark(settings) not in final.body


def test_discovery_created_task_gets_same_fill(ctx, settings, data_dir):
    """Discovery creates tasks with research already complete and its own managed blocks; research it again
    goes through the same submit path and fills the blank sections without touching discovery's blocks."""
    area = settings.area_dir("work")
    area.mkdir(parents=True, exist_ok=True)
    tid = tf.new_task_id()
    fm = {"task_id": tid, "schema_version": tf.SCHEMA_VERSION, "title": "Book the venue", "status": "open",
          "area": "work", "due": "2026-12-01", "scheduled": "2026-12-01", "created": settings.today(),
          "completed": None, "priority": "normal", "tags": ["task"], "reminders": [],
          "enrichment": {"status": "complete", "attempts": 0, "research_origin": "discovery",
                         "accepted_research_revision": "sha256:abc"}, "dossier_ids": ["dos-1"]}
    body = ("## Notes\n\n<!-- discovery-context:start dos-1 r1 -->\n### Discovery context\n\n- From a thread.\n"
            "<!-- discovery-context:end dos-1 r1 -->\n\n## Log\n\n- 2026-11-01: Discovery context added (r1).\n\n"
            "<!-- discovery-dossier:start dos-1 -->\n## Discovery dossier\n\nEvidence.\n"
            "<!-- discovery-dossier:end dos-1 -->\n")
    path = area / f"{settings.today()}-book-the-venue-{tid}.md"
    path.write_text(tf.render(fm, body))
    doc = TaskStore(settings, data_dir).resolve(tid)
    final, _ = run(ctx, doc, again=True)
    notes = section(final.body, "Notes")
    assert notes.startswith("The cafe reopens") and "<!-- discovery-context:start dos-1 r1 -->" in final.body
    assert final.body.index("The cafe reopens") < final.body.index("<!-- discovery-context:start")
    assert mark(settings) in section(final.body, "Plan") and mark(settings) in section(final.body, "Subtasks")
    assert final.body.index("## Subtasks") < final.body.index("## Log")
    assert "<!-- discovery-dossier:start dos-1 -->" in final.body and "Evidence." in final.body
    assert final.fm["summary"] == FILL["summary"]


def test_blank_sections_helper():
    assert rs.blank_sections({"summary": None}, "## Notes\n\n## Log\n") == ["summary", "notes", "plan", "subtasks"]
    body = "## Notes\n\nHi.\n\n## Plan\n\n1. a\n\n## Subtasks\n\n- [ ] x\n"
    assert rs.blank_sections({"summary": "s"}, body) == []
    assert rs.blank_sections({"summary": "s"}, "## Notes\n\n## Subtasks\n\nno checklist here\n") == [
        "notes", "plan", "subtasks"]



def test_fill_never_reflows_user_text(ctx, settings, data_dir):
    doc = make(settings, data_dir, notes="Line one.\n\n\n\nLine two after gaps.")
    final, _ = run(ctx, doc)
    assert "Line one.\n\n\n\nLine two after gaps." in final.body
    assert "\n\n\n" not in final.body.split("## Plan")[1]
