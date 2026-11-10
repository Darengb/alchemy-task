"""Discovery-created tasks get blank summary, notes, plan and subtasks filled at creation, same rules as research."""
import pytest
from alchemy_task.core import taskfile as tf
from alchemy_task.core import research as rs
from test_discovery_conversion import custom_joined

UNDERSTANDING = ('The vendor confirmed the new label proof is ready. Legal still has to sign off on the claim wording. '
                 'Printing is booked for next month. The old stock runs out in six weeks. A fifth sentence stays out.')
NEXT = 'Review the proof against the claim list. Send the wording to legal. Book the print slot once legal agrees.'


def _make(settings, data_dir, tmp_path, **changes):
    changes.setdefault('current_understanding', UNDERSTANDING)
    changes.setdefault('substantive_next_action', NEXT)
    changes.setdefault('implementation_context', ['The printer needs files two weeks ahead.'])
    return custom_joined(settings, data_dir, tmp_path, [], **changes)


def _section(body, heading):
    return body.split('## ' + heading + '\n', 1)[1].split('\n## ', 1)[0].split('<!-- ', 1)[0]


def _mark(settings):
    return rs.fill_marker(settings.today())


def test_new_task_gets_agent_summary_notes_plan_subtasks_with_markers(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                 summary='Get the new label proof through legal and booked for print.',
                 notes='The proof is ready. Legal has not signed off yet.',
                 plan=['Check the proof', 'Send wording to legal', 'Book the print slot'],
                 subtasks=['Check proof', 'Email legal'])
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert task.fm['summary'] == 'Get the new label proof through legal and booked for print.'
    notes, plan, subs = _section(task.body, 'Notes'), _section(task.body, 'Plan'), _section(task.body, 'Subtasks')
    assert 'The proof is ready.' in notes and _mark(settings) in notes
    assert '1. Check the proof' in plan and '3. Book the print slot' in plan and _mark(settings) in plan
    assert '- [ ] Check proof' in subs and '- [ ] Email legal' in subs and _mark(settings) in subs
    prints = task.fm['enrichment']['fill']
    assert set(prints) == {'summary', 'notes', 'plan', 'subtasks'}
    assert prints['summary'] == rs.fingerprint(task.fm['summary'])
    # what discovery wrote is research-owned: a later research run may refresh it
    assert rs.fill_targets(task.fm, task.body) == {k: 'refresh' for k in rs.FILL_SECTIONS}
    assert 'filled summary, notes, plan and subtasks' in task.body.split('## Log', 1)[1]
    assert task.body.index('## Subtasks') < task.body.index('<!-- discovery-dossier:start')


def test_fallback_fills_from_research_when_agent_supplies_nothing(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.')
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert task.fm['summary'].startswith('The vendor confirmed the new label proof is ready.')
    assert len(task.fm['summary']) <= 300
    notes = _section(task.body, 'Notes')
    assert 'Printing is booked for next month.' in notes and 'A fifth sentence stays out.' not in notes.split(_mark(settings))[0]
    plan = _section(task.body, 'Plan')
    assert '1. Review the proof against the claim list.' in plan
    assert '4. The printer needs files two weeks ahead.' in plan and _mark(settings) in plan
    assert '## Subtasks' not in task.body
    log = task.body.split('## Log', 1)[1]
    assert 'Subtasks skipped: not supplied at approval.' in log
    # the dossier still carries the full research
    assert UNDERSTANDING in task.body


def test_fallback_plan_omitted_when_fewer_than_three_steps(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path, substantive_next_action='Send it to legal.', implementation_context=[])
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.')
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert '## Plan' not in task.body.split('<!-- discovery-dossier:start')[0]
    assert 'plan' not in task.fm['enrichment']['fill']


def test_checklist_goes_to_subtasks_for_new_task(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                 checklist=['Verify print proof', 'Confirm date'])
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    subs = _section(task.body, 'Subtasks')
    assert '- [ ] Verify print proof' in subs and '- [ ] Confirm date' in subs
    assert 'Verify print proof' not in _section(task.body, 'Plan')


def test_short_agent_plan_text_is_kept_not_dropped(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                 plan='Read-only verification of the existing proof.')
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert 'Read-only verification of the existing proof.' in _section(task.body, 'Plan')


def test_update_never_overwrites_existing_sections(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    rt, store, run, wid, conv = joined(tmp_path, settings, data_dir)
    task = rt.store().create(title='Existing work', area='work', undated=True, research=False,
                             notes='User words stay. slack:T1:C1:171.1:171.2', plan='- My own plan', summary='My own summary.')
    conv.prepare(run, wid, choice='update', user_approved=True, target_task_id=task.task_id,
                 expected_revision=tf.content_hash(task.raw), reason='User approved update.',
                 summary='Agent summary.', subtasks=['New subtask'])
    actual = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert actual.fm['summary'] == 'My own summary.'
    assert 'User words stay.' in actual.body and '- My own plan' in actual.body
    assert '- [ ] New subtask' in _section(actual.body, 'Subtasks')   # blank Subtasks is filled
    assert 'Agent summary.' not in actual.raw.decode()


def test_crash_resume_writes_byte_identical_postimage(settings, data_dir, tmp_path, monkeypatch):
    from alchemy_task import discovery_conversion as module
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    args = dict(choice='create', user_approved=True, area='work', undated=True, reason='User approved.', subtasks=['One thing'])
    plan = conv.prepare(run, wid, **args)
    assert plan['request']['subtasks'] == ['One thing']
    assert conv.prepare(run, wid, **args) == plan          # same request resumes the frozen plan
    original = module.atomic_json
    def crash(path, value):
        if path.name.endswith('.receipt.json'):
            raise RuntimeError('crash after task write')
        return original(path, value)
    monkeypatch.setattr(module, 'atomic_json', crash)
    with pytest.raises(RuntimeError):
        conv.apply(run, wid)
    path = rt.store().root / plan['path']
    assert path.read_bytes() == plan['postimage'].encode()
    monkeypatch.setattr(module, 'atomic_json', original)
    receipt = conv.apply(run, wid)
    assert path.read_bytes() == plan['postimage'].encode() and receipt['local']['state'] == 'verified'
    assert _mark(settings) in plan['postimage']


def test_legacy_request_without_new_fields_still_resumes(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    plan = conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.')
    assert not {'summary', 'subtasks', 'subtasks_skipped_reason'} & set(plan['request'])


def test_fill_problems_never_block_conversion(settings, data_dir, tmp_path, monkeypatch):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    def boom(*a, **k):
        raise ValueError('bad fill')
    monkeypatch.setattr(rs, 'apply_fill', boom)
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                 summary='S.', subtasks=['x'])
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert '<!-- discovery-dossier:start' in task.body
    assert 'fill dropped (ValueError)' in task.body.split('## Log', 1)[1]


def test_bad_agent_subtasks_type_is_rejected_before_writing(settings, data_dir, tmp_path):
    from alchemy_task.core.discovery_identity import UserError
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    with pytest.raises(UserError, match='subtasks'):
        conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='r', subtasks='not a list')


def test_approved_text_past_fill_caps_is_appended_whole_not_dropped(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    checklist = [f'Checklist item number {i}' for i in range(25)]
    notes = ' '.join(f'Sentence {i} about the approved context.' for i in range(80))
    assert len(notes) > 2900
    plan = [f'Step {i} of the approved plan' for i in range(10)]
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                 notes=notes, plan=plan, checklist=checklist)
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    main = task.body.split('<!-- discovery-dossier:start')[0]
    for item in checklist: assert '- [ ] ' + item + '\n' in main
    assert notes in main
    for step in plan: assert step in main
    assert 'Step 9 of the approved plan' in _section(task.body, 'Plan')
    # nothing truncated was written as a fill in place of the approved text
    assert main.count('Checklist item number 0\n') == 1 and main.count('Step 0 of the approved plan') == 1


def test_agent_subtasks_past_cap_are_kept(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = _make(settings, data_dir, tmp_path)
    subtasks = [f'Agent subtask {i}' for i in range(15)]
    checklist = [f'Checklist entry {i}' for i in range(10)]
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                 subtasks=subtasks, checklist=checklist)
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    subs = _section(task.body, 'Subtasks')
    for item in subtasks + checklist: assert '- [ ] ' + item + '\n' in subs


def test_bind_manual_rebinds_create_plan_with_list_plan(settings, data_dir, tmp_path):
    from test_discovery_conversion import joined
    from alchemy_task.core.discovery_dossiers import content_revision
    rt, store, run, wid, conv = joined(tmp_path, settings, data_dir)
    prepared = conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.',
                            plan=['Check the proof', 'Send wording to legal', 'Book the print slot'])
    manual = rt.store().create(title='Manual task', area='work', undated=True, research=False, notes='Manual words.')
    conv.bind_manual(run, wid, target_task_id=manual.task_id, expected_revision=tf.content_hash(manual.raw),
                     expected_plan_revision=content_revision(prepared), reason='User named the manual task.')
    actual = rt.store().resolve(conv.apply(run, wid)['task_id'])
    assert actual.task_id == manual.task_id
    assert 'Check the proof' in actual.body and 'Book the print slot' in actual.body


def test_merge_does_not_duplicate_shared_notes_or_plan_and_keeps_member_subtasks(settings, data_dir):
    from test_discovery_completion import two_joined
    rt, store, run, units, conv = two_joined(settings, data_dir)
    shared = dict(choice='create', user_approved=True, area='work', undated=True, reason='User selected same combined task.',
                  notes='Shared approved notes paragraph.', plan=['First shared step', 'Second shared step', 'Third shared step'])
    conv.prepare(run, units[0], **shared, subtasks=['First member subtask'])
    conv.prepare(run, units[1], **shared, subtasks=['Second member subtask'], checklist=['Second member check'])
    conv.merge_prepared([(run, w) for w in units], reason='User explicitly merged these two proposals.')
    conv.preflight([(run, w) for w in units])
    doc = rt.store().resolve(conv.apply(run, units[0])['task_id'])
    main = doc.body.split('<!-- discovery-dossier:start')[0]
    assert main.count('Shared approved notes paragraph.') == 1
    assert main.count('First shared step') == 1
    subs = _section(doc.body, 'Subtasks')
    for item in ('First member subtask', 'Second member subtask', 'Second member check'):
        assert subs.count('- [ ] ' + item) == 1
