from __future__ import annotations
import re
import pytest
from alchemy_task.core.discovery_dossiers import DossierError, content_revision, render_discovery_dossier, render_generic_dossier, upsert_managed_block

def generic_research(**overrides):
    payload = {
        "recommended_approach": ["Reuse the existing targeted sync."],
        "useful_context": ["The task already has a canonical vault note."],
        "dependencies_and_risks": ["Google notes may be truncated at 8,192 characters."],
        "open_questions": [],
        "sources": [
            {
                "title": "Google Tasks API",
                "url": "https://developers.google.com/tasks/reference/rest/v1/tasks",
                "relevance": "Documents the external task surface.",
            }
        ],
    }
    payload.update(overrides)
    return payload

def test_render_generic_dossier_is_stable_and_omits_empty_sections():
    revision, block = render_generic_dossier(generic_research())

    assert re.fullmatch(r"sha256:[0-9a-f]{64}", revision)
    assert block.startswith("<!-- task-research-dossier:start -->\n## Research dossier")
    assert f"**Content revision:** `{revision}`" in block
    assert "### Recommended approach" in block
    assert "### Useful context" in block
    assert "### Dependencies and risks" in block
    assert "### Open questions" not in block
    assert "[Google Tasks API](https://developers.google.com/tasks/reference/rest/v1/tasks)" in block
    assert block.endswith("<!-- task-research-dossier:end -->")
    assert render_generic_dossier(generic_research()) == (revision, block)

def test_content_revision_ignores_dictionary_insertion_order():
    left = {"a": [1, 2], "b": {"x": "y"}}
    right = {"b": {"x": "y"}, "a": [1, 2]}
    assert content_revision(left) == content_revision(right)

def test_upsert_appends_at_end_and_preserves_existing_bytes():
    body = "## Notes\n\nUser-authored notes.\n"
    _, block = render_generic_dossier(generic_research())

    updated, changed = upsert_managed_block(
        body,
        start_marker="<!-- task-research-dossier:start -->",
        end_marker="<!-- task-research-dossier:end -->",
        block=block,
    )

    assert changed is True
    assert updated.startswith(body.rstrip())
    assert updated == body.rstrip() + "\n\n" + block + "\n"

def test_upsert_replaces_only_managed_bytes_and_second_run_is_noop():
    _, first = render_generic_dossier(generic_research())
    _, second = render_generic_dossier(
        generic_research(recommended_approach=["Use the shared dossier helper."])
    )
    body = f"Prefix byte-for-byte.\n\n{first}\n\nSuffix byte-for-byte.\n"

    updated, changed = upsert_managed_block(
        body,
        start_marker="<!-- task-research-dossier:start -->",
        end_marker="<!-- task-research-dossier:end -->",
        block=second,
    )

    assert changed is True
    assert updated == f"Prefix byte-for-byte.\n\n{second}\n\nSuffix byte-for-byte.\n"
    unchanged, changed_again = upsert_managed_block(
        updated,
        start_marker="<!-- task-research-dossier:start -->",
        end_marker="<!-- task-research-dossier:end -->",
        block=second,
    )
    assert changed_again is False
    assert unchanged == updated

@pytest.mark.parametrize(
    "body",
    [
        "<!-- task-research-dossier:start -->\nmissing end\n",
        "<!-- task-research-dossier:end -->\nmissing start\n",
        "<!-- task-research-dossier:start -->\na\n<!-- task-research-dossier:start -->\nb\n<!-- task-research-dossier:end -->\n",
    ],
)
def test_upsert_rejects_malformed_or_duplicate_markers(body):
    _, block = render_generic_dossier(generic_research())
    with pytest.raises(DossierError, match="markers"):
        upsert_managed_block(
            body,
            start_marker="<!-- task-research-dossier:start -->",
            end_marker="<!-- task-research-dossier:end -->",
            block=block,
        )

def test_render_generic_dossier_rejects_unknown_fields_and_preserves_contextual_urls():
    with pytest.raises(DossierError, match="fields"):
        render_generic_dossier(generic_research(extra=[]))
    _, block = render_generic_dossier(
        generic_research(
            sources=[
                {
                    "title": "Contextual source",
                    "url": "https://example.com/?token=context-value",
                    "relevance": "Preserve the exact useful source link.",
                }
            ]
        )
    )
    assert "https://example.com/?token=context-value" in block

def test_render_discovery_dossier_preserves_existing_inline_format():
    research = {
        "candidate_id": "c_abc",
        "status": "complete",
        "disposition": "retain",
        "title": "Prepare launch follow-up",
        "current_understanding": "The launch needs a decision.",
        "substantive_next_action": "Choose the launch date.",
        "owner_and_collaborators": [{"name": "Example User", "role": "owner"}],
        "decisions_and_open_questions": {
            "decisions": [],
            "open_questions": ["Which date?"],
        },
        "dependencies_and_risks": ["Approval"],
        "implementation_context": ["Update the launch page after approval."],
        "execution_classification": "user_collaboration_or_approval",
        "exact_source_ids": ["slack:T1:C1:171.1:171.2"],
        "related_source_ids": [],
        "source_links": ["https://example.com/source"],
        "related_context_links": [],
        "sources_consulted": [{"source": "Slack thread", "result": "complete"}],
        "sources_unavailable": [],
        "existing_task_candidates": [],
        "new_information": ["Launch date is unresolved."],
        "errors": [],
        "represented_candidate_ids": [],
    }

    revision, block = render_discovery_dossier(
        research,
        dossier_id="dos-abc",
        candidate_source_ids=["slack:T1:C1:171.1:171.2"],
    )

    assert f"**Content revision:** `{revision}`" in block
    assert "<!-- discovery-dossier:start dos-abc -->" in block
    assert "### Next Action\n\nChoose the launch date." in block
    assert "- Example User - owner" in block
    assert "- Slack thread - complete" in block
    assert block.endswith("<!-- discovery-dossier:end dos-abc -->")

@pytest.mark.parametrize('body', ['<!-- x:end --> text <!-- x:start -->', '<!-- x:start --><!-- x:end --><!-- x:start --><!-- x:end -->'])
def test_reversed_or_duplicate_pairs_fail_closed(body):
    with pytest.raises(DossierError, match='markers'):
        upsert_managed_block(body, start_marker='<!-- x:start -->', end_marker='<!-- x:end -->', block='<!-- x:start -->new<!-- x:end -->')


def test_multiple_dossiers_and_related_evidence_are_separate():
    from test_discovery_schema import bundle
    research=bundle()['workstreams'][0]
    research['related_source_ids']=[{'type':'gmail','account':'work','thread_id':'related'}]
    research['related_context_links']=['https://example.test/related']
    body='## Notes\n\nKeep exact bytes.\n'
    for dossier_id in ['one','two']:
        revision,block=render_discovery_dossier(research,dossier_id=dossier_id,candidate_source_ids=['slack:T1:C1:171.1:171.2'])
        body,changed=upsert_managed_block(body,start_marker=f'<!-- discovery-dossier:start {dossier_id} -->',end_marker=f'<!-- discovery-dossier:end {dossier_id} -->',block=block)
        assert changed
    assert body.count('## Research Dossier')==2
    assert '### Decisive Source Identities' in body
    assert '### Related Source Identities' in body
    assert 'gmail:work:related' in body
    with pytest.raises(DossierError):
        render_discovery_dossier(research,dossier_id='invalid -->',candidate_source_ids=[])
