"""Post-join typed matching and recoverable whole-document discovery conversion.

Matching adapts the established helper's exact_task_matches nomination guard.
Semantic equivalence and useful delta remain parent judgments, never title scores.
"""
from __future__ import annotations
import json
import copy
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

    def _production(self, run):
        if self.store.get_run(run)['config'].get('mode') != 'production':
            raise UserError('task/Git conversion requires explicit production mode; shadow/research_only/missing modes cannot mutate tasks')

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

    def _exact_values(self, doc, *, slack_workspaces=None):
        # Related-only identities in a managed dossier never grant write authority.
        body = doc.body
        self._validate_dossiers(body)
        values = set()
        for match in re.finditer(r'<!-- discovery-dossier:start ([A-Za-z0-9._-]+) -->(.*?)<!-- discovery-dossier:end \1 -->', body, re.S):
            values.add('dossier:' + match[1])
            decisive = re.search(r'### Decisive Source Identities\n(.*?)(?=\n### |$)', match[2], re.S)
            if decisive:
                values.update(extract_identities(decisive[1], slack_workspaces=slack_workspaces))
        body = re.sub(r'<!-- discovery-dossier:start .*?<!-- discovery-dossier:end .*?-->', '', body, flags=re.S)
        metadata = {k: v for k, v in doc.fm.items() if k not in {'related_source_ids', 'discovery_related_source_ids'}}
        values.update(extract_identities(metadata, slack_workspaces=slack_workspaces))
        values.update(extract_identities(body, slack_workspaces=slack_workspaces))
        return values

    @staticmethod
    def _validate_dossiers(body):
        opened = None
        seen = set()
        for marker in re.finditer(r'<!-- discovery-dossier:(start|end) ([A-Za-z0-9._-]+) -->', body):
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

    def match(self, run, wid):
        candidate, research = self.joined(run, wid)
        wanted = {canonical_source_id(x) for x in research['exact_source_ids']}
        wanted.add('dossier:dos-' + wid[2:])
        nominations = {x['path']: x['match_basis'] for x in research['existing_task_candidates']}
        tasks = self.rt.store()
        for relative, basis in nominations.items():
            if basis != 'exact': continue
            path = (tasks.root / relative).resolve()
            if not any(path.is_relative_to(folder.resolve()) for _, folder in tasks.task_dirs()) or not path.is_file():
                raise UserError('exact task nomination is missing or outside canonical task directories')
            nominated = tf.parse_file(path)
            if not tf.has_task_tag(nominated.fm) or not nominated.task_id:
                raise UserError('exact nomination must be a tagged canonical task with stable task_id')
        workspaces = {}
        for source in self.store.get_run(run)['config'].get('sources', []):
            if isinstance(source, dict):
                for host, workspace in (source.get('url_mappings', {}).get('slack_workspaces') or {}).items():
                    if host in workspaces and workspaces[host] != workspace: raise UserError('conflicting approved workspace URL mapping')
                    workspaces[host] = workspace
        scan = tasks.scan()
        if scan.errors:
            raise UserError('canonical task inventory is incomplete; resolve parse failures before matching')
        exact, semantic = [], []
        for item in scan.tasks:
            doc = tf.parse_file(item.path)  # full current bytes, not cached summaries
            rel = tasks.rel(doc.path)
            values = self._exact_values(doc, slack_workspaces=workspaces)
            overlap = sorted(r for r in wanted if any(s == r or (source_identity_covers(s, r) and (not candidate.get('parent_candidate_id') or not is_message_refinement(r) or nominations.get(rel) == 'exact')) for s in values))
            # A genuine message is a container for independent frozen actions.
            # Shared-message provenance alone must not authorize another action.
            if candidate.get('action_id') and overlap and 'dossier:dos-' + wid[2:] not in overlap:
                bound = doc.fm.get('discovery_action_ids') or []
                if candidate['action_id'] not in bound and nominations.get(rel) != 'exact': overlap = []
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

    @staticmethod
    def _append_section(body, heading, text):
        """Insert before dossier tail; reuse one existing Notes/Plan/Log heading."""
        tail_at = body.find('<!-- discovery-dossier:start ')
        main, tail = (body[:tail_at], body[tail_at:]) if tail_at >= 0 else (body, '')
        heading_match = re.search(r'^## ' + re.escape(heading) + r'\s*$', main, re.M)
        if heading_match:
            next_heading = re.search(r'^## ', main[heading_match.end():], re.M)
            at = heading_match.end() + next_heading.start() if next_heading else len(main)
            main = main[:at].rstrip() + '\n\n' + text.rstrip() + '\n\n' + main[at:]
        else:
            main = main.rstrip() + '\n\n## ' + heading + '\n\n' + text.rstrip() + '\n\n'
        return main + tail

    def prepare(self, run, wid, *, choice, reason, target_task_id='', expected_revision='',
                useful_delta=False, user_approved=False, area='', title='', due='', undated=False,
                expected_plan_revision='', scope_notes='', priority='', scheduled='', execution_method='',
                notes='', plan='', checklist=None, active_goal='', manual_binding=False):
        self._production(run)
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
                       user_approved=user_approved, area=area, title=title, due=due, undated=undated,
                       scope_notes=scope_notes, priority=priority, scheduled=scheduled, execution_method=execution_method,
                       notes=notes, plan=plan, checklist=checklist, active_goal=active_goal, manual_binding=manual_binding)
        plan_path, _ = self._paths(run, wid)
        with self.store._lock('conversion:' + run + ':' + wid):
            old = read_json(plan_path)
            if old:
                if not expected_plan_revision and old['request'] != request:
                    raise UserError('conversion binding is immutable; resume exact saved conversion')
                if not expected_plan_revision: return old
                self._unwritten(old, run, wid, expected_plan_revision)
            task_store = self.rt.store()
            if choice != 'create':
                targets = [t for t in outcome['targets'] if t['task_id'] == target_task_id]
                manual = manual_binding is True and user_approved is True and bool(expected_plan_revision)
                if manual and outcome['kind'] == 'exact' and outcome['targets'][0]['task_id'] != target_task_id:
                    raise UserError('different exact destination exists; explicit manual binding refused')
                if not tf.valid_task_id(target_task_id) or (len(targets) != 1 and not manual):
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
                tid = old['task_id'] if old and old['request']['choice'] == 'create' else tf.new_task_id()
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
            if before:
                if title:
                    if not isinstance(title, str) or not title.strip() or len(title) > 200:
                        raise UserError('task title requires 1..200 characters')
                    fm['title'] = title.strip()
                if due or undated:
                    date = tf.parse_date_words(due, self.rt.settings.today(), 'due')
                    fm['due'] = date
                    fm['scheduled'] = date
                if area and area != fm.get('area'): raise UserError('rehome existing tasks through task_update, not discovery approval')
            for field, value in {'scope_notes': scope_notes, 'notes': notes, 'plan': plan, 'active_goal': active_goal, 'execution_method': execution_method}.items():
                if not isinstance(value, str) or len(value) > 16000: raise UserError(field + ' must be text up to 16000 characters')
            if priority:
                if priority not in tf.PRIORITIES: raise UserError('invalid priority override')
                fm['priority'] = priority
            if scheduled: fm['scheduled'] = tf.parse_date_words(scheduled, self.rt.settings.today(), 'scheduled')
            if execution_method: fm['execution_method'] = execution_method
            if active_goal: fm['active_goal'] = active_goal
            if notes or scope_notes: body = self._append_section(body, 'Notes', '\n\n'.join(x for x in (notes, scope_notes) if x))
            if plan or active_goal or execution_method: body = self._append_section(body, 'Plan', '\n\n'.join(x for x in (active_goal, plan, 'Execution method: ' + execution_method if execution_method else '') if x))
            if checklist is not None:
                if not isinstance(checklist, list) or len(checklist) > 50 or any(not isinstance(x, str) or not x.strip() or len(x) > 2000 for x in checklist): raise UserError('checklist requires bounded nonempty text items')
                body = self._append_section(body, 'Plan', '\n'.join('- [ ] ' + x for x in checklist))
            dossier_id = 'dos-' + wid[2:]
            active_research = copy.deepcopy(research)
            if active_goal or execution_method:
                active_research['substantive_next_action'] = (active_goal or research['substantive_next_action']) + ('\n\nExecution method: ' + execution_method if execution_method else '')
                active_research['implementation_context'] += ['User approval constraint: ' + x for x in (scope_notes, notes, plan) if x]
            revision, block = render_discovery_dossier(active_research, dossier_id=dossier_id, candidate_source_ids=candidate['source_ids'])
            if active_research != research:
                marker = f'<!-- discovery-dossier:end {dossier_id} -->'
                block = block.replace(marker, '### Historical Accepted Recommendation\n\n' + research['substantive_next_action'] + '\n\nAccepted evidence revision: ' + content_revision(research) + '\n' + marker)
            ids = fm.get('dossier_ids') or []
            if isinstance(ids, str): ids = [ids]
            if not isinstance(ids, list): raise UserError('invalid task dossier_ids')
            fm['dossier_ids'] = list(dict.fromkeys([*ids, dossier_id]))
            if candidate.get('action_id'):
                fm['discovery_action_ids'] = list(dict.fromkeys([*(fm.get('discovery_action_ids') or []), candidate['action_id']]))
            # Append synthesis before existing managed dossiers, preserving every old section.
            additions = [x for x in research['new_information'] if x and x not in body]
            if additions:
                start_marker, end_marker = f'<!-- discovery-context:start {dossier_id} -->', f'<!-- discovery-context:end {dossier_id} -->'
                text = start_marker + '\n### Discovery context\n\n' + '\n'.join('- ' + x for x in additions) + '\n' + end_marker
                if start_marker in body:
                    body, _ = upsert_managed_block(body, start_marker=start_marker, end_marker=end_marker, block=text)
                else: body = self._append_section(body, 'Notes', text)
                body = self._append_section(body, 'Log', '- ' + self.rt.settings.today() + ': Discovery context added (' + revision + ').')
            body, _ = upsert_managed_block(body, start_marker=f'<!-- discovery-dossier:start {dossier_id} -->',
                                            end_marker=f'<!-- discovery-dossier:end {dossier_id} -->', block=block)
            postimage = tf.render(fm, body, **({'seq_offset': doc.seq_offset, 'keep_blank': doc.blank_keys} if before else {}))
            plan = {'run_id': run, 'unit_id': wid, 'request': request, 'state': 'prepared',
                    'task_id': tid, 'path': task_store.rel(path), 'preimage_sha256': tf.content_hash(before) if before else None,
                    'postimage': postimage, 'postimage_sha256': tf.content_hash(postimage.encode()),
                    'dossier_id': dossier_id, 'research_revision': content_revision(research), 'dossier_revision': revision}
            if old:
                plan['history'] = [*old.get('history', []), old]
            atomic_json(plan_path, plan)  # UUID, path and FULL postimage persisted BEFORE any task write
            return plan

    def _unwritten(self, plan, run, wid, expected):
        if content_revision(plan) != expected: raise UserError('stale conversion plan revision')
        _, receipt_path = self._paths(run, wid)
        path = self.rt.store().root / plan['path']
        actual = path.read_bytes() if path.exists() else None
        if read_json(receipt_path) or (tf.content_hash(actual) if actual is not None else None) != plan['preimage_sha256']:
            raise UserError('conversion may already be written or task changed; cannot revise/cancel pending plan')
        if plan.get('merge_group'): raise UserError('revise/cancel the whole merge group, not one member')

    def revise(self, run, wid, *, expected_plan_revision, edits, reason):
        plan = read_json(self._paths(run, wid)[0])
        if not plan: raise UserError('no prepared plan to revise')
        if set(edits) - {'choice', 'target_task_id', 'expected_revision', 'area', 'title', 'due', 'undated', 'scope_notes', 'priority', 'scheduled', 'execution_method', 'notes', 'plan', 'checklist', 'active_goal'}:
            raise UserError('unsupported pending plan edits')
        request = {**plan['request'], **edits, 'reason': reason, 'user_approved': True}
        return self.prepare(run, wid, **request, expected_plan_revision=expected_plan_revision)

    def bind_manual(self, run, wid, *, target_task_id, expected_revision, expected_plan_revision, reason):
        old = read_json(self._paths(run, wid)[0])
        if not old or old['request']['choice'] != 'create': raise UserError('manual recovery requires an existing unwritten create plan')
        request = {**old['request'], 'choice': 'update', 'target_task_id': target_task_id, 'expected_revision': expected_revision,
                   'user_approved': True, 'manual_binding': True, 'reason': reason, 'area': '', 'title': '', 'due': '', 'undated': False}
        return self.prepare(run, wid, **request, expected_plan_revision=expected_plan_revision)

    def cancel(self, run, wid, *, expected_plan_revision, reason):
        if not reason: raise UserError('explicit cancellation reason required')
        plan_path, _ = self._paths(run, wid)
        with self.store._lock('conversion:' + run + ':' + wid):
            plan = read_json(plan_path)
            if not plan: raise UserError('no prepared plan to cancel')
            self._unwritten(plan, run, wid, expected_plan_revision)
            plan.update(state='cancelled', cancellation_reason=reason)
            atomic_json(plan_path, plan)
            return plan

    def merge_prepared(self, bindings, *, reason):
        """One user-approved task, every accepted dossier and per-unit receipt."""
        if len(bindings) < 2 or len(set(bindings)) != len(bindings) or not reason:
            raise UserError('explicit merge requires at least two distinct approved units and reason')
        group = 'merge-' + content_revision(sorted(bindings)).split(':')[-1][:32]
        manifest_path = self.store.state_root / 'conversion-groups' / (group + '.json')
        with self.store._lock('conversion-merge'):
            manifest = read_json(manifest_path)
            if manifest:
                self._materialize_merge(manifest)
                return manifest
            plans = []
            for run, wid in bindings:
                plan = read_json(self._paths(run, wid)[0])
                if not plan: raise UserError('prepare every selected proposal before merge')
                self._unwritten(plan, run, wid, content_revision(plan))
                plans.append(plan)
            first = plans[0]
            create = first['request']['choice'] == 'create'
            if any((p['request']['choice'] == 'create') != create or (not create and (p['task_id'], p['preimage_sha256']) != (first['task_id'], first['preimage_sha256'])) for p in plans):
                raise UserError('merge choices must all create one task or explicitly update the same task/revision')
            fm, body = tf.split_text(first['postimage'], rt=True)
            for (run, wid), plan in zip(bindings[1:], plans[1:]):
                candidate, research = self.joined(run, wid)
                marker = re.search(r'<!-- discovery-dossier:start ' + re.escape(plan['dossier_id']) + r' -->.*?<!-- discovery-dossier:end ' + re.escape(plan['dossier_id']) + r' -->', plan['postimage'], re.S)
                if not marker: raise UserError('merge member missing exact approved dossier block')
                block = marker[0]
                additions = [x for x in research['new_information'] if x not in body]
                if additions: body = self._append_section(body, 'Notes', '### Combined approved context\n\n' + '\n'.join('- ' + x for x in additions))
                for field, heading in (('notes', 'Notes'), ('scope_notes', 'Notes'), ('plan', 'Plan'), ('active_goal', 'Plan'), ('execution_method', 'Plan')):
                    value = plan['request'].get(field)
                    if value and value not in body: body = self._append_section(body, heading, value)
                member_fm, _ = tf.split_text(plan['postimage'], rt=True)
                for field in ('title', 'due', 'scheduled', 'priority', 'execution_method', 'active_goal'):
                    explicit = plan['request'].get(field) or (field in {'due', 'scheduled'} and plan['request'].get('undated'))
                    if explicit:
                        first_value = first['request'].get(field) or (field in {'due', 'scheduled'} and first['request'].get('undated'))
                        if first_value and fm.get(field) != member_fm.get(field): raise UserError('combined approvals contain conflicting explicit task metadata')
                        fm[field] = member_fm.get(field)
                body, _ = upsert_managed_block(body, start_marker=f"<!-- discovery-dossier:start {plan['dossier_id']} -->", end_marker=f"<!-- discovery-dossier:end {plan['dossier_id']} -->", block=block)
                fm['dossier_ids'] = list(dict.fromkeys([*fm['dossier_ids'], plan['dossier_id']]))
                if candidate.get('action_id'):
                    fm['discovery_action_ids'] = list(dict.fromkeys([*(fm.get('discovery_action_ids') or []), candidate['action_id']]))
            from .core import yamlio
            raw_fm = tf.split_raw(first['postimage'])[0]
            postimage = tf.render(fm, body, seq_offset=yamlio.seq_offset(raw_fm), keep_blank=frozenset(yamlio.blank_keys(raw_fm)))
            merged = []
            for plan in plans:
                merged.append({**plan, 'task_id': first['task_id'], 'path': first['path'], 'preimage_sha256': first['preimage_sha256'],
                               'postimage': postimage, 'postimage_sha256': tf.content_hash(postimage.encode()), 'merge_group': group})
            manifest = {'group_id': group, 'state': 'prepared', 'reason': reason, 'bindings': [list(b) for b in bindings],
                        'original_plans': plans, 'plans': merged}
            atomic_json(manifest_path, manifest)  # commit ALL postimages before materializing member pointers
            self._materialize_merge(manifest)
            return manifest

    def _materialize_merge(self, manifest):
        for original, merged in zip(manifest['original_plans'], manifest['plans']):
            path, _ = self._paths(merged['run_id'], merged['unit_id'])
            current = read_json(path)
            if current == merged: continue
            if current != original: raise UserError('merge member plan changed; do not overwrite revised intent')
            atomic_json(path, merged)

    def recover_merges(self, run, wid):
        for path in (self.store.state_root / 'conversion-groups').glob('merge-*.json'):
            manifest = read_json(path)
            if [run, wid] in manifest['bindings']:
                with self.store._lock('conversion-merge'):
                    self._materialize_merge(manifest)

    def preflight(self, bindings):
        """Validate the complete approved batch, including all CASes, before writes."""
        groups = {}
        for run, wid in bindings:
            plan = read_json(self._paths(run, wid)[0], {})
            if plan and plan.get('request', {}).get('choice') in {'update', 'auto'}:
                groups.setdefault(plan['path'], []).append((run, wid))
        for members in groups.values():
            if len(members) > 1:
                hashes = {read_json(self._paths(r, w)[0])['postimage_sha256'] for r, w in members}
                if len(hashes) > 1: self.merge_prepared(members, reason='Compose independently approved sibling updates to one exact preimage')
        destinations = {}
        for run, wid in bindings:
            self._production(run)
            self.recover_merges(run, wid)
            _, research = self.joined(run, wid)
            plan_path, receipt_path = self._paths(run, wid)
            plan = read_json(plan_path)
            if not plan or plan.get('state') == 'cancelled': raise UserError('missing or cancelled conversion plan')
            if content_revision(research) != plan['research_revision'] or tf.content_hash(plan['postimage'].encode()) != plan['postimage_sha256']:
                raise UserError('prepared plan hash/research binding mismatch')
            path = (self.rt.store().root / plan['path']).resolve()
            if not any(path.is_relative_to(folder.resolve()) for _, folder in self.rt.store().task_dirs()):
                raise UserError('conversion path outside task directories')
            prior = destinations.setdefault(str(path), plan['postimage_sha256'])
            if prior != plan['postimage_sha256']: raise UserError('several plans target same task; explicit combined merge required')
            actual = path.read_bytes() if path.exists() else None
            hash_ = tf.content_hash(actual) if actual is not None else None
            receipt = read_json(receipt_path)
            if hash_ != plan['postimage_sha256']:
                if receipt or hash_ != plan['preimage_sha256']:
                    raise tf.ConcurrentEditError('whole batch preflight CAS failed')
                outcome = self.match(run, wid)
                if outcome['kind'] == 'conflict' or (outcome['kind'] == 'exact' and (plan['request']['choice'] == 'create' or outcome['targets'][0]['task_id'] != plan['task_id'])):
                    raise UserError('destination identity changed during batch preflight')
            self._validate_dossiers(plan['postimage'])
        return {'state': 'verified', 'count': len(bindings)}

    def apply(self, run, wid):
        self.preflight([(run, wid)])
        _, research = self.joined(run, wid)
        plan_path, receipt_path = self._paths(run, wid)
        with self.store._lock('conversion:' + run + ':' + wid):
            plan = read_json(plan_path)
            if not plan:
                raise UserError('prepare immutable approved conversion first')
            if plan.get('state') == 'cancelled': raise UserError('conversion plan cancelled')
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
                    if current['kind'] == 'conflict' or (current['kind'] == 'exact' and (plan['request']['choice'] == 'create' or current['targets'][0]['task_id'] != plan['task_id'])):
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
                pass
            elif self.rt.settings.git_transport == 'none':
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
            from .ios_sync import discovery_mirror_status
            receipt['phone'] = discovery_mirror_status(self.rt, receipt['task_id'])
            receipt['state'] = ('git_pending' if receipt['git']['state'] not in {'verified', 'deferred'} else
                                'phone_pending' if receipt['phone']['state'] not in {'verified', 'deferred'} else 'complete')
            atomic_json(receipt_path, receipt)
            return receipt
