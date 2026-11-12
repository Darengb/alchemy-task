import copy
import json
from pathlib import Path

import pytest

from alchemy_task.core import discovery_research as m
from alchemy_task.core.discovery_identity import UserError
from alchemy_task.discovery_conversion import order_semantic_targets
from alchemy_task.discovery_digest import DiscoveryDigest, choice_line
from alchemy_task.discovery_integration import resolve_target_reply

ORIGIN = {'session_id': 'chat'}
IM8 = {'task_id': 't_im8', 'title': "What You'll Feel PDP Section (IM8 Style)", 'path': 'Tasks/im8.md'}
MULTI = {'task_id': 't_multi', 'title': 'ultimate multivitamin PDP sections', 'path': 'Tasks/multi.md'}
THIRD = {'task_id': 't_third', 'title': 'Third task', 'path': 'Tasks/third.md'}


def bundle():
    return json.loads((Path(__file__).parent / 'fixtures/discovery/bundle.json').read_text())


def research(*candidates, recommended=None):
    out = {'existing_task_candidates': [dict(c) for c in candidates]}
    if recommended: out['recommended_task_path'] = recommended
    return out


# Research fields: optional, older bundles stay valid.

def test_confidence_and_recommended_path_are_optional_and_validated():
    b = bundle(); w = b['workstreams'][0]
    w['existing_task_candidates'] = [{'path': 'Tasks/multi.md', 'match_basis': 'related_only', 'confidence': 'high'},
                                     {'path': 'Tasks/im8.md', 'match_basis': 'related_only'}]
    w['recommended_task_path'] = 'Tasks/multi.md'
    m.validate_shape(b)
    units = m.validate_bundle(b, b['candidate_id'], ['slack:T1:C1:171.1'])
    assert units[0][1]['recommended_task_path'] == 'Tasks/multi.md'
    assert units[0][1]['existing_task_candidates'][0]['confidence'] == 'high'
    m.validate_bundle(bundle(), bundle()['candidate_id'], ['slack:T1:C1:171.1'])  # older bundle
    for bad in [lambda w: w['existing_task_candidates'][0].update(confidence='sure'),
                lambda w: w.update(recommended_task_path='Tasks/elsewhere.md'),
                lambda w: w.update(recommended_task_path=3)]:
        x = copy.deepcopy(b); bad(x['workstreams'][0])
        with pytest.raises(UserError):
            m.validate_bundle(x, x['candidate_id'], ['slack:T1:C1:171.1'])


def test_schema_oracle_accepts_the_optional_fields():
    js = pytest.importorskip('jsonschema')
    b = bundle(); w = b['workstreams'][0]
    w['existing_task_candidates'] = [{'path': 'Tasks/multi.md', 'match_basis': 'exact', 'confidence': 'medium'}]
    w['recommended_task_path'] = 'Tasks/multi.md'
    js.Draft202012Validator(m.child_schema()).validate(b)
    w['existing_task_candidates'][0]['confidence'] = 'certain'
    assert list(js.Draft202012Validator(m.child_schema()).iter_errors(b))


# Ordering and recommendation.

def test_research_order_is_kept_and_recommended_path_is_marked_first():
    r = research({'path': 'Tasks/multi.md', 'match_basis': 'related_only'}, {'path': 'Tasks/im8.md', 'match_basis': 'related_only'},
                 recommended='Tasks/multi.md')
    out = order_semantic_targets([IM8, MULTI], r)
    assert [t['task_id'] for t in out] == ['t_multi', 't_im8']
    assert out[0]['recommended'] is True and 'recommended' not in out[1]


def test_single_high_confidence_is_recommended_and_confidence_orders():
    r = research({'path': 'Tasks/im8.md', 'match_basis': 'related_only', 'confidence': 'low'},
                 {'path': 'Tasks/third.md', 'match_basis': 'related_only', 'confidence': 'medium'},
                 {'path': 'Tasks/multi.md', 'match_basis': 'related_only', 'confidence': 'high'})
    out = order_semantic_targets([IM8, THIRD, MULTI], r)
    assert [t['task_id'] for t in out] == ['t_multi', 't_third', 't_im8']
    assert [bool(t.get('recommended')) for t in out] == [True, False, False]


def test_no_clear_recommendation_marks_none():
    two_high = research({'path': 'Tasks/im8.md', 'match_basis': 'related_only', 'confidence': 'high'},
                        {'path': 'Tasks/multi.md', 'match_basis': 'related_only', 'confidence': 'high'})
    out = order_semantic_targets([MULTI, IM8], two_high)
    assert [t['task_id'] for t in out] == ['t_im8', 't_multi']
    assert not any(t.get('recommended') for t in out)
    plain = order_semantic_targets([MULTI, IM8], research({'path': 'Tasks/im8.md', 'match_basis': 'related_only'},
                                                          {'path': 'Tasks/multi.md', 'match_basis': 'related_only'}))
    assert [t['task_id'] for t in plain] == ['t_im8', 't_multi'] and not any(t.get('recommended') for t in plain)


# Digest lines.

def item(unit, targets, kind='selection'):
    return {'unit_id': unit, 'research_revision': unit, 'title': 'Title ' + unit, 'kind': kind, 'targets': targets,
            'current_understanding': 'State.', 'substantive_next_action': 'Next.', 'digest_addition': 'Adds the new section.'}


def test_digest_lists_each_task_on_its_own_line_with_recommendation(tmp_path):
    targets = order_semantic_targets([IM8, MULTI], research({'path': 'Tasks/multi.md', 'match_basis': 'related_only'},
                                                            {'path': 'Tasks/im8.md', 'match_basis': 'related_only'},
                                                            recommended='Tasks/multi.md'))
    d = DiscoveryDigest(tmp_path).prepare(
        'run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M', items=[item('u1', targets)])
    text = d['text']
    assert ('**Task type:** Potential existing task update\n**Existing tasks:**\n'
            "1. ultimate multivitamin PDP sections (recommended)\n2. What You'll Feel PDP Section (IM8 Style)\n") in text
    assert ('**Choice:** Reply "M1, update" to add this to "ultimate multivitamin PDP sections", '
            '"M1, update 2" for the other task, or "M1, create" for a separate task.') in text
    assert ';' not in text.split('**Existing tasks:**')[1].split('**Choice:**')[0]
    assert '\u2014' not in text
    # The frozen binding keeps the listed order so positions stay stable.
    assert [t['task_id'] for t in d['items'][0]['targets']] == ['t_multi', 't_im8']


def test_choice_lines_for_three_tasks_no_recommendation_and_single():
    three = [dict(MULTI, recommended=True), IM8, THIRD]
    assert choice_line('M29', three) == ('Reply "M29, update" to add this to "ultimate multivitamin PDP sections", '
                                         '"M29, update 2" or "M29, update 3" for another listed task, or "M29, create" for a separate task.')
    assert choice_line('M29', [IM8, MULTI]) == ('Reply "M29, update 1" or "M29, update 2" to add this to that task, '
                                                'or "M29, create" for a separate task.')
    assert choice_line('M29', [IM8]) == 'Reply "M29, update" to add this to the existing task, or "M29, create" for a separate task.'


def test_single_target_keeps_one_line(tmp_path):
    d = DiscoveryDigest(tmp_path).prepare('run1', stream='mbg', day='2026-11-11', origin=ORIGIN, label='M',
                                          items=[item('u1', [IM8], kind='semantic')])
    assert "**Existing task:** What You'll Feel PDP Section (IM8 Style)\n" in d['text']
    assert '**Existing tasks:**' not in d['text']


# Reply resolution.

def proposal(targets):
    return {'kind': 'selection', 'targets': targets}


def test_update_takes_recommended_and_update_n_takes_listed_position():
    p = proposal([dict(MULTI, recommended=True), IM8])
    assert resolve_target_reply(p, {'choice': 'update'}) == {'choice': 'update', 'target_task_id': 't_multi'}
    assert resolve_target_reply(p, {'choice': 'update 2'}) == {'choice': 'update', 'target_task_id': 't_im8'}
    assert resolve_target_reply(p, {'choice': 'update', 'target_position': 1}) == {'choice': 'update', 'target_task_id': 't_multi'}
    assert resolve_target_reply(p, {'choice': 'create'}) == {'choice': 'create'}
    with pytest.raises(UserError, match='not one of'):
        resolve_target_reply(p, {'choice': 'update 3'})
    with pytest.raises(UserError, match='different tasks'):
        resolve_target_reply(p, {'choice': 'update 2', 'target_task_id': 't_multi'})


def test_update_without_recommendation_still_asks_which_task():
    p = proposal([IM8, MULTI])
    assert resolve_target_reply(p, {'choice': 'update'}) == {'choice': 'update'}
    assert resolve_target_reply(p, {'choice': 'update 1'}) == {'choice': 'update', 'target_task_id': 't_im8'}


def test_decide_resolved_uses_the_frozen_positions(monkeypatch):
    from alchemy_task import discovery_integration as di
    calls = []

    class Conv:
        def _paths(self, run, unit): return Path('/nonexistent/plan.json'), Path('/nonexistent/receipt.json')
        def prepare(self, run, unit, **kw): calls.append(kw)
        def preflight(self, items): pass
        def apply(self, run, unit): return {'state': 'pending'}

    class Dig:
        def __init__(self, props): self.props = props
        def _load(self): return {'proposals': {p['proposal_id']: {'state': 'pending'} for p in self.props.values()}}
        def decide(self, pid, state): pass

    props = {'M1': {'proposal_id': 'p1', 'run_id': 'r', 'unit_id': 'w', 'kind': 'selection', 'targets': [dict(MULTI, recommended=True), IM8]},
             'M2': {'proposal_id': 'p2', 'run_id': 'r', 'unit_id': 'w2', 'kind': 'selection', 'targets': [IM8, MULTI]}}
    svc = di.DiscoveryIntegration.__new__(di.DiscoveryIntegration)
    svc.conversion, svc.digest, svc.rt = Conv(), Dig(props), object()
    svc._decide_resolved({'approve': ['M1'], 'edits': {'M1': {'choice': 'update'}}}, resolve=lambda ref: props[ref])
    assert calls[-1]['choice'] == 'update' and calls[-1]['target_task_id'] == 't_multi'
    svc._decide_resolved({'approve': ['M1'], 'edits': {'M1': {'choice': 'update 2'}}}, resolve=lambda ref: props[ref])
    assert calls[-1]['target_task_id'] == 't_im8'
    with pytest.raises(UserError, match='ask which task'):
        svc._decide_resolved({'approve': ['M2'], 'edits': {'M2': {'choice': 'update'}}}, resolve=lambda ref: props[ref])
