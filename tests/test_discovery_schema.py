import copy
import json
from pathlib import Path
import pytest
from alchemy_task.core import discovery_research as m


def bundle():
    return json.loads((Path(__file__).parent / 'fixtures/discovery/bundle.json').read_text())


def test_full_contract_and_tolerant_extraction():
    b = bundle()
    for text in [json.dumps(b), 'Result:\n```json\n'+json.dumps(b)+'\n```\nDone.']:
        assert m.extract_json(text) == b
    units = m.validate_bundle(b, b['candidate_id'], ['slack:T1:C1:171.1'])
    assert len(units) == 1
    assert units[0][1]['status'] == 'complete'
    with pytest.raises(m.UserError):
        m.extract_json('{"candidate_id":1,"candidate_id":2}')


@pytest.mark.parametrize('field', list(bundle()['workstreams'][0]))
def test_every_original_field_is_required_without_jsonschema(field):
    b=bundle();del b['workstreams'][0][field]
    with pytest.raises(m.UserError):
        m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])


@pytest.mark.parametrize('bad', [lambda w: w['owner_and_collaborators'][0].update(role='boss'), lambda w: w['decisions_and_open_questions'].update(extra=[]), lambda w: w.update(title='x'*301), lambda w: w.update(source_links=[{}]), lambda w: w.update(exact_source_ids=['slack:T1:C1:171.1']), lambda w: w.update(existing_task_candidates=[{'path':'../task.md','match_basis':'exact'}]), lambda w: w.update(existing_task_candidates=[{'path':'areas/work/tasks/a.md','match_basis':'related_only','unknown':True}]), lambda w: w.update(represented_candidate_ids=['c_'+'b'*20]), lambda w: w.update(source_links=['https://example.test/?token=secret-value'])])
def test_invalid_nested_values_fail_closed(bad):
    b=bundle();bad(b['workstreams'][0])
    with pytest.raises(m.UserError):
        m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])


def test_atomic_ineligibility_related_boundary_and_self_representation():
    b=bundle();w=b['workstreams'][0]
    w['represented_candidate_ids']=[b['candidate_id']]
    w['related_source_ids']=[{'type':'notion','page_id':f'{i:032x}'} for i in range(14)]
    units=m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])
    assert units[0][1]['represented_candidate_ids']==[]
    w['related_source_ids'].append({'type':'notion','page_id':f'{20:032x}'})
    with pytest.raises(m.UserError,match='source identity count'):
        m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])
    b=bundle();other=copy.deepcopy(b['workstreams'][0]);other['exact_source_ids'][0]['message_ts']='171.9';other['research_status']='insufficient';b['workstreams'].append(other)
    with pytest.raises(m.UserError,match='delivery-ineligible'):
        m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])


def test_same_message_requires_verified_frozen_independent_anchors():
    from alchemy_task.core.discovery_identity import freeze_actions
    b=bundle();w=b['workstreams'][0];other=copy.deepcopy(w);b['workstreams'].append(other)
    for i,unit in enumerate(b['workstreams'],1):
        unit.update(action_key=f'ask{i}',action_anchor={'locator':f'bullet:{i}','outcome':f'Outcome {i}'},action_relation='independent')
    with pytest.raises(m.UserError):
        m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])
    registry=freeze_actions(b['candidate_id'],['slack:T1:C1:171.1'],[x['action_anchor'] for x in b['workstreams']])
    units=m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'],action_registry=registry)
    assert len({u[0] for u in units})==2
    retry=copy.deepcopy(b);retry['workstreams'].reverse();retry['workstreams'][0]['title']='Edited display'
    assert {u[0] for u in m.validate_bundle(retry,b['candidate_id'],['slack:T1:C1:171.1'],action_registry=registry)}=={u[0] for u in units}


@pytest.mark.parametrize('field', ['research_status','disposition','execution_classification'])
def test_wrong_enum_type_returns_validation_error_not_runtime_exception(field):
    b=bundle();b['workstreams'][0][field]=[]
    with pytest.raises(m.UserError):m.validate_bundle(b,b['candidate_id'],['slack:T1:C1:171.1'])


def test_nested_schema_oracle_parity_for_types_keys_and_limits():
    js=pytest.importorskip('jsonschema');validator=js.Draft202012Validator(m.child_schema())
    cases=[bundle()]
    base=bundle();w=base['workstreams'][0]
    for key in w:
        for value in [None,False,1,{},[], 'x'*4001]:
            mutated=copy.deepcopy(base);mutated['workstreams'][0][key]=value;cases.append(mutated)
    for key in ['name','role']:
        mutated=copy.deepcopy(base);del mutated['workstreams'][0]['owner_and_collaborators'][0][key];cases.append(mutated)
    for count in [0,1,12,13]:
        mutated=copy.deepcopy(base);mutated['workstreams']=[copy.deepcopy(w) for _ in range(count)];cases.append(mutated)
    for exact_count in [1,2,14,15]:
        for related_count in [0,1,14,15]:
            mutated=copy.deepcopy(base);mutated['workstreams'][0]['exact_source_ids']=[{'type':'gmail','account':'work','thread_id':str(i)} for i in range(exact_count)];mutated['workstreams'][0]['related_source_ids']=[{'type':'gmail','account':'related','thread_id':str(i)} for i in range(related_count)];cases.append(mutated)
    for value in cases:
        oracle=not list(validator.iter_errors(value))
        try:m.validate_shape(value);actual=True
        except m.UserError:actual=False
        assert actual==oracle


def test_schema_oracle_if_available():
    js=pytest.importorskip('jsonschema')
    schema=m.child_schema();js.Draft202012Validator.check_schema(schema)
    js.Draft202012Validator(schema).validate(bundle())
    for value in [False,None,[],{'workstreams':[]}]:
        assert list(js.Draft202012Validator(schema).iter_errors(value))
        with pytest.raises(m.UserError): m.validate_shape(value)


def test_shared_decisive_message_error_tells_the_child_how_to_repair():
    b = bundle()
    other = copy.deepcopy(b['workstreams'][0]); other['title'] = 'Second ask in the same message'
    b['workstreams'].append(other)
    with pytest.raises(m.UserError, match='duplicate workstream decisive identity') as caught:
        m.validate_bundle(b, b['candidate_id'], ['slack:T1:C1:171.1'])
    assert 'merge them into one workstream' in str(caught.value) and 'subtasks' in str(caught.value)
