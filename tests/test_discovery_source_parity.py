"""Concrete daily helper regressions, transformed to synthetic portable APIs.

No source checkout, private imports, runtime source execution or mocked research.
The adapter below supplies real lifecycle evidence/page reads around the old
record_bundle calls; the pure eligibility validator runs before any spool write.
"""
import json
import stat
from pathlib import Path
import pytest
from alchemy_task.core import discovery_research as m
from alchemy_task.core.discovery_identity import candidate_id, canonical_source_id
from alchemy_task.core.discovery_state import DiscoveryStore, read_json
from test_discovery_state import prepare, read_all
m.candidate_id = candidate_id
m.canonical_source_id = canonical_source_id
m.read_json = read_json


class SourceCaseStore(DiscoveryStore):
    def record_research_bundle(self, run, cid, payload):
        item=self.get_candidate(run,cid)
        if item['prefilter_disposition']=='excluded':raise m.UserError('prefilter-excluded')
        others={x['candidate_id']:x['source_ids'] for x in self.candidate_index(run) if x['candidate_id']!=cid and x['prefilter_disposition']=='research'}
        m.validate_bundle(payload,cid,item['source_ids'],other_sources=others)
        existing=self.accepted_bundle(run,cid)
        if existing:
            # Production immutable acceptance still checks saved payload equality.
            a=next(a for a in self.get_run(run)['attempts'].values() if a['candidate_id']==cid)
            receipt=self.spool_payload(run,a['token'],payload)
            return {'run_id':run,'candidate_id':cid,'workstream_ids':existing['workstream_ids']}
        self.freeze_index(run,rubric='Read authoritative sources then canonical tasks.')
        a=prepare(self,run,cid)
        receipt=self.spool_payload(run,a['token'],payload)
        self.observe_terminal(run,a['token'],state='SUCCEEDED',receipt={'state':'SUCCEEDED'})
        read_all(self,run,receipt['resource'],'parent')
        result=self.accept_attempt(run,a['token'],payload_sha256=receipt['payload_sha256'],assessment={'accepted':True,'reason':'Synthetic parent reviewed authoritative evidence'},reader='parent')
        return {'run_id':run,'candidate_id':cid,'workstream_ids':result['workstream_ids']}

    def status(self,run):return {'candidates':self.get_run(run)['candidates']}
    def _research_for(self,item):return self.research_for(item['run_id'],item['candidate_id'])


def setup_store(tmp_path):
    store=SourceCaseStore(tmp_path/'state')
    return store,store.init_run('run-1'),tmp_path/'workspace'

def source_slack(message="171.2"):
    return {
        "type": "slack",
        "workspace_id": "T1",
        "channel_id": "C1",
        "thread_root_ts": "171.1",
        "message_ts": message,
    }

def candidate(title="Follow up", message="171.2"):
    return {"title": title, "source_ids": [source_slack(message)]}

def research(cid, *, status="complete", disposition="retain"):
    return {
        "candidate_id": cid,
        "status": status,
        "disposition": disposition,
        "title": "Prepare launch follow-up",
        "current_understanding": "The launch needs a decision.",
        "substantive_next_action": "Choose the launch date.",
        "owner_and_collaborators": [{"name": "Example User", "role": "owner"}],
        "decisions_and_open_questions": {"decisions": [], "open_questions": ["Which date?"]},
        "dependencies_and_risks": ["Approval"],
        "implementation_context": ["Update the launch page after approval."],
        "execution_classification": "user_collaboration_or_approval",
        "exact_source_ids": [source_slack()],
        "related_source_ids": [],
        "source_links": ["https://workspace.example.test/archives/C1/p1712000000?thread_ts=171.1"],
        "related_context_links": [],
        "sources_consulted": [{"source": "Slack thread", "result": "complete"}],
        "sources_unavailable": [],
        "existing_task_candidates": [],
        "represented_candidate_ids": [],
        "new_information": ["Launch date is unresolved."],
        "errors": [],
    }

def research_bundle(cid, *messages):
    workstreams = []
    for index, message in enumerate(messages, 1):
        item = research(cid)
        item.pop("candidate_id")
        item["research_status"] = {
            "complete": "sufficient",
            "incomplete": "insufficient",
            "failed": "failed",
        }[item.pop("status")]
        item["title"] = f"Workstream {index}"
        item["exact_source_ids"] = [source_slack(message)]
        workstreams.append(item)
    return {"candidate_id": cid, "workstreams": workstreams}

def test_canonical_ids_are_stable_typed_and_deduplicated(tmp_path):
    store, run, _ = setup_store(tmp_path)
    a = candidate()
    b = {"title": "Same occurrence, different display title", "source_ids": [dict(reversed(list(source_slack().items())))]}
    added = store.add_candidates(run, [a, b])
    assert len(added) == 1
    assert added[0]["candidate_id"] == m.candidate_id([source_slack()])
    assert m.canonical_source_id({"type": "gmail", "account": "work", "thread_id": "17", "message_id": "2"}) == "gmail:work:17:2"
    assert m.canonical_source_id({"type": "slack", "team_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"}) == "slack:T1:C1:171.1"
    assert m.canonical_source_id({"type": "notion", "page_id": "AABBCCDD-EEFF-0011-2233-445566778899"}) == "notion:aabbccdd-eeff-0011-2233-445566778899"

def test_state_modes_and_atomic_write_cleanup(tmp_path):
    store, run, _ = setup_store(tmp_path)
    store.add_candidates(run, [candidate()])
    assert stat.S_IMODE(store.state_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((store.run_dir(run) / "ledger.json").stat().st_mode) == 0o600
    assert not list(store.state_root.rglob("*.tmp"))

def test_representation_targets_are_unique_nonexcluded_index_survivors(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent, excluded = store.add_candidates(run, [
        {"title": "Broad", "source_ids": [{"type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"}]},
        {**candidate("Resolved", "999.2"), "prefilter_disposition": "excluded", "prefilter_reason": "resolved"},
    ])
    payload = research_bundle(parent["candidate_id"], "171.2")
    payload["workstreams"][0]["represented_candidate_ids"] = [excluded["candidate_id"]]
    with pytest.raises(m.UserError, match="valid shared-index survivor"):
        store.record_research_bundle(run, parent["candidate_id"], payload)
    payload["workstreams"][0]["represented_candidate_ids"] = [excluded["candidate_id"], excluded["candidate_id"]]
    with pytest.raises(m.UserError, match="unique candidate IDs"):
        store.record_research_bundle(run, parent["candidate_id"], payload)

def test_bundle_normalizes_assigned_candidate_self_representation(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [{"title": "Broad", "source_ids": [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]}])[0]
    payload = research_bundle(parent["candidate_id"], "171.2")
    payload["workstreams"][0]["represented_candidate_ids"] = [parent["candidate_id"]]

    result = store.record_research_bundle(run, parent["candidate_id"], payload)

    saved = store._research_for(store.get_candidate(run, result["workstream_ids"][0]))
    assert saved["represented_candidate_ids"] == []

def test_occurrences_are_run_scoped_and_input_order_is_preserved(tmp_path):
    store, run1, _ = setup_store(tmp_path)
    same = candidate("same")
    first = store.add_candidates(run1, [candidate("later", "171.9"), same])
    run2 = store.init_run("run-0")
    second = store.add_candidates(run2, [same])
    assert [x["title"] for x in first] == ["later", "same"]
    assert first[1]["candidate_id"] == second[0]["candidate_id"]
    store.record_failure(run2, second[0]["candidate_id"], "research", "bounded failure")
    assert store.get_candidate(run1, first[1]["candidate_id"])["state"] == "proposed"
    assert store.get_candidate(run2, second[0]["candidate_id"])["state"] == "recoverable_failure"

def test_candidate_index_is_compact_complete_and_stable_for_every_child(tmp_path):
    store, run, _ = setup_store(tmp_path)
    items = store.add_candidates(run, [
        {**candidate("Recovery pricing", "171.2"), "summary": "private collector summary"},
        candidate("Minicart upsell", "171.3"),
    ])
    index = store.candidate_index(run)
    assert index == [{
        "candidate_id": item["candidate_id"],
        "title": item["title"],
        "source_ids": item["source_ids"],
        "prefilter_disposition": item["prefilter_disposition"],
    } for item in items]
    assert "private collector summary" not in json.dumps(index)

def test_research_bundle_materializes_independent_collision_safe_workstreams(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [{"title": "Broad DM", "source_ids": [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]}])[0]
    payload = research_bundle(parent["candidate_id"], "171.2", "171.9")
    result = store.record_research_bundle(run, parent["candidate_id"], payload)
    assert len(result["workstream_ids"]) == 2
    assert len(set(result["workstream_ids"])) == 2
    candidates = store.status(run)["candidates"]
    assert candidates[0]["decomposition_state"] == "complete"
    workstreams = candidates[1:]
    assert [item["parent_candidate_id"] for item in workstreams] == [parent["candidate_id"]] * 2
    assert [item["source_ids"][0].rsplit(":", 1)[-1] for item in workstreams] == ["171.2", "171.9"]
    assert store.record_research_bundle(run, parent["candidate_id"], payload) == result

def test_bundle_rejects_prefilter_excluded_parent_without_writes(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [{
        "title": "Resolved thread",
        "source_ids": [{"type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"}],
        "prefilter_disposition": "excluded",
        "prefilter_reason": "resolved",
    }])[0]
    before = json.dumps(store.get_run(run)["candidates"]).encode()
    with pytest.raises(m.UserError, match="excluded"):
        store.record_research_bundle(run, parent["candidate_id"], research_bundle(parent["candidate_id"], "171.2"))
    assert json.dumps(store.get_run(run)["candidates"]).encode() == before
    assert not (store.run_dir(run) / "research" / f"{parent['candidate_id']}.bundle.json").exists()

def test_bundle_rejects_overlapping_decisive_identity_sets(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [{"title": "Broad DM", "source_ids": [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]}])[0]
    payload = research_bundle(parent["candidate_id"], "171.2", "171.9")
    payload["workstreams"][0]["exact_source_ids"].append(source_slack("171.9"))
    with pytest.raises(m.UserError, match="overlapping workstream"):
        store.record_research_bundle(run, parent["candidate_id"], payload)

def test_workstream_hash_collision_fails_before_overwriting_research(tmp_path, monkeypatch):
    store, run, _ = setup_store(tmp_path)
    first, second = store.add_candidates(run, [
        {"title": "First", "source_ids": [{"type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"}]},
        {"title": "Second", "source_ids": [{"type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "999.1"}]},
    ])
    monkeypatch.setattr(m, "workstream_id", lambda parent, sources: "w_forcedcollision")
    store.record_research_bundle(run, first["candidate_id"], research_bundle(first["candidate_id"], "171.2"))
    research_path = store.run_dir(run) / "research" / "w_forcedcollision.json"
    before = research_path.read_bytes()
    second_payload = research_bundle(second["candidate_id"], "999.2")
    second_payload["workstreams"][0]["exact_source_ids"] = [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "999.1", "message_ts": "999.2"
    }]
    with pytest.raises(m.UserError, match="collision"):
        store.record_research_bundle(run, second["candidate_id"], second_payload)
    assert research_path.read_bytes() == before

def test_bundle_cannot_absorb_identity_represented_by_another_candidate(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent, other = store.add_candidates(run, [
        {"title": "Broad DM", "source_ids": [{"type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"}]},
        candidate("Minicart upsell", "171.9"),
    ])
    payload = research_bundle(parent["candidate_id"], "171.2", "171.9")
    payload["workstreams"][0]["represented_candidate_ids"] = [other["candidate_id"]]
    with pytest.raises(m.UserError, match="represented by another candidate"):
        store.record_research_bundle(run, parent["candidate_id"], payload)

def test_bundle_rejects_cross_thread_sources_and_ambiguous_multi_unit_identity(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [{"title": "Broad DM", "source_ids": [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]}])[0]
    crossed = research_bundle(parent["candidate_id"], "171.2")
    crossed["workstreams"][0]["exact_source_ids"].append({
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "999.1", "message_ts": "999.2"
    })
    with pytest.raises(m.UserError, match="outside assigned thread"):
        store.record_research_bundle(run, parent["candidate_id"], crossed)

    ambiguous = research_bundle(parent["candidate_id"], "171.2", "171.9")
    ambiguous["workstreams"][0]["exact_source_ids"] = [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]
    with pytest.raises(m.UserError, match="decisive message"):
        store.record_research_bundle(run, parent["candidate_id"], ambiguous)

def test_bundle_keeps_related_typed_identity_out_of_decisive_identity_boundary(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [{"title": "Welcome Pack", "source_ids": [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]}])[0]
    notion = {"type": "notion", "page_id": "00000000-0000-0000-0000-000000000001"}
    payload = research_bundle(parent["candidate_id"], "171.2")
    payload["workstreams"][0]["related_source_ids"] = [notion]

    recorded = store.record_research_bundle(run, parent["candidate_id"], payload)
    wid = recorded["workstream_ids"][0]
    saved = json.loads((store.run_dir(run) / "research" / f"{wid}.json").read_text())
    assert saved["related_source_ids"] == [notion]
    assert store.get_candidate(run, wid)["source_ids"] == ["slack:T1:C1:171.1:171.2"]

    other_run = store.init_run("related-in-exact")
    other_parent = store.add_candidates(other_run, [{"title": "Welcome Pack", "source_ids": [{
        "type": "slack", "workspace_id": "T1", "channel_id": "C1", "thread_root_ts": "171.1"
    }]}])[0]
    invalid = research_bundle(other_parent["candidate_id"], "171.2")
    invalid["workstreams"][0]["exact_source_ids"].append(notion)
    with pytest.raises(m.UserError, match="outside assigned thread"):
        store.record_research_bundle(other_run, other_parent["candidate_id"], invalid)

def notion_source(index):
    return {"type": "notion", "page_id": f"{index:032x}"}

def test_source_identity_target_is_12_but_validator_allows_through_15(tmp_path):
    assert m.REQUESTED_SOURCE_IDS == 12
    assert m.MAX_SOURCE_IDS == 15
    schema = json.loads(
        (Path(__file__).parents[1] / "schemas" / "discovery-child-output.schema.json").read_text()
    )["$defs"]["workstream"]["properties"]
    assert schema["exact_source_ids"]["maxItems"] == 15
    assert schema["related_source_ids"]["maxItems"] == 15

    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [candidate("Many linked sources")])[0]
    payload = research_bundle(parent["candidate_id"], "171.2")
    payload["workstreams"][0]["related_source_ids"] = [notion_source(i) for i in range(1, 15)]

    recorded = store.record_research_bundle(run, parent["candidate_id"], payload)
    assert len(recorded["workstream_ids"]) == 1

def test_related_and_exact_source_ids_reject_total_over_15(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [candidate("Over hard ceiling")])[0]
    payload = research_bundle(parent["candidate_id"], "171.2")
    payload["workstreams"][0]["related_source_ids"] = [notion_source(i) for i in range(1, 16)]

    with pytest.raises(m.UserError, match="source identity count"):
        store.record_research_bundle(run, parent["candidate_id"], payload)

def test_bundle_rejects_noncomplete_workstream_before_materializing(tmp_path):
    store, run, _ = setup_store(tmp_path)
    parent = store.add_candidates(run, [candidate()])[0]
    payload = research_bundle(parent["candidate_id"], "171.2")
    payload["workstreams"][0]["research_status"] = "insufficient"
    payload["workstreams"][0]["disposition"] = "retain"

    with pytest.raises(m.UserError, match="delivery-ineligible research_status requires a fresh research retry"):
        store.record_research_bundle(run, parent["candidate_id"], payload)

    assert not (store.run_dir(run) / "research" / f"{parent['candidate_id']}.bundle.json").exists()
    assert store.get_candidate(run, parent["candidate_id"]).get("decomposition_state") is None
    assert all(
        not item.get("parent_candidate_id")
        for item in store.get_run(run)["candidates"]
    )
