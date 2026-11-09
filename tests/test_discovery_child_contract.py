"""The child must receive exact frozen mechanics, not guess them."""
import json
import pytest
from test_discovery_runner import setup_runner
from test_discovery_schema import bundle


def test_frozen_own_action_registry_is_a_required_immutable_child_resource(tmp_path):
    runner, store, _, run = setup_runner(tmp_path, count=1)
    cid = store.get_run(run)['candidates'][0]['candidate_id']
    registry = store.freeze_action_registry(run, cid, [
        {'locator': 'message:latest/proof', 'outcome': 'Approve latest proof'},
        {'locator': 'message:latest/chase', 'outcome': 'Supplier chase already resolved'},
    ])
    attempt = store.reserve_attempt(run, cid, owner_session='parent')
    boot = json.loads(runner._bootstrap(run, attempt)['context'])
    name = attempt.get('action_registry_resource')
    assert name and name in attempt['required_resources']
    assert name in boot['resources']
    descriptor = boot['resources'][name]
    actual = json.loads((store.run_dir(run) / 'resources' / descriptor['sha256']).read_text())
    assert actual == registry
    assert boot['action_registry_resource'] == name
    assert len(json.dumps(boot)) < 32000


def test_generic_typed_identity_guidance_preserves_the_actual_assignment(tmp_path):
    runner, store, _, run = setup_runner(tmp_path, count=1)
    cid = store.get_run(run)['candidates'][0]['candidate_id']
    attempt = store.reserve_attempt(run, cid, owner_session='parent')
    boot = json.loads(runner._bootstrap(run, attempt)['context'])
    name = boot['typed_source_templates_resource']
    assert name in attempt['required_resources']
    descriptor = boot['resources'][name]
    example = json.loads((store.run_dir(run) / 'resources' / descriptor['sha256']).read_text())[0]
    assert example['assigned_source_id'] == 'source:source:account:thread:t0'
    assert example['typed_source'] == {'type': 'source', 'source_key': 'source',
        'account_key': 'account', 'object_kind': 'thread', 'object_id': 't0'}
    assert 'message_id' in example['decisive_message_rule']
    assert 'Gmail' in example['decisive_message_rule']
    assert 'message_id' not in example['typed_source']  # no invented primary fact


def test_registered_callback_exposes_the_complete_child_payload_schema():
    js = pytest.importorskip('jsonschema')
    from alchemy_task.discovery_integration import SCHEMAS
    from alchemy_task.discovery_runner import BINDING_KEYS
    schema = SCHEMAS['discovery_research_submit']['parameters']
    js.Draft202012Validator.check_schema(schema)
    args = {'run_id': 'run', 'token': 'opaque',
            'binding': {k: 'revision' for k in BINDING_KEYS}, 'payload': bundle()}
    js.validate(args, schema)
    del args['payload']['workstreams'][0]['errors']
    with pytest.raises(js.ValidationError):
        js.validate(args, schema)
