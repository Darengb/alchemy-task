"""One item that matches several existing tasks exactly becomes a numbered choice, never a dead end."""
import pytest
from alchemy_task.core import taskfile as tf
from alchemy_task.core.discovery_identity import UserError
from test_discovery_integration import service
from test_discovery_conversion import custom_joined
from test_discovery_digest_replies import _own, _coverage_complete
from test_setup import home  # noqa: F401  (fixture)

NOTE = 'slack:T1:C1:171.1:171.2'


def _two_exact(settings, data_dir, tmp_path, nominate=None):
    integration, rt, ctx = service(settings, data_dir, tmp_path)
    docs = [rt.store().create(title=t, area='work', undated=True, research=False, confirm_new=True, notes=NOTE)
            for t in ('Launch decision A', 'Launch decision B')]
    nominations, extra = [], {}
    if nominate is not None:
        rel = rt.store().rel(docs[nominate].path)
        nominations = [{'path': rel, 'match_basis': 'related_only', 'confidence': 'high'}]
        extra = {'recommended_task_path': rel}
    _, store, run, wid, _ = custom_joined(settings, data_dir, tmp_path, nominations, **extra)
    _own(store, run); _coverage_complete(store, run)
    return integration, rt, store, run, wid, docs


def test_multiple_exact_matches_are_a_numbered_choice(settings, data_dir, tmp_path):
    integration, rt, store, run, wid, docs = _two_exact(settings, data_dir, tmp_path)
    assert integration.conversion.match(run, wid)['kind'] == 'conflict'
    before = [d.path.read_bytes() for d in docs]
    integration.record_decision(run, wid, decision='propose', reason='Two exact tasks; the user picks.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    text = digest['text']
    item = digest['items'][0]
    ref = item['ref']
    assert item['kind'] == 'selection' and [t['task_id'] for t in item['targets']] == [d.task_id for d in docs]
    assert '**Task type:** Potential existing task update' in text
    assert '**Existing tasks:**\n1. Launch decision A\n2. Launch decision B\n' in text
    assert f'Reply "{ref}, update 1" or "{ref}, update 2" to add this to that task, or "{ref}, create" for a separate task.' in text
    assert 'blocked' not in text and 'conflict' not in text
    assert [d.path.read_bytes() for d in docs] == before


def test_multiple_exact_matches_refuse_automatic_writes(settings, data_dir, tmp_path):
    integration, rt, store, run, wid, docs = _two_exact(settings, data_dir, tmp_path)
    for decision in ('auto', 'noop'):
        with pytest.raises(UserError, match='several|multiple'):
            integration.record_decision(run, wid, decision=decision, reason='Guess.', session_id='parent',
                                        target_task_id=docs[0].task_id, expected_revision=tf.content_hash(docs[0].raw), useful_delta=True)


def test_research_recommendation_allows_plain_update(settings, data_dir, tmp_path):
    integration, rt, store, run, wid, docs = _two_exact(settings, data_dir, tmp_path, nominate=1)
    integration.record_decision(run, wid, decision='propose', reason='Two exact tasks; research prefers B.', session_id='parent')
    digest = integration.finalize(run, session_id='parent')
    ref = digest['items'][0]['ref']
    assert '**Existing tasks:**\n1. Launch decision B (recommended)\n2. Launch decision A\n' in digest['text']
    assert f'Reply "{ref}, update" to add this to "Launch decision B", "{ref}, update 2" for the other task' in digest['text']


def test_user_choice_updates_only_the_chosen_exact_task(settings, data_dir, tmp_path):
    integration, rt, store, run, wid, docs = _two_exact(settings, data_dir, tmp_path)
    conversion = integration.conversion
    first, second = docs[0].path.read_bytes(), docs[1].path.read_bytes()
    with pytest.raises(UserError):
        conversion.prepare(run, wid, choice='update', reason='No approval.', target_task_id=docs[1].task_id,
                           expected_revision=tf.content_hash(docs[1].raw))
    conversion.prepare(run, wid, choice='update', user_approved=True, reason='User chose update 2.',
                       target_task_id=docs[1].task_id, expected_revision=tf.content_hash(docs[1].raw))
    conversion.apply(run, wid)
    assert docs[0].path.read_bytes() == first
    assert docs[1].path.read_bytes() != second
    assert 'discovery-dossier' in docs[1].path.read_text()


def test_user_may_create_a_separate_task_instead(settings, data_dir, tmp_path):
    integration, rt, store, run, wid, docs = _two_exact(settings, data_dir, tmp_path)
    count = len(rt.store().scan().tasks)
    integration.conversion.prepare(run, wid, choice='create', user_approved=True, area='work', undated=True, reason='User chose create.')
    integration.conversion.apply(run, wid)
    assert len(rt.store().scan().tasks) == count + 1
