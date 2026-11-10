"""Review fixes for the research fill: user Subtasks are never replaced, fill text cannot create headings or open
HTML comments or code fences, and the log only mentions sections that were fill targets."""
from __future__ import annotations

from alchemy_task.core import research as rs

DAY = "2026-11-10"
FULL_FILL = {"summary": "S.", "notes": "N.", "plan": ["a", "b", "c"], "subtasks": ["x", "y"]}


def body_with_subtasks(sub: str) -> str:
    return f"## Notes\n\n## Plan\n\n## Subtasks\n\n{sub}\n\n## Log\n"


def test_subtasks_prose_bullets_and_numbers_are_kept():
    for sub in ("Wait for Bob before anything.", "- call Bob", "1. buy paint",
                "Wait for Bob before anything.\n- call Bob\n1. buy paint"):
        body = body_with_subtasks(sub)
        assert "subtasks" not in rs.fill_targets({}, body), sub
        new, _, _, report = rs.apply_fill({}, body, FULL_FILL, day=DAY)
        assert sub in new and "- [ ] x" not in new, sub
        assert "subtasks" not in report["filled"]


def test_subtasks_with_only_empty_checkboxes_are_blank():
    for sub in ("", "- [ ]", "- [ ]\n* [ ] \n+ [x]"):
        assert rs.fill_targets({}, body_with_subtasks(sub)).get("subtasks") == "blank", sub
    assert "subtasks" not in rs.fill_targets({}, body_with_subtasks("- [ ] call Bob"))


def test_fill_line_never_makes_a_heading_or_list_lead():
    for raw in ("# ## Log", "## Log", "- # Log", "1. ## Log", "#  - [ ] ## Log", "- - # # Log"):
        out = rs._fill_line(raw)
        assert out == "Log", (raw, out)
    fill, _ = rs.normalize_fill({"notes": "# ## Log\n\nfine"})
    new, _, _, _ = rs.apply_fill({}, "## Notes\n\n## Log\n", fill, day=DAY)
    assert new.count("## Log") == 1


def test_fill_line_escapes_comments_and_drops_code_fences():
    for raw in ("<!-- hidden", "a <!-- b", "x --> y", "<!-- task-research-dossier:start -->"):
        out = rs._fill_line(raw)
        assert "<!--" not in out and "-->" not in out, (raw, out)
    assert rs._fill_line("a <!-- b") == "a &lt;!-- b"
    assert rs._fill_line("x --> y") == "x --&gt; y"
    for raw in ("```", "```python", "~~~", "- ```js"):
        out = rs._fill_line(raw)
        assert not out.startswith("```") and not out.startswith("~~~"), (raw, out)
    fill, _ = rs.normalize_fill({"notes": "```\n\nreal text"})
    assert "```" not in fill.get("notes", "")


def test_log_only_mentions_targets():
    full = body_with_subtasks("- [ ] call Bob").replace("## Plan\n", "## Plan\n\n1. mine\n2. mine\n3. mine\n")
    fill, problems = rs.normalize_fill({"notes": "N.", "plan": ["only one"], "subtasks_skipped_reason": "too small"})
    assert problems
    _, _, _, report = rs.apply_fill({}, full, fill, day=DAY)
    line = rs.fill_log(report, problems)
    assert "Subtasks skipped" not in line
    assert "plan" not in line.lower()
    assert "Research filled notes" in line
    # when the sections are targets, the reason and problem still show
    blank = body_with_subtasks("")
    _, _, _, report = rs.apply_fill({}, blank, fill, day=DAY)
    line = rs.fill_log(report, problems)
    assert "Subtasks skipped: too small" in line and "plan needs at least 3 steps" in line


def test_fill_line_escapes_leading_html_block_starter():
    from alchemy_task.core import research as rs
    assert rs._fill_line('<pre> hidden text') == '&lt;pre> hidden text'
    assert rs._fill_line('- <script>x') == '&lt;script>x'
    fill, _ = rs.normalize_fill({'notes': '<pre>\nhidden', 'plan': ['<style> a', 'b', 'c']})
    assert not fill['notes'].startswith('<') and fill['plan'][0].startswith('&lt;')
