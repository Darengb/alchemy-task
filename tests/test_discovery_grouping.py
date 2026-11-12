"""One proposal per conversation: related asks are subtasks, stable on repeats, full-thread repeat check."""
import pytest
from alchemy_task.core import discovery_research as dr
from alchemy_task.core import taskfile as tf
from alchemy_task.discovery_digest import DiscoveryDigest
from alchemy_task import discovery_runner
from test_discovery_conversion import custom_joined
from test_discovery_schema import bundle

ORIGIN = {'session_id': 'chat'}
SLACK_A = 'https://example.slack.com/archives/C111/p1794325208261679'
SLACK_B = 'https://example.slack.com/archives/C222/p1794411111000001'


def _item(unit, rev, title, links, **extra):
    return {'unit_id': unit, 'research_revision': rev, 'title': title, 'kind': 'new', 'targets': [], 'source_links': links, **extra}


def _section(body, heading):
    return body.split('## ' + heading + '\n', 1)[1].split('\n## ', 1)[0].split('<!-- discovery-dossier', 1)[0]


def test_subtasks_are_optional_and_bounded():
    old = bundle()
    assert 'subtasks' not in dr.validate_bundle(old, old['candidate_id'], ['slack:T1:C1:171.1'])[0][1]
    b = bundle(); b['workstreams'][0]['subtasks'] = ['Send the proof', 'Book the print slot']
    assert dr.validate_bundle(b, b['candidate_id'], ['slack:T1:C1:171.1'])[0][1]['subtasks'] == ['Send the proof', 'Book the print slot']
    for bad in (['x'] * 9, ['x' * 141], ['']):
        b = bundle(); b['workstreams'][0]['subtasks'] = bad
        with pytest.raises(dr.UserError):
            dr.validate_bundle(b, b['candidate_id'], ['slack:T1:C1:171.1'])
    text = discovery_runner.GROUPING_INSTRUCTIONS
    assert 'one workstream per ACTION, not per conversation' in text and 'per conversation and list' not in text
    assert 'SAME action' in text and 'different existing tasks' in text and 'resolved or excluded' in text
    assert 'decisive message' in text and 'stand alone' in text
    assert len(text) < 900
    again = discovery_runner.PREVIOUS_RESEARCH_INSTRUCTIONS
    assert 'keep their titles' in again and 'genuinely new action' in again


def test_approved_create_writes_research_subtasks_as_checkboxes(settings, data_dir, tmp_path):
    rt, store, run, wid, conv = custom_joined(settings, data_dir, tmp_path, [], subtasks=['Send the proof to legal', 'Book the print slot'])
    conv.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User approved.')
    task = rt.store().resolve(conv.apply(run, wid)['task_id'])
    subs = _section(task.body, 'Subtasks')
    assert '- [ ] Send the proof to legal' in subs and '- [ ] Book the print slot' in subs
    assert task.body.split('<!-- discovery-dossier')[0].count('Book the print slot') == 1


def test_approved_update_appends_only_missing_subtasks(settings, data_dir, tmp_path):
    from alchemy_task.core.store import TaskStore
    tasks = TaskStore(settings, data_dir)
    doc = tasks.create(title='Label proof', area='work', undated=True, research=False, notes='My notes.', subtasks=['Send the proof to legal'])
    rt, store, run, wid, conv = custom_joined(settings, data_dir, tmp_path, [{'path': tasks.rel(doc.path), 'match_basis': 'related_only'}],
                                              subtasks=['Send the proof to legal', 'Book the print slot'])
    conv.prepare(run, wid, choice='update', user_approved=True, target_task_id=doc.task_id,
                 expected_revision=tf.content_hash(doc.raw), reason='User approved update.')
    actual = rt.store().resolve(conv.apply(run, wid)['task_id'])
    main = actual.body.split('<!-- discovery-dossier')[0]
    assert main.count('Send the proof to legal') == 1 and '- [ ] Book the print slot' in main
    assert '- [ ] Book the print slot' in _section(actual.body, 'Subtasks') and 'My notes.' in main


def test_previous_research_is_exposed_for_the_same_conversation(settings, data_dir, tmp_path):
    from test_discovery_state import setup
    custom_joined(settings, data_dir, tmp_path, [], title='Label proof', subtasks=['Book the print slot'])
    store, run2, items = setup(data_dir)
    earlier = dr.previous_research(store, run2, items[0])
    assert [x['title'] for x in earlier] == ['Label proof'] and earlier[0]['subtasks'] == ['Book the print slot']
    assert dr.previous_research(store, run2, {**items[0], 'source_ids': ['slack:T1:C9:999.1']}) == []


def test_digest_lists_subtasks_and_repeats_with_reordered_links_are_not_renumbered(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    steps = [f'Step {i}' for i in range(1, 8)]
    first = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M',
                           items=[_item('w_a', 'r1', 'Launch plan', [SLACK_A, SLACK_B], digest_next_action='Share the plan.', subtasks=steps)])
    text = first['text']
    assert '**Next action:** Share the plan.\n\n- Step 1\n' in text and '- Step 5\n- +2 more' in text and 'Step 6' not in text
    again = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, label='M',
                           items=[_item('w_b', 'r2', 'Launch plan, again', [SLACK_B, SLACK_A],
                                        digest_next_action='Confirm the date with Sam.', subtasks=['Step 1', 'Order the banners'])])
    assert again['items'] == [] and again['repeats'][0]['earlier_ref'] == 'M1'
    assert ('**Also from an earlier thread:** M1 gets a new step: Confirm the date with Sam; also: Order the banners') in again['text']
    assert 'Still open from earlier' not in again['text']


def test_waiting_reason_line(tmp_path):
    digest = DiscoveryDigest(tmp_path)
    cap = digest.prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, items=[], queued_count=16, queued_reason='daily_cap')
    assert '**Still researching:** 16 items are waiting for tomorrow (daily limit reached).' in cap['text']
    later = digest.prepare('run2', stream='mbg', day='2026-11-12', origin=ORIGIN, items=[], queued_count=2, queued_reason='time')
    assert '**Still researching:** 2 items are queued for the next scheduled run.' in later['text']
    now = digest.prepare('run3', stream='mbg', day='2026-11-13', origin=ORIGIN, items=[], queued_count=1, follow_up_started=True)
    assert '**Still researching:** 1 item is queued for the next run, which starts within 30 minutes.' in now['text']
