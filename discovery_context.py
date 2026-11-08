"""Lossless canonical context snapshots. No credentials or implicit profile reads."""
from __future__ import annotations
import hashlib
import json
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
            # Preserve complete raw document, including completed tasks and managed dossiers.
            body = self.store.put_resource(run_id, name, doc.raw.decode('utf-8'))
            resources[name] = body
            inventory.append({'path': rel, 'filename': doc.path.name, 'title': doc.title, 'task_id': str(doc.fm.get('task_id') or ''), 'status': str(doc.fm.get('status') or ''), 'body': body})
        resources['task_inventory'] = self.store.put_resource(run_id, 'task_inventory', {'tasks': inventory, 'errors': scan.errors, 'untagged': [task_store.rel(p) for p in scan.untagged], 'all_statuses': True, 'complete': not scan.errors})
        installed = []
        if self.skills_root:
            for path in sorted(self.skills_root.rglob('SKILL.md')):
                real = path.resolve()
                if not real.is_relative_to(self.skills_root) or not real.is_file():
                    raise UserError('installed skill escapes approved root')
                rel = path.parent.relative_to(self.skills_root).as_posix()
                name = 'installed-skill-' + hashlib.sha256(rel.encode()).hexdigest()[:24]
                info = self.store.put_resource(run_id, name, real.read_text(encoding='utf-8'))
                installed.append({'name': rel, 'resource': info})
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
