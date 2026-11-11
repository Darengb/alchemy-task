"""Outcome readers that do NOT use plugin code: plain files, YAML, git CLI, digest lines."""
from __future__ import annotations

import re

import yaml


def frontmatter(text: str) -> dict:
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    assert m, 'task file lacks frontmatter'
    return yaml.safe_load(m.group(1)) or {}


def dossier_ids(text: str) -> list:
    return re.findall(r'<!-- discovery-dossier:start ([A-Za-z0-9._-]+) -->', text)


def numbered_lines(text: str) -> dict:
    """{number: title} for every numbered item as the user sees it in the delivered digest."""
    shown = {}
    for line in text.splitlines():
        m = re.match(r'^### [A-Za-z]*(\d+)\. (.+?)(?: \[|$)', line)
        if m:
            shown[int(m.group(1))] = m.group(2).strip()
    return shown


def snapshot(world):
    """Every user-visible artifact of the task store, local and remote."""
    files = {world.rel(p): p.read_bytes() for p in world.task_files()}
    remote = {rel: world.remote_bytes(rel) for rel in world.remote_files()}
    return {'local': files, 'remote': remote, 'commits': world.commit_count(), 'head': world.local_head(),
            'remote_head': world.remote_head(), 'dirty': world.dirty()}
