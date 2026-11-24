"""Stat-refreshed index of the exact identities each task file carries.

Discovery matching asks one question of every task file: could it carry one of
this unit's exact source identities? Answering it by fully parsing every file
for every match starved the dashboard. The index keeps, per task file, the
identities the exact-match rules extract, its task_id, open/closed state and
content revision. An entry is recomputed only when the file's size or mtime_ns
changes. The index is kept in memory per process and persisted in the plugin
data dir (never the task workspace), so a restart reuses it.

Slack URLs count as identities only through a run's approved host to workspace
mapping. Entries are computed once with placeholder workspaces and the real
mapping is applied at lookup time, so one entry serves every run.

Stdlib plus core modules only: discovery must load without the research module.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from . import taskfile as tf
from .discovery_identity import UserError, canonical_source_id, extract_identities

INDEX_VERSION = 1
_MARKER = re.compile(r'<!-- discovery-dossier:(start|end) ([A-Za-z0-9._-]+) -->')
_PLACEHOLDER = 'atidxhost'  # placeholder Slack workspace: atidxhost<n>, n indexes the entry's hosts
_lock = threading.Lock()
_memory: dict[str, dict[str, Any]] = {}


# ------------------------------------------------------------ exact identity rules

def validate_dossiers(body: str) -> None:
    """Refuse malformed or duplicated managed dossier markers."""
    opened = None
    seen = set()
    for marker in _MARKER.finditer(body):
        kind, identity = marker.groups()
        if kind == 'start':
            if opened or identity in seen: raise UserError('malformed or duplicated existing dossier markers')
            opened = identity
            seen.add(identity)
        else:
            if opened != identity: raise UserError('malformed existing dossier end marker')
            opened = None
    if opened or body.count('<!-- discovery-dossier:') != len(list(re.finditer(r'<!-- discovery-dossier:(?:start|end) [A-Za-z0-9._-]+ -->', body))):
        raise UserError('malformed existing dossier markers')


def exact_values(fm: dict, body: str, *, slack_workspaces=None) -> set[str]:
    """Identities in one task that may grant exact write authority."""
    # Related-only identities in a managed dossier never grant write authority.
    values = set()
    metadata = {k: v for k, v in fm.items() if k not in {'related_source_ids', 'discovery_related_source_ids'}}
    try:
        validate_dossiers(body)
    except UserError:
        # One task whose text merely mentions a marker (for example in a code span) must not block
        # matching for every unit. Its dossier blocks grant no exact identity; plain metadata and
        # body identities still count, and writing into it is still refused at the write check.
        body = re.sub(r'<!-- discovery-dossier:[^>]*-->', '', body)
        values.update(extract_identities(metadata, slack_workspaces=slack_workspaces))
        values.update(extract_identities(body, slack_workspaces=slack_workspaces))
        return values
    for match in re.finditer(r'<!-- discovery-dossier:start ([A-Za-z0-9._-]+) -->(.*?)<!-- discovery-dossier:end \1 -->', body, re.S):
        values.add('dossier:' + match[1])
        decisive = re.search(r'### Decisive Source Identities\n(.*?)(?=\n### |$)', match[2], re.S)
        if decisive:
            values.update(extract_identities(decisive[1], slack_workspaces=slack_workspaces))
    body = re.sub(r'<!-- discovery-dossier:start .*?<!-- discovery-dossier:end .*?-->', '', body, flags=re.S)
    values.update(extract_identities(metadata, slack_workspaces=slack_workspaces))
    values.update(extract_identities(body, slack_workspaces=slack_workspaces))
    return values


class _HostProbe(dict):
    """Stands in for any Slack host mapping and records which hosts were asked for."""

    def __init__(self):
        super().__init__()
        self.hosts: list[str] = []

    def __bool__(self):
        return True

    def __contains__(self, host):
        return isinstance(host, str)

    def __getitem__(self, host):
        if host not in self.hosts: self.hosts.append(host)
        return _PLACEHOLDER + str(self.hosts.index(host))


def _raw_values(fm: dict, body: str) -> tuple[list[str], list[str], list[str]]:
    """(identities needing no mapping, placeholder Slack URL identities, hosts)."""
    plain = exact_values(fm, body)
    probe = _HostProbe()
    probed = exact_values(fm, body, slack_workspaces=probe)
    return sorted(plain), sorted(probed - plain), probe.hosts


def apply_mapping(entry: dict, slack_workspaces: dict | None) -> set[str]:
    """The entry's exact identities under one run's Slack host mapping."""
    values = set(entry['values'])
    hosts = entry.get('hosts') or []
    for value in entry.get('mapped') or []:
        parts = value.split(':')
        host = hosts[int(parts[1][len(_PLACEHOLDER):])]
        if host not in (slack_workspaces or {}): continue
        with contextlib.suppress(UserError):
            values.add(canonical_source_id(':'.join(['slack', slack_workspaces[host], *parts[2:]])))
    return values


def match_keys(wanted) -> set[str]:
    """Every identity that equals or covers (is the thread of) a wanted identity."""
    keys = set()
    for identity in wanted:
        keys.add(identity)
        parts = identity.split(':')
        if (parts[0], len(parts)) in {('slack', 5), ('gmail', 4), ('source', 6)}:
            keys.add(':'.join(parts[:-1]))
    return keys


# ------------------------------------------------------------ index

def _entry(tasks, path: Path, st: os.stat_result) -> dict[str, Any]:
    from .store import _cached_parse  # the scan's safe-load parse and its cache
    entry: dict[str, Any] = {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'rel': tasks.rel(path)}
    try:
        doc = _cached_parse(path)
    except tf.TaskFormatError as exc:
        entry['error'] = str(exc)
        return entry
    entry['revision'] = tf.content_hash(doc.raw)
    entry['tagged'] = tf.has_task_tag(doc.fm)
    if not entry['tagged']:
        return entry
    task_id = doc.fm.get(tf.TASK_ID_KEY)
    entry['task_id'] = task_id if isinstance(task_id, str) else None
    entry['closed'] = doc.is_closed
    entry['values'], entry['mapped'], entry['hosts'] = _raw_values(doc.fm, doc.body)
    return entry


class TaskIndex:
    def __init__(self, root: str, entries: dict[str, dict[str, Any]], order: list[str]):
        self.root, self.entries, self.order = root, entries, order

    @property
    def errors(self) -> list[dict[str, str]]:
        return [{'path': self.entries[p]['rel'], 'error': self.entries[p]['error']} for p in self.order if 'error' in self.entries[p]]

    def tasks(self):
        """(absolute path, entry) for every tagged task file, in scan order."""
        return [(p, self.entries[p]) for p in self.order if self.entries[p].get('tagged')]

    def candidates(self, wanted, slack_workspaces, nominated=()):
        """Tagged task files that could exactly match a wanted identity, plus nominated paths, in scan order."""
        keys = match_keys(wanted)
        nominated = set(nominated)
        out = []
        for path, entry in self.tasks():
            if entry['rel'] in nominated or (not entry['closed'] and keys & apply_mapping(entry, slack_workspaces)):
                out.append((path, entry))
        return out

    def signature(self, wanted, slack_workspaces, nominated=()):
        """Files that could match exactly (open candidates and exact nominations) with their revisions.

        Equal signatures mean matching would find the same exact destinations, so a later
        check compares signatures instead of rereading every task."""
        found = {e['rel']: e['revision'] for _, e in self.candidates(wanted, slack_workspaces, nominated)}
        return sorted([rel, found.get(rel)] for rel in {*found, *nominated})


def _index_path(data_dir: Path, root: str) -> Path:
    return Path(data_dir) / 'task-index' / (hashlib.sha256(root.encode()).hexdigest()[:16] + '.json')


def _load(path: Path, root: str) -> dict[str, dict[str, Any]]:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(saved, dict) or saved.get('version') != INDEX_VERSION or saved.get('root') != root:
        return {}
    entries = saved.get('entries')
    return entries if isinstance(entries, dict) else {}


def _save(path: Path, root: str, entries: dict[str, dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
        tmp.write_text(json.dumps({'version': INDEX_VERSION, 'root': root, 'entries': entries}, separators=(',', ':')))
        os.replace(tmp, path)
    except OSError:
        pass  # the index is a cache; matching stays correct without the saved copy


def refresh(tasks, data_dir: Path) -> TaskIndex:
    """Bring the index up to date by stat: reindex changed or new files, drop removed ones."""
    root = str(tasks.root)
    path = _index_path(data_dir, root)
    with _lock:
        entries = _memory.get(root)
        if entries is None:
            entries = _load(path, root)
        fresh, order, changed = {}, [], False
        for file in tasks.task_files():
            key = str(file)
            try:
                st = file.stat()
            except OSError:
                continue
            old = entries.get(key)
            if old and old.get('size') == st.st_size and old.get('mtime_ns') == st.st_mtime_ns:
                fresh[key] = old
            else:
                fresh[key] = _entry(tasks, file, st)
                changed = True
            order.append(key)
        if changed or len(fresh) != len(entries):
            _save(path, root, fresh)
        _memory[root] = fresh
        return TaskIndex(root, fresh, order)
