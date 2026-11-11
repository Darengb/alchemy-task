"""The always-on plugin context stays within its limit (Hermes drops an oversized section entirely), offers
tasks, and the plugin skills carry the area-first setup and the task-offer rules."""
from __future__ import annotations

from pathlib import Path

import alchemy_task as at
from alchemy_task.core.config import Settings

ROOT = Path(at.__file__).parent


def _section(configured: bool, monkeypatch) -> str:
    monkeypatch.setattr(Settings, 'load', classmethod(lambda cls, *_a, **_k: cls()))
    monkeypatch.setattr(Settings, 'configured', property(lambda self: configured), raising=False)
    return at._prompt_section()


def test_prompt_sections_fit_and_offer_tasks(monkeypatch):
    on = _section(True, monkeypatch)
    off = _section(False, monkeypatch)
    assert len(on) <= at.PROMPT_SECTION_MAX and len(off) <= at.PROMPT_SECTION_MAX
    assert 'ask once if they want a task' in on and 'alchemy-task:tasks' in on


def test_tasks_skill_has_two_step_offer_rules():
    text = (ROOT / 'skills/tasks/SKILL.md').read_text()
    assert '## Suggesting tasks' in text
    assert 'Do you want to create a task for this?' in text
    assert 'not in scheduled' in text and 'do not ask again' in text
    assert text.index('## Suggesting tasks') < text.index('## Creating')


def test_discovery_skill_starts_from_areas():
    text = (ROOT / 'skills/discovery/SKILL.md').read_text()
    assert "**Start from the user's areas.**" in text
    assert text.index('Start from the user') < text.index('When sources are missing')
    assert 'always pass `areas`' in text and 'alchemy-task:setup' in text
    assert 'only the default `general`' in text and 'still ask' in text
