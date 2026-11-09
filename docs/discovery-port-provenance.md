# Discovery core port provenance

## Pre-implementation source QA

This phase adapts the authorized daily helper, dossier library and synthetic regression cases from source revision `5e69620137a585664c151813284937faa4ee79f6`. It does not copy the credential collectors, private prompts, production paths, task mutation code or scheduler. The destination repository is MIT licensed. Extraction is user-authorized; no third-party licensing assertion is inferred for private operational material.

Inspected algorithm inputs (SHA-256):

- Deterministic helper: `d9f80d57eb09a24d081aa9ae93ae3e060fc3c0eceee7df36fabf782424c9890f`.
- Dossier library: `ef63031d29c76900da3d5fb0d47fded844ea0bba250dd2e389e068622c7a3019`.
- Child schema: `3ef20cd8db820381801f6a072f359b34380eda5d806f8b584206ce447a1592b8`.
- Helper regression suite: `1be3c582d798e488ba7ea0fb0db7622a7b0e771c98aeb4a2a7a53a70baca8a86`.
- Dossier regression suite: `65e08b6b997189b167f53f130edca4cb6450df3d18ee9b82c39817ef99c7cf07`.

### Necessary local design adjustments

1. The revised public lifecycle route controls. Store one reserved ordinal per actual launch intent, never reserve two speculative native attempts. Unknown admission is fenced, retains its ordinal and cannot retry automatically. Full spool and terminal execution evidence are distinct from semantic acceptance.
2. Source helper components trim whitespace and its Notion normalizer removes arbitrary hyphens. The portable strict boundary rejects whitespace and malformed UUID spelling before normalization. Preserve source timestamps verbatim. URL extraction requires explicit provider/account mapping; do not infer a workspace from a host label or trim timestamp zeros.
3. The source bundle algorithm assumes every unit covers every assigned primary identity and rejects overlapping decisive sources. Preserve assignment coverage and legacy overlap rejection, extending only explicitly verified same-message independent anchors. A frozen parent-issued registry, not child labels or array positions, supplies action IDs.
4. The source schema lacks the combined exact-plus-related bound and safe-component patterns present in helper validation. Add schema constraints for the combined bound and use a dependency-free interpreter of the actual schema keywords at runtime. Retain all 20 child fields and required nested fields. Parent self-representation remains a sanctioned normalization, not a missing-field repair.
5. The source Store writes unit files before its bundle marker. Add durable validated commit intent and deterministic replay. This is recoverable per-file materialization, not a cross-file transaction. Only committed markers expose accepted bundles.
6. The source helper caps an entire run at 200 and 256 KiB. The portable store retains an unlimited ordered source backlog and freezes explicit bounded cohorts, plus a full-run manifest. Daily research budget is separate from cohort and two-attempt limits.
7. Resource paging is lossless UTF-8, revision-bound and hashed. Persist complete page receipts for each reader. Parent full-payload retrieval is a prerequisite for semantic acceptance; retrieval is not proof of understanding. Chunked upload preserves the 512-KiB limit and uses the same spool path as direct submission.
8. Dossier rendering keeps every source synthesis section, adds decisive versus related evidence sections and neutral per-ID markers. Generic research markers remain unchanged. Reject reversed/duplicate markers, including malformed supplied replacement blocks, instead of leaking a bare index exception.
9. This phase supplies storage primitives for review, coverage, supervisor leases and lifecycle bindings, not task writes, stream entrypoints, model dispatch, semantic decisions, Git or digest delivery. Later coordinators must verify actual caller identity and terminal evidence before invoking acceptance.

Public transformations replace private person, organization, domain, path and account references with synthetic data. Source-dependent runtime imports are forbidden. Pure algorithms are imported only from adjacent portable core modules.

## Verification and API handoff

Implementation results and concrete exported signatures are recorded below when exercised. Source regression counts are not full workflow or Cloud acceptance.

## Source function correspondence

| Portable module | Source algorithms retained | Deliberate transformations |
| --- | --- | --- |
| `discovery_identity` | `_component`, `_notion`, `canonical_source_id`, `source_identity_covers`, `candidate_id`, `workstream_id`; boundary-delimited provenance and URL extraction | Reject malformed spelling instead of repair; explicit Slack host mapping; generic scoped provider identity; frozen same-message action anchors extend, not replace, legacy hashes. |
| `discovery_research` | `_str`, `_strings`, `_privacy_walk`, `validate_research`, validation half of `Store._record_research_bundle_locked` | Pure whole-bundle validation, exact checked-in schema interpreter, tolerant JSON extraction, separate shape/helper decisions, optional parent-verified action registry. No task or host imports. |
| `discovery_state` | `_json_bytes`, `atomic_write`, `atomic_json`, `read_json`, `file_fingerprint`, Store candidate normalization/index projection/run locks/failure records/immutable bundle materialization/pruning | Explicit profile root, UUID runs, one atomic mutable run ledger, durable source backlog, bounded cohorts, immutable resources, attempt/spool/acceptance intents and recoverable markers, retained review tombstones. |
| `discovery_dossiers` | `content_revision`, generic validation/rendering, inline discovery rendering, `upsert_managed_block` | Neutral per-ID discovery markers, explicit decisive/related identity sections, malformed/reversed marker refusal. Existing generic markers unchanged. |
| child schema | Complete original 20-field workstream contract, nested requirements, types, enums, bounds and identity variants | Neutral collaboration enum, generic source variant, optional all-or-none action fields, combined 15-identity bound, configured-workspace-relative nomination syntax. |

The concrete source regressions in `test_discovery_source_parity.py` preserve sixteen helper cases: canonical/deduplicated identities, private state modes, representation survivor checks, self-representation compatibility, run-scoped occurrences/order, complete compact shared index, independent collision-safe units, excluded-parent refusal, overlapping identities, hash collision, competing candidate representation, cross-thread/ambiguous decomposition refusal, related-versus-decisive boundary, 12-target/15-ceiling compatibility, combined-15 refusal and whole-bundle insufficient refusal. Their fixtures are synthetic. A test-only adapter surrounds the original record-bundle assertions with real portable attempt, resource-read, spool, terminal and parent-acceptance calls; it does not mock validation or execute private source code.

`test_discovery_dossiers.py` additionally adapts every source dossier test, including the original three malformed-marker parameter cases, and adds multiple-ID/related-evidence/reversed-marker cases. The rest of the historical 194-case baseline covers collectors, matching, task mutation, conversion, prompt and delivery contracts outside this phase. It has not been relabeled as 194 portable passes.

## Exported contracts for the next coordinator

All modules import locally and require only the standard library. `UserError` is the shared bounded-input/transition error. The existing plugin files are unchanged.

### Pure identities and validation

```python
canonical_source_id(source) -> str
source_identity_covers(assigned, reported) -> bool
candidate_id(source_ids) -> str
workstream_id(parent_candidate_id, source_ids, *, action_id=None) -> str
freeze_actions(parent_id, source_ids, anchors, *, existing=None) -> list[dict]
extract_identities(value, *, slack_workspaces=None) -> set[str]
url_identities(text, *, slack_workspaces=None) -> set[str]
child_schema() -> dict
extract_json(text_or_object) -> dict
validate_shape(payload) -> dict
validate_research(payload, cid, expected_sources) -> dict
validate_bundle(bundle, cid, expected_sources, *, other_sources=None,
                action_registry=None) -> list[tuple[str, dict, list[str]]]
```

`validate_bundle` returns helper-issued workstream ID, normalized complete research and decisive canonical IDs. It performs no writes. A single insufficient/failed/invalid unit rejects the entire candidate bundle. The registry is supplied only after parent verification, never directly trusted from a child. Anchor keys are `locator` and `outcome`; supported locator prefixes are message/bullet/section/paragraph/line/item. Duplicate keys/outcomes and legacy decisive overlap fail. Same-message overlap requires distinct frozen independent actions. Anchor changes require explicit parent reconciliation, not a title or position-based re-key. Related evidence never changes the hash or covers assignments. The shape interpreter evaluates only the vocabulary used in the checked-in schema and fails closed on unknown keywords; JSON Schema is a test oracle, not a runtime dependency.

### Store lifecycle and full spool

Construct `DiscoveryStore(profile_data_dir / 'discovery')`. No default-profile paths are inferred.

```python
init_run(run_id=None, *, stream='default', business_date='', config=None,
         schema_revision=None, origin=None, lineage=None) -> str
add_candidates(run_id, supplied_items) -> list[dict]
freeze_index(run_id, *, rubric) -> dict
candidate_index(run_id, cohort=None) -> list[dict]
get_run(run_id) -> dict
get_candidate(run_id, cid) -> dict
claim_lease(run_id, *, owner, expires_at) -> dict
release_lease(run_id, *, owner) -> None
reserve_attempt(run_id, cid, *, owner_session, daily_limit=50) -> dict
record_start(run_id, *, parent_session, child_session, subagent_id) -> None
bind_attempt(run_id, token, handle, *, owner_session) -> dict
authorize_attempt(run_id, token, *, child_session, subagent_id=None) -> dict
mark_running(run_id, token, *, started_at, deadline_utc) -> dict
fence_attempt(run_id, token, *, reason, cancellation=None) -> dict
observe_terminal(run_id, token, *, state, receipt) -> dict
reject_attempt(run_id, token, *, reason, retryable, semantic=False) -> dict
recover_owner(run_id, *, owner_session, owner_restarted=False) -> list[str]
get_attempt(run_id, token) -> dict
quarantine(run_id, token, *, caller, payload) -> dict
spool_payload(run_id, token, payload) -> dict
begin_upload(run_id, token, *, total_bytes, sha256, part_count) -> dict
upload_part(run_id, token, *, index, content) -> dict
commit_upload(run_id, token) -> dict
recover_spools(run_id) -> list[dict]
freeze_action_registry(run_id, cid, anchors) -> list[dict]
accept_attempt(run_id, token, *, payload_sha256, assessment, reader) -> dict
recover_bundles(run_id) -> list[dict]
accepted_bundle(run_id, cid) -> dict | None
research_for(run_id, wid) -> dict
```

The coordinator must pass the frozen local business date, approved source/account configuration, actual parent identity, origin and source revisions. Defaults exist for isolated pure tests, not as a timezone or source-setup policy. A supervisor lease owner must be a unique invocation ID, not a shared parent session ID. It is distinct from an attempt's actual `owner_session`. Claim/release around an active-handler invocation and enforce the revised rolling-three admission/drain mechanics outside ledger locks.

One `reserve_attempt` commits one fresh ordinal and charges one run/candidate daily unit idempotently. A retry consumes the same daily unit and at most ordinal two. Unknown, active, held or accepted research cannot auto-reserve another child. Budget charging is a separate monotone file committed before the attempt: an interruption in between can conservatively retain the daily charge, never refund an uncertain launch or permit a third child. Resume the same run rather than minting another run for retry. Source backlog replay is handled separately from new research occurrences.

The start hook and returned handle can arrive in either order. Exact subagent ID joins the actual parent/child session observation. `authorize_attempt` takes observed caller metadata, not model-supplied identity. Early callbacks can be quarantined; no automatic guessed association or acceptance occurs. Only the future tool wrapper authenticates callers, revision envelopes and allowed resource names. The Python store methods are trusted internal APIs, not registered tools or an authorization boundary.

`mark_running` persists the execution deadline supplied from the actual observed RUNNING event. The coordinator retains its in-process monotonic timer and manages PENDING/admission separately. Read/submit paths reject expired live attempts; fences retain late/unknown audit. `observe_terminal` records actual terminal evidence, not a clipped summary as research. A confirmed terminal timeout may be rejected into its remaining fresh ordinal while its old capability stays fenced. Accepted or rejected facts cannot be changed by repeating a binding or submitting a rewritten payload.

`spool_payload` returns only a small receipt containing canonical payload hash, transport hash, parsed flag, resource name and exact bytes. It saves the full owner-only structured bundle plus original text transport, including malformed text as ineligible audit evidence. Same-token changed bytes conflict; identical already-committed payload returns its receipt without reopening a fence. The 512-KiB bound applies independently of lifecycle summary length. Multipart declarations use exact UTF-8 byte count and SHA-256; parts are zero-indexed, at most 16 KiB each, immutable and contiguous at commit, at most 1024 parts. Commit uses the same spool acceptance path. Incomplete uploads do not become research.

Spool receipt commits bridge a crash before ledger checkpoint. `recover_spools` reconstructs saved callback evidence and validates hashes without inventing terminal success. `accept_attempt` requires actual successful terminal evidence, the exact saved payload hash, full parent payload-page receipts and an assessment with `accepted=True` and a nonempty bounded reason. Parent semantic checklist substance remains model judgment in the future coordinator. The full bundle is revalidated before a durable immutable acceptance intent is written. `recover_bundles` replays partial unit/ledger/marker writes and verifies committed units; repeated completed recovery does not rewrite bytes. Only a completed bundle marker exposes `research_for` to downstream task logic.

### Immutable paging, source backlog and review storage

```python
put_resource(run_id, name, content) -> dict
resource_info(run_id, name) -> dict
fetch_resource(run_id, name, *, revision, reader, cursor=None, limit=8192) -> dict
source_state(stream, source) -> dict
enqueue_backlog(stream, source, entries) -> dict
update_backlog(stream, source, backlog_id, *, status, lineage) -> dict
record_coverage(stream, source, receipt) -> dict
record_failure(run_id, cid, operation, reason, *, attempt_count=None,
               failure_category='unknown') -> dict
save_review(run_id, review) -> dict
prune(*, days=60) -> dict
```

Resources use exact UTF-8 bytes, lossless string splitting, full/page hashes, exact totals and revision/reader-bound cursors. Default content limit is 8 KiB and maximum is 16 KiB. Reader names are safe opaque ledger keys; the coordinator maps actual caller sessions to them. All required per-attempt index/schema/rubric/assignment/manifest/outcome pages must be fetched before a new spool commit. Parent full payload reads are checked separately. Page receipts prove retrieval only. Cohorts preserve 200-parent/256-KiB bounds; the full-run manifest and immutable successive outcome projections expose all cohorts without truncating 201 or more candidates. An attempt freezes its outcome revision, while subsequent attempts see newly accepted action representations. Cross-cohort semantic reconciliation still belongs to the parent.

Backlog is ordered, durable and keyed by complete source identities plus source revision. Updating a terminal lineage cannot silently requeue old activity; new activity needs a new revision. Coverage is independent of research selection/budget. Attested or partial receipts cannot advance watermarks. A complete adapter-verified exhausted receipt additionally requires durable backlog identity references. The future source adapter owns account/window/contiguous-interval/exhaustiveness verification; the storage method does not manufacture those facts from a boolean.

Reviews are immutable caller-built projections; the future coordinator must enforce full join and finalization semantics before saving them. Repeats are no-ops. Errors and unresolved research/backlog are retained. Pruning removes only age-eligible resolved artifacts, retaining readable run/review tombstones and refusing to reuse old run IDs. Task conversion and delivery completion must be populated by the later coordinator; this phase does not invent them.

### Dossier rendering

```python
content_revision(value) -> str
render_generic_dossier(payload) -> tuple[str, str]
render_discovery_dossier(research, *, dossier_id,
                         candidate_source_ids) -> tuple[str, str]
upsert_managed_block(body, *, start_marker, end_marker, block) -> tuple[str, bool]
```

Render from the accepted saved normalized research, not the lifecycle summary. Generic markers are `task-research-dossier:start/end`; neutral discovery markers are `discovery-dossier:start/end <id>`. Call upsert independently for each stable dossier ID. These functions return strings only and never write a task.

## Executed verification

The red/green slices were executed against missing portable modules first, then against concrete malformed-type, timeout/review, binding-regression, crash-recovery, spool and lease/backlog failures before their corrections. The full existing plus new suite was exercised with the managed interpreter and the already-installed development test packages. The runtime-only venv additionally exercises all portable checks without `jsonschema`; only the two optional schema-oracle tests skip there.

Final command results and exact implementation revision are supplied in the phase handoff. No lifecycle dispatch, source collector, task conversion, Git delivery, digest or Cloud runtime parity is claimed by these core tests. Those remain integration and release acceptance work, with independent contextual review owned by the parent.
