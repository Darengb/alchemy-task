"""Lossless canonical context snapshots. No credentials or implicit profile reads."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from .core.discovery_identity import UserError


def resolve_identity(metadata: dict, approved_context: list[dict]) -> dict:
    """Resolve only explicit, account-scoped approved identity evidence.

    Input comes from setup's approved metadata/memory/docs, never credentials.
    A ready result still asks the future configuration integration to persist it.
    """
    account = metadata.get('account_key')
    if not isinstance(account, str) or not account:
        return {'status': 'needs_input', 'missing': ['account_key']}
    matches = [x for x in approved_context if x.get('account_key') == account and x.get('confirmed') is True]
    if metadata.get('confirmed') is True:
        matches.append(metadata)
    identities = {(x.get('name'), tuple(x.get('aliases', [])), x.get('user_id')) for x in matches if x.get('name')}
    if len(identities) != 1:
        return {'status': 'needs_input', 'missing': ['name', 'confirmed_alias_mapping'], 'ambiguous': len(identities) > 1}
    name, aliases, uid = identities.pop()
    if not isinstance(name, str) or not name.strip() or any(not isinstance(a, str) or not a for a in aliases):
        return {'status': 'needs_input', 'missing': ['name', 'confirmed_alias_mapping']}
    if metadata.get('requires_user_id') and not uid:
        return {'status': 'needs_input', 'missing': ['user_id']}
    return {'status': 'ready', 'identity': {'account_key': account, 'name': name, 'aliases': list(aliases), 'user_id': uid}, 'persist_confirmation': True}


class DiscoveryContext:
    def __init__(self, rt: Any, store: Any, *, installed_skills_root: Path | None = None):
        self.rt, self.store = rt, store
        # Supplied by installing-profile integration, not discovered via another profile.
        self.skills_root = Path(installed_skills_root).resolve() if installed_skills_root else None

    def freeze(self, run_id: str, *, source_config: dict, rubric: str, skills: tuple[str, ...] | list[str] = ()) -> dict:
        existing = self.store.get_run(run_id)['resources']
        if 'context-bootstrap' in existing:
            info = existing['context-bootstrap']
            return json.loads((self.store.run_dir(run_id) / 'resources' / info['sha256']).read_text())
        task_store = self.rt.store()
        scan = task_store.scan()
        resources = {}
        inventory = []
        for doc in sorted(scan.tasks, key=lambda d: task_store.rel(d.path)):
            real = doc.path.resolve()
            if not any(real.is_relative_to(folder.resolve()) for _, folder in task_store.task_dirs()):
                raise UserError('task inventory contains escaping path')
            rel = task_store.rel(doc.path)
            name = 'task-body-' + hashlib.sha256(rel.encode()).hexdigest()[:24]
            # Complete raw document (all statuses, managed dossiers) stays fetchable on demand;
            # the index below is compact and carries no bodies.
            body = self.store.put_resource(run_id, name, doc.raw.decode('utf-8'))
            inventory.append({'task_id': str(doc.fm.get('task_id') or ''), 'title': doc.title, 'status': str(doc.fm.get('status') or ''),
                              'area': str(doc.fm.get('area') or task_store.area_of(doc.path) or ''), 'due': str(doc.fm.get('due') or ''),
                              'summary': _one_line(doc.fm, doc.body), 'path': rel, 'body': name, 'revision': body['sha256']})
        resources['task_inventory'] = self.store.put_resource(run_id, 'task_inventory', {
            'tasks': inventory, 'errors': scan.errors, 'untagged': [task_store.rel(p) for p in scan.untagged], 'all_statuses': True,
            'complete': not scan.errors,
            'bodies': 'Compact index. Fetch a full task body only when it is plausibly relevant: discovery_research_fetch(resource=body, revision=revision).'})
        installed = []
        if self.skills_root:
            wanted = _candidate_words(self.store, run_id)
            for path in sorted(self.skills_root.rglob('SKILL.md')):
                real = path.resolve()
                if not real.is_relative_to(self.skills_root) or not real.is_file():
                    raise UserError('installed skill escapes approved root')
                rel = path.parent.relative_to(self.skills_root).as_posix()
                text = real.read_text(encoding='utf-8')
                skill_name, description = _skill_meta(text)
                # Only skills that match the run's candidates (plus the discovery and tasks skills) are frozen.
                if not _skill_relevant(rel, skill_name, description, wanted):
                    continue
                name = 'installed-skill-' + hashlib.sha256(rel.encode()).hexdigest()[:24]
                info = self.store.put_resource(run_id, name, text)
                installed.append({'name': rel, 'description': description[:200], 'resource': info})
        resources['skill-inventory'] = self.store.put_resource(run_id, 'skill-inventory', installed)
        for skill in skills:
            if not self.skills_root:
                raise UserError('installing-profile skill root not supplied')
            path = (self.skills_root / skill / 'SKILL.md').resolve()
            if not path.is_relative_to(self.skills_root) or not path.is_file():
                raise UserError('skill outside approved installed root or missing')
            name = 'skill-' + skill.replace('/', '-')
            resources[name] = self.store.put_resource(run_id, name, path.read_text(encoding='utf-8'))
        resources['source_config'] = self.store.put_resource(run_id, 'source_config', source_config)
        resources['context-rubric'] = self.store.put_resource(run_id, 'context-rubric', rubric)
        self.store.put_resource(run_id, 'context-bootstrap', resources)
        return resources


ALWAYS_SKILLS = {'alchemy-task:discovery', 'alchemy-task:tasks', 'alchemy-task-discovery', 'alchemy-task-tasks'}
# Words too common in skill names to signal relevance on their own.
GENERIC_WORDS = frozenset('''use when the and for with from into your this that operations operation production research workflow workflows
management development debugging analysis guide review reviews update updates daily weekly work assets asset creation skill
skills tasks task agent agents hermes discovery setup reconciliation drafting conventions page pages api cli ops media content
data code create edit build run running make read write file files tool tools safe safely local remote using used user users
plan plans plugin plugins operate manage managing project projects source sources item items notes note'''.split())


def _one_line(fm: dict, body: str) -> str:
    for value in (fm.get('summary'), fm.get('description')):
        if isinstance(value, str) and value.strip():
            return ' '.join(value.split())[:160]
    for line in (body or '').splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '<!--', '---', '```')):
            continue
        return ' '.join(line.lstrip('-*> ').split())[:160]
    return ''


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) >= 3 and w not in GENERIC_WORDS}


def _skill_meta(text: str) -> tuple[str, str]:
    head = text.split('\n---', 1)[0] if text.startswith('---') else ''
    name = re.search(r'(?m)^name:\s*["\']?([^"\'\n]*)', head)
    description = re.search(r'(?m)^description:\s*["\']?([^"\'\n]*)', head)
    return (name.group(1).strip() if name else ''), (description.group(1).strip() if description else '')


def _candidate_words(store, run_id: str) -> set[str]:
    """Words from every top-level candidate's title, summary and frozen primary text."""
    ledger = store.get_run(run_id)
    parts = []
    for candidate in ledger.get('candidates', []):
        if not candidate.get('parent_candidate_id'):
            parts += [str(candidate.get('title') or ''), str(candidate.get('summary') or '')]
    for name, info in ledger.get('resources', {}).items():
        if name.startswith('source-body-'):
            try:
                parts.append((store.run_dir(run_id) / 'resources' / info['sha256']).read_text(encoding='utf-8'))
            except OSError:
                pass
    return _words(' '.join(parts))


def _skill_relevant(rel: str, name: str, description: str, wanted: set[str]) -> bool:
    keys = {rel.replace('/', ':'), rel.replace('/', '-'), name}
    if keys & ALWAYS_SKILLS or rel.split('/')[-1] in {'discovery', 'tasks'} and 'alchemy-task' in rel:
        return True
    # Name words must match: one when the name has one distinctive word, otherwise at least two.
    named = _words(rel.replace('/', ' ') + ' ' + name)
    if named and len(named & wanted) >= min(2, len(named)):
        return True
    # Description alone needs several distinct matching words.
    return len(_words(description) & wanted) >= 3
