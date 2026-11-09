"""Synthetic world for end-to-end runs: isolated HOME/HERMES_HOME, a Git task repo and a local bare remote.

Outcome readers here use only plain files and the git CLI; they never import plugin code.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

PLUGIN_ID = 'alchemy-task'


def git(cwd, *args, check=True):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=check)


def isolate_env(root: Path, monkeypatch):
    """Point HOME, git global config and HERMES_HOME at the test's scratch directory."""
    home = root / 'home'
    home.mkdir(parents=True, exist_ok=True)
    gitconfig = home / '.gitconfig'
    gitconfig.write_text('[user]\n\tname = E2E\n\temail = e2e@example.test\n[init]\n\tdefaultBranch = main\n')
    hermes_home = root / 'hermes-home'
    hermes_home.mkdir(exist_ok=True)
    for key, value in {'HOME': home, 'GIT_CONFIG_GLOBAL': gitconfig, 'GIT_CONFIG_NOSYSTEM': '1',
                       'HERMES_HOME': hermes_home, 'GIT_TERMINAL_PROMPT': '0'}.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.delenv('ALCHEMY_TASK_GIT_TOKEN', raising=False)
    return hermes_home


def write_host_config(hermes_home: Path, settings: dict):
    """The profile config.yaml the real host reads plugin settings from (JSON is valid YAML)."""
    (hermes_home / 'config.yaml').write_text(json.dumps({'plugins': {
        'enabled': [PLUGIN_ID], 'isolation': 'in_process',
        'entries': {PLUGIN_ID: {'settings': settings}}}}))


TASK_TEMPLATE = """---
title: "{title}"
task_id: {task_id}
schema_version: 1
status: {status}
priority: normal
area: work
due: 2026-12-01
created: "2026-10-01"
tags:
  - task
---

## Notes

{notes}

## Log

- 2026-10-01: Created by hand.
"""


class World:
    def __init__(self, root: Path, hermes_home: Path):
        self.root = Path(root)
        self.hermes_home = hermes_home
        self.root.mkdir(parents=True, exist_ok=True)
        self.remote = self.root / 'remote.git'
        self.ws = self.root / 'workspace'
        git(self.root, 'init', '--bare', '-q', str(self.remote))
        self.ws.mkdir()
        git(self.ws, 'init', '-q', '-b', 'main')
        self.tasks_dir.mkdir(parents=True)
        (self.tasks_dir / '.keep').write_text('')
        git(self.ws, 'add', '-A')
        git(self.ws, 'commit', '-q', '-m', 'init')
        git(self.ws, 'remote', 'add', 'origin', str(self.remote))
        git(self.ws, 'push', '-q', 'origin', 'main')

    @property
    def tasks_dir(self):
        return self.ws / 'areas' / 'work' / 'tasks'

    def add_task(self, slug, title, *, notes, status='open', task_id=None):
        task_id = task_id or str(uuid.uuid4())
        path = self.tasks_dir / f'2026-10-01-{slug}.md'
        path.write_text(TASK_TEMPLATE.format(title=title, task_id=task_id, status=status, notes=notes))
        git(self.ws, 'add', '-A')
        git(self.ws, 'commit', '-q', '-m', 'add ' + slug)
        git(self.ws, 'push', '-q', 'origin', 'main')
        return task_id, path

    # ---------------------------------------------------------------- outcomes
    def task_files(self):
        return sorted(self.tasks_dir.glob('*.md'))

    def remote_files(self, branch='main'):
        out = git(self.root, '--git-dir', str(self.remote), 'ls-tree', '-r', '--name-only', branch).stdout.split()
        return sorted(x for x in out if x.endswith('.md'))

    def remote_bytes(self, rel, branch='main'):
        return subprocess.run(['git', '--git-dir', str(self.remote), 'show', f'{branch}:{rel}'],
                              capture_output=True, check=True).stdout

    def remote_head(self, branch='main'):
        return git(self.root, '--git-dir', str(self.remote), 'rev-parse', branch).stdout.strip()

    def local_head(self):
        return git(self.ws, 'rev-parse', 'HEAD').stdout.strip()

    def commit_count(self):
        return int(git(self.ws, 'rev-list', '--count', 'HEAD').stdout.strip())

    def dirty(self):
        return git(self.ws, 'status', '--porcelain').stdout.strip()

    def rel(self, path):
        return str(Path(path).relative_to(self.ws))
