"""Post-join typed matching and recoverable whole-document discovery conversion.

Matching adapts the established helper's exact_task_matches nomination guard.
Semantic equivalence and useful delta remain parent judgments, never title scores.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from .core.discovery_state import atomic_json, read_json
from .core.discovery_dossiers import content_revision, render_discovery_dossier, upsert_managed_block
from .core.locks import task_lock
from .core import taskfile as tf
from .core.discovery_identity import UserError, canonical_source_id, extract_identities, source_identity_covers, is_message_refinement


class DiscoveryConversion:
    def __init__(self, rt, store):
        self.rt, self.store = rt, store

    def joined(self, run, wid):
        ledger = self.store.get_run(run)
        info = ledger['resources'].get('join-record')
        if not info:
            raise UserError('global join required before matching or mutation')
        join = json.loads((self.store.run_dir(run) / 'resources' / info['sha256']).read_text())
        c = self.store.get_candidate(run, wid)
        if not join.get('joined') or c.get('parent_candidate_id') not in join['accepted']:
            raise UserError('unit not part of accepted global join')
        research = self.store.research_for(run, wid)
        if not c.get('eligible_research'):
            raise UserError('excluded research cannot produce tasks')
        return c, research

    def _exact_values(self, doc):
        # Related-only identities in a managed dossier never grant write authority.
        body = doc.body
        values = set()
        for match in re.finditer(r'<!-- discovery-dossier:start ([A-Za-z0-9._-]+) -->(.*?)<!-- discovery-dossier:end \1 -->', body, re.S):
            values.add('dossier:' + match[1])
            decisive = re.search(r'### Decisive Source Identities\n(.*?)(?=\n### |$)', match[2], re.S)
            if decisive:
                values.update(extract_identities(decisive[1]))
        body = re.sub(r'<!-- discovery-dossier:start .*?<!-- discovery-dossier:end .*?-->', '', body, flags=re.S)
        metadata = {k: v for k, v in doc.fm.items() if k not in {'related_source_ids', 'discovery_related_source_ids'}}
        values.update(extract_identities(metadata))
        values.update(extract_identities(body))
        return values

    def match(self, run, wid):
        candidate, research = self.joined(run, wid)
        wanted = {canonical_source_id(x) for x in research['exact_source_ids']}
        wanted.add('dossier:dos-' + wid[2:])
        nominations = {x['path']: x['match_basis'] for x in research['existing_task_candidates']}
        tasks = self.rt.store()
        scan = tasks.scan()
        if scan.errors:
            raise UserError('canonical task inventory is incomplete; resolve parse failures before matching')
        exact, semantic = [], []
        for item in scan.tasks:
            doc = tf.parse_file(item.path)  # full current bytes, not cached summaries
            rel = tasks.rel(doc.path)
            values = self._exact_values(doc)
            overlap = sorted(r for r in wanted if any(s == r or (source_identity_covers(s, r) and (not candidate.get('parent_candidate_id') or not is_message_refinement(r) or nominations.get(rel) == 'exact')) for s in values))
            target = {**tasks.summary(doc), 'revision': tf.content_hash(doc.raw)}
            if overlap:
                target['matched_identities'] = overlap
                exact.append(target)
            elif rel in nominations:
                semantic.append(target)
        return {'run_id': run, 'unit_id': wid, 'kind': 'conflict' if len(exact) > 1 else 'exact' if exact else 'selection' if len(semantic) > 1 else 'semantic' if semantic else 'new', 'targets': exact or semantic, 'research': research}

    def _paths(self, run, wid):
        self.store.get_candidate(run, wid)  # validate identifiers before constructing paths
        folder = self.store.run_dir(run) / 'conversions'
        return folder / (wid + '.plan.json'), folder / (wid + '.receipt.json')

    def prepare(self, run, wid, *, choice, reason, target_task_id='', expected_revision='',
                useful_delta=False, user_approved=False, area='', title='', due='', undated=False):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise UserError('substantive parent decision reason required')
        if choice not in {'create', 'update', 'auto', 'noop'}:
            raise UserError('choice must be create, update, auto or noop')
        if choice in {'create', 'update'} and user_approved is not True:
            raise UserError('explicit user approval required')
        outcome = self.match(run, wid)
        candidate, research = self.joined(run, wid)
        if outcome['kind'] == 'conflict':
            raise UserError('multiple exact destinations conflict; no mutation')
        if choice in {'auto', 'noop'} and outcome['kind'] != 'exact':
            raise UserError('automatic action requires unique verified exact destination')
        if choice == 'auto' and useful_delta is not True:
            raise UserError('automatic enrichment requires parent verified useful delta')
        if choice == 'create' and outcome['kind'] == 'exact':
            raise UserError('exact task already exists; cannot create a duplicate')
        request = dict(choice=choice, reason=reason, target_task_id=target_task_id,
                       expected_revision=expected_revision, useful_delta=useful_delta,
                       user_approved=user_approved, area=area, title=title, due=due, undated=undated)
        plan_path, _ = self._paths(run, wid)
        with self.store._lock('conversion:' + run + ':' + wid):
            old = read_json(plan_path)
            if old:
                if old['request'] != request:
                    raise UserError('conversion binding is immutable; resume exact saved conversion')
                return old
            task_store = self.rt.store()
            if choice != 'create':
                targets = [t for t in outcome['targets'] if t['task_id'] == target_task_id]
                if not tf.valid_task_id(target_task_id) or len(targets) != 1:
                    raise UserError('choose exact nominated target_task_id, never a title')
                doc = tf.parse_file(task_store.resolve(target_task_id).path)
                if not expected_revision or tf.content_hash(doc.raw) != expected_revision:
                    raise tf.ConcurrentEditError('task changed since full read')
                if choice == 'noop':
                    return {'state': 'noop', 'task_id': target_task_id, 'revision': expected_revision, 'reason': reason}
                ok, why = tf.writable(doc.fm)
                if not ok:
                    raise UserError('task cannot be edited: ' + why)
                fm, body = doc.fm, doc.body
                path, tid, before = doc.path, doc.task_id, doc.raw
            else:
                area = task_store._pick_area(area, False)
                date = tf.parse_date_words(due, self.rt.settings.today(), 'due')
                if not date and not undated:
                    raise UserError('ask for due date or explicit undated approval')
                tid = tf.new_task_id()
                name = title or research['title']
                if not isinstance(name, str) or not name.strip() or len(name) > 200:
                    raise UserError('task title requires 1..200 characters')
                path = self.rt.settings.area_dir(area) / (self.rt.settings.today() + '-' + tf.slugify(name) + '-' + tid + '.md')
                fm = {'task_id': tid, 'schema_version': tf.SCHEMA_VERSION, 'title': name, 'status': 'open',
                      'area': area, 'due': date, 'scheduled': date, 'created': self.rt.settings.today(),
                      'completed': None, 'priority': 'normal', 'tags': ['task'], 'reminders': [],
                      'enrichment': {'status': 'complete', 'attempts': 0, 'research_origin': 'discovery',
                                     'accepted_research_revision': content_revision(research)}}
                body, before = '## Notes\n', None
            dossier_id = 'dos-' + wid[2:]
            revision, block = render_discovery_dossier(research, dossier_id=dossier_id, candidate_source_ids=candidate['source_ids'])
            ids = fm.get('dossier_ids') or []
            if isinstance(ids, str): ids = [ids]
            if not isinstance(ids, list): raise UserError('invalid task dossier_ids')
            fm['dossier_ids'] = list(dict.fromkeys([*ids, dossier_id]))
            # Append synthesis before existing managed dossiers, preserving every old section.
            additions = [x for x in research['new_information'] if x and x not in body]
            if additions:
                text = '\n\n### Discovery context\n\n' + '\n'.join('- ' + x for x in additions)
                text += '\n\n## Log\n\n- ' + self.rt.settings.today() + ': Discovery context added (' + revision + ').\n'
                pos = body.find('<!-- discovery-dossier:start ')
                body = body[:pos].rstrip() + text + '\n\n' + body[pos:] if pos >= 0 else body.rstrip() + text
            body, _ = upsert_managed_block(body, start_marker=f'<!-- discovery-dossier:start {dossier_id} -->',
                                            end_marker=f'<!-- discovery-dossier:end {dossier_id} -->', block=block)
            postimage = tf.render(fm, body, **({'seq_offset': doc.seq_offset, 'keep_blank': doc.blank_keys} if before else {}))
            plan = {'run_id': run, 'unit_id': wid, 'request': request, 'state': 'prepared',
                    'task_id': tid, 'path': task_store.rel(path), 'preimage_sha256': tf.content_hash(before) if before else None,
                    'postimage': postimage, 'postimage_sha256': tf.content_hash(postimage.encode()),
                    'dossier_id': dossier_id, 'research_revision': content_revision(research), 'dossier_revision': revision}
            atomic_json(plan_path, plan)  # UUID, path and FULL postimage persisted BEFORE any task write
            return plan

    def apply(self, run, wid):
        _, research = self.joined(run, wid)
        plan_path, receipt_path = self._paths(run, wid)
        with self.store._lock('conversion:' + run + ':' + wid):
            plan = read_json(plan_path)
            if not plan:
                raise UserError('prepare immutable approved conversion first')
            if content_revision(research) != plan['research_revision']:
                raise UserError('accepted research binding changed')
            old = read_json(receipt_path)
            path = (self.rt.store().root / plan['path']).resolve()
            if not any(path.is_relative_to(folder.resolve()) for _, folder in self.rt.store().task_dirs()):
                raise UserError('conversion task path escapes configured task directories')
            with task_lock(self.rt.data_dir, plan['task_id'], path):
                actual = path.read_bytes() if path.exists() else None
                if actual is not None and tf.content_hash(actual) == plan['postimage_sha256']:
                    pass  # exact complete postimage is the only lost-receipt recognition
                elif old:
                    raise tf.ConcurrentEditError('converted task changed; do not overwrite user edits')
                elif (tf.content_hash(actual) if actual is not None else None) == plan['preimage_sha256']:
                    current = self.match(run, wid)
                    if current['kind'] == 'conflict' or (plan['request']['choice'] == 'create' and current['kind'] == 'exact'):
                        raise UserError('exact destinations changed since preparation')
                    tf.atomic_write(path, plan['postimage'].encode(), expect=actual)
                else:
                    raise tf.ConcurrentEditError('task differs from both prepared preimage and whole postimage')
                verified = tf.parse_file(path)
                if verified.task_id != plan['task_id'] or tf.content_hash(verified.raw) != plan['postimage_sha256']:
                    raise UserError('task readback failed whole postimage/UUID verification')
            if old:
                return old
            receipt = {'run_id': run, 'unit_id': wid, 'task_id': plan['task_id'], 'path': plan['path'],
                       'local': {'state': 'verified', 'sha256': plan['postimage_sha256']},
                       'git': {'state': 'pending'},
                       'google': {'state': 'deferred', 'reason': 'Google integration is disabled for discovery'},
                       'phone': {'state': 'deferred', 'reason': 'Optional phone sync remains controlled by its existing explicit setup contract'},
                       'state': 'local_verified'}
            atomic_json(receipt_path, receipt)
            return receipt

    def deliver_git(self, run, wid):
        receipt = self.apply(run, wid)
        _, receipt_path = self._paths(run, wid)
        with self.store._lock('conversion:' + run + ':' + wid):
            receipt = read_json(receipt_path)
            if receipt['git']['state'] == 'verified':
                return receipt
            if self.rt.settings.git_transport == 'none':
                receipt['git'] = {'state': 'deferred', 'reason': 'Git delivery disabled by task settings'}
            else:
                delivery = self.rt.git()
                try:
                    raw = delivery.deliver([receipt['path']], 'task: promote accepted discovery dossier')
                    head = delivery.git('rev-parse', 'HEAD').stdout.strip()
                    branch = self.rt.settings.git_branch or delivery.git('branch', '--show-current').stdout.strip()
                    committed = delivery.git('show', head + ':' + receipt['path']).stdout.encode('utf-8')
                    remote_result = delivery.git('ls-remote', self.rt.settings.git_remote, 'refs/heads/' + branch)
                    lines = remote_result.stdout.splitlines()
                    remote = lines[0].split()[0] if len(lines) == 1 else ''
                    if tf.content_hash(committed) != receipt['local']['sha256']:
                        raise UserError('committed tree does not contain exact prepared task bytes')
                    if not remote or remote != head:
                        raise UserError('remote branch does not equal verified committed tree')
                    receipt['git'] = {'state': 'verified', 'commit': head, 'remote_commit': remote,
                                      'branch': branch, 'sha256': tf.content_hash(committed)}
                except Exception as exc:
                    receipt['git'] = {'state': 'pending', 'reason': str(exc)[:500]}
            receipt['state'] = 'complete' if receipt['git']['state'] in {'verified', 'deferred'} else 'git_pending'
            atomic_json(receipt_path, receipt)
            return receipt
