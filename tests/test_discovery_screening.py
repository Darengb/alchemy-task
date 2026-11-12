import json
from pathlib import Path

from alchemy_task import discovery_sources
from alchemy_task.core.discovery_state import DiscoveryStore
from alchemy_task.core.screening import screen, screen_items

CFG = {'source_key': 'source', 'account_key': 'account', 'scope': {'folder': 'all'}, 'read_method': 'approved_reader'}
START, END = '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'


def item(n, title, *messages, **extra):
    msgs = [{'id': f'm{n}-{i}', 'author': a, 'time': START, 'text': t} for i, (a, t) in enumerate(messages)]
    return {'source_ids': [f'source:source:account:thread:t{n}'], 'source_revision': 'r1', 'title': title, 'messages': msgs, **extra}


HUMAN = 'Pat Lee <pat@example.test>'


def test_rules_exclude_low_value_and_keep_when_unsure():
    drop = {
        'calendar': item(1, 'Invitation: Weekly sync', ('cal@example.test', 'Join the call'), subject='Invitation: Weekly sync @ Mon'),
        'updated': item(2, 'Updated invitation: Pat / Sam', ('Pat', 'See you')),
        'calendar_text': item(3, 'Sync', (HUMAN, 'Invitation from Google Calendar. You are receiving this email because you are an attendee.')),
        'auto': item(4, 'Automatic reply: rider', (HUMAN, 'I am out of the office until Monday.')),
        'auto_text': item(5, 'Re: rider', (HUMAN, "Hi, I'm currently out of the office with limited access.")),
        'bulk_header': item(6, '4 nutrients linked to better mood', ('News <news@brand.test>', 'Read more'), headers={'List-Unsubscribe': '<mailto:x>'}),
        'bulk_link': item(7, 'Save your seat', ('Brand <no-reply@brand.test>', 'Join our webinar. Unsubscribe here.')),
        'bot': item(8, 'Build failed', ('github-actions[bot]', 'Run 12 failed')),
        'parent': item(9, 'fixing it now', (HUMAN, 'fixing it now'), disposition='exclude', reason='Fragment of the deploy thread'),
    }
    for name, it in drop.items():
        keep, reason = screen(it)
        assert not keep and reason, name
    assert screen(drop['parent'])[1] == 'parent: Fragment of the deploy thread'
    keep = {
        'human': item(10, 'Can you send the rider?', (HUMAN, 'Can you send the rider by Friday?')),
        'surname': item(11, 'Venue', ('Jane Talbot <jane@example.test>', 'Please confirm the venue.')),
        'reply_to_bulk': item(12, 'Re: newsletter', ('News <news@brand.test>', 'Unsubscribe'), (HUMAN, 'Should we sponsor this?'),
                              headers={'List-Unsubscribe': '<mailto:x>'}),
        'reply_to_invite': item(13, 'Re: Invitation: Offsite', (HUMAN, 'Can we move this to 3pm?')),
        'parent_research': item(14, 'Invitation: Budget review', ('cal@example.test', 'Agenda attached'), disposition='research'),
        'empty': {'title': 'x'},
    }
    for name, it in keep.items():
        assert screen(it) == (True, ''), name
    kept, screened = screen_items([*drop.values(), *keep.values()])
    assert len(kept) == len(keep) and len(screened) == len(drop)


def test_collect_saves_screened_items_as_excluded_backlog(tmp_path):
    store = DiscoveryStore(tmp_path / 'discovery')
    items = [item(1, 'Can you send the rider?', (HUMAN, 'Can you send the rider by Friday?')),
             item(2, 'Invitation: Weekly sync', ('cal@example.test', 'Join')),
             item(3, 'Hmmm maybe', (HUMAN, 'Hmmm maybe'), disposition='exclude', reason='Merged into the rider thread')]
    receipt = discovery_sources.collect_attested(store, 'stream', CFG, {'start': START, 'end': END, 'account_key': 'account', 'items': items, 'status': 'complete', 'pagination_exhausted': True})
    backlog = {x['candidate']['title']: x for x in store.source_state('stream', 'source')['backlog']}
    assert backlog['Can you send the rider?']['status'] == 'queued'
    assert backlog['Invitation: Weekly sync']['status'] == 'excluded'
    assert backlog['Invitation: Weekly sync']['lineage'] == {'screened': 'calendar notice'}
    assert backlog['Hmmm maybe']['lineage'] == {'screened': 'parent: Merged into the rider thread'}
    assert set(receipt['backlog_ids']) == {x['backlog_id'] for x in backlog.values()}
    assert [x['reason'] for x in receipt['screened']] == ['calendar notice', 'parent: Merged into the rider thread']
    # Collecting the same items again is idempotent and keeps them excluded.
    discovery_sources.collect_attested(store, 'stream', CFG, {'start': START, 'end': END, 'account_key': 'account', 'items': items, 'status': 'complete'})
    assert sorted(x['status'] for x in store.source_state('stream', 'source')['backlog']) == ['excluded', 'excluded', 'queued']


def _synthetic(workspace, skills, n_tasks=120, n_skills=60):
    folder = workspace / 'areas' / 'work' / 'tasks'
    for i in range(n_tasks):
        body = (f'Context line {i} about the vendor contract and budget.\n' * 60)
        (folder / f'2026-10-01-synthetic-task-{i}.md').write_text(
            f'---\ntitle: "Synthetic task {i}"\nschema_version: 1\nstatus: {"done" if i % 3 == 0 else "open"}\npriority: normal\n'
            f'area: work\ndue: 2026-12-{1 + i % 28:02d}\ncreated: "2026-10-01"\ntags:\n  - task\n---\n\n## Notes\n\n{body}')
    for i in range(n_skills):
        (skills / f'topic{i}-operations').mkdir(parents=True)
        (skills / f'topic{i}-operations' / 'SKILL.md').write_text(f'---\nname: topic{i}-operations\ndescription: Use when handling topic{i} work.\n---\n' + 'Guidance.\n' * 400)
    (skills / 'alchemy-task' / 'discovery').mkdir(parents=True)
    (skills / 'alchemy-task' / 'discovery' / 'SKILL.md').write_text('---\nname: alchemy-task:discovery\ndescription: Discovery.\n---\nRubric.\n')


def _legacy_fetch_all_bytes(rt, skills):
    """Bytes a child read before: full inventory with body descriptors, a bootstrap naming every
    task body, every task body and every installed skill (children were told to fetch all)."""
    scan = rt.store().scan()
    bodies = [d.raw for d in scan.tasks]
    descriptor = {'name': 'task-body-' + 'x' * 24, 'sha256': 'x' * 64, 'total_bytes': 10000, 'entry_count': None}
    inventory = {'tasks': [{'path': rt.store().rel(d.path), 'filename': d.path.name, 'title': d.title, 'task_id': '', 'status': d.status, 'body': descriptor} for d in scan.tasks]}
    bootstrap = {f'task-body-{i}': descriptor for i in range(len(bodies))}
    skill_bytes = sum(len(p.read_bytes()) for p in skills.rglob('SKILL.md'))
    return sum(map(len, bodies)) + len(json.dumps(inventory)) + len(json.dumps(bootstrap)) + skill_bytes


def test_compact_task_index_bodies_on_demand_and_relevant_skills(settings, data_dir, tmp_path):
    from alchemy_task.discovery_context import DiscoveryContext
    from alchemy_task.runtime import Runtime
    rt = Runtime(settings=settings, data_dir=data_dir)
    skills = tmp_path / 'skills'
    _synthetic(Path(settings.workspace_root), skills)
    store = DiscoveryStore(data_dir / 'discovery'); run = store.init_run()
    store.add_candidates(run, [{'title': 'Renew the topic7 contract', 'source_ids': ['source:source:account:thread:t1'], 'summary': 'Pat asks for the renewal'}])
    resources = DiscoveryContext(rt, store, installed_skills_root=skills).freeze(run, source_config={}, rubric='rubric')

    def read(info):
        return (store.run_dir(run) / 'resources' / info['sha256']).read_text()
    inventory = json.loads(read(resources['task_inventory']))
    entry = next(x for x in inventory['tasks'] if x['title'] == 'Synthetic task 5')
    assert set(entry) == {'task_id', 'title', 'status', 'area', 'due', 'summary', 'path', 'body', 'revision'}
    assert entry['area'] == 'work' and entry['due'] == '2026-12-06' and entry['summary'].startswith('Context line 5')
    assert not any(name.startswith(('task-body-', 'installed-skill-')) for name in resources)
    page = store.fetch_resource(run, entry['body'], revision=entry['revision'], reader='test', limit=16384)
    assert page['content'].startswith('---\ntitle: "Synthetic task 5"')
    assert [x['name'] for x in json.loads(read(resources['skill-inventory']))] == ['alchemy-task/discovery', 'topic7-operations']

    before = _legacy_fetch_all_bytes(rt, skills)
    after = sum(info['total_bytes'] for info in resources.values())  # everything a child must read now
    print(f'context bytes before={before} after={after} ratio={after / before:.3f}')
    assert after * 5 < before
