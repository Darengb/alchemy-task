# Discovery backend contract

## Status and scope

This is a local integration checkpoint, not a full-parity or deployment claim. It registers the source/context/lifecycle/matching/review/conversion backend and preserves the existing stream setup surface. UI is separate. Real provider bindings, positive model-driven local/Cloud acceptance and the remaining limitations below must be closed before release.

The installing profile owns all mutable discovery state under its plugin data directory. No bundled credentials, private collectors, cross-profile lookup, source mutation or new runtime dependency is introduced. Broad inherited source tools are procedurally read-only, not a mechanical sandbox. Registered task/integration entrypoints additionally refuse verified discovery-child writes.

## Registered tools

All handlers consume host `session_id`/`task_id` kwargs, never model-provided caller identity. New tools return `{ok,result}` or `{ok:false,error}`. Existing `discovery_start`, `discovery_submit`, `discovery_decide` retain the plugin's top-level receipt convention.

| Tool | Required inputs and effect |
| --- | --- |
| `discovery_stream` | Existing list/create/update/remove/run_now UX, origin chat, schedule, areas, source scopes and optional actual reader `toolsets`. |
| `discovery_config` | `action=source`, stream, config, user_approved; `action=identity`, account_key, explicit identity, user_approved; `action=delivery`, stream, binding, user_approved; or status. Never accepts credentials. |
| `discovery_start` | stream; creates or resumes the same pending saved run/config/business date/window for its verified parent. Missing setup blocks. |
| `discovery_collect` | run_id, source_key; executes the approved configured reader, or records an explicitly partial envelope. Optional max_pages bounds one pass, never proves exhaustion. |
| `discovery_context` | run_id, optional approved context; freezes collected candidates, full all-status task bodies, complete installed-skill inventory/content, installing-profile SOUL/memory files, full discovery rubric and source/config context. |
| `discovery_research_run` | run_id, optional expected_revision; bounded public lifecycle FIFO. Requires operator-installed supported timeout evidence, not a fabricated native delegation field. |
| `discovery_research_fetch` | run_id, resource, revision, optional cursor/limit; child adds token/binding. Full lossless pages and durable page receipts. |
| `discovery_research_submit` | run_id, token, binding, payload OR multipart upload action begin/part/commit. Intermediate parts explicitly continue; full commit says stop. |
| `discovery_research_accept` | run_id, token, payload_sha256, assessment with accepted/reason and textual observations for all exported CHECKLIST fields. Full parent payload reads required. |
| `discovery_actions` | run_id, cid, verified locator/outcome anchors for independent asks sharing source identities. |
| `discovery_reconcile` | run_id, cid, current accepted-outcome-bound decision/reason/accepted_unit_ids. |
| `discovery_join` | run_id, optional explicit degraded reasons; full selected-run barrier, never a live-attempt success. |
| `discovery_recover` | run_id, optional owner_restarted/adopt. Reconnect/fence unknown evidence without refund; new-owner adoption still needs an integration authorizer. |
| `discovery_release_hold` | run_id, explicit reason; deliberate release, not uncertain-attempt refund. |
| `discovery_match` | run_id, unit_id; post-join exact matching over all-status current full task files; complete target-body resources and ALL nominated semantic options. |
| `discovery_decision` | run_id, unit_id, decision=propose/auto/noop/conflict, substantive reason; auto/noop use exact target_task_id and expected_revision. Auto additionally requires parent useful_delta=true. |
| `discovery_digest` | run_id, action=prepare/get/delivery/send. Preparation freezes numbering/review. send requires approved origin sender plus exact-message readback mapping. |
| `discovery_submit` | Compatibility alias requiring saved run_id and completed research/join/decisions. Freeform candidates/research_notes are rejected, not silently imported. |
| `discovery_decide` | approve/dismiss references, optional day/stream and per-reference edits. Semantic items require choice=update/create; multiple options require target_task_id. No title resolution. |
| `discovery_conversion_recover` | run_id, unit_id; exact already-prepared conversion only, no new plan or blind re-creation. |
| `discovery_runs` | Optional run_id; exact origin-authorized record or list of full backend records. |

`plugin.yaml` declares every tool. `__init__.py` registers the factory handlers and actual subagent_start/pre_tool_call/pre_llm_call hooks. The existing reply hint remains separate from saved-run continuation. Hooks do not schedule a model turn.

## Source/config contract

A source config contains `source_key`, `name` matching an approved stream source, `account_key`, exact `scope`, `read_method`, and `relevance={rules,identity_requirements}`. Required identity fields are explicit name/aliases/user_id, not a universal personal-name gate. Confirmations are persisted per account in profile-local plugin state; no email-local-part inference. Source/account keys are typed validated tokens, not repaired identifiers.

A generic structured binding contains:

```json
{
  "tool": "approved_existing_reader",
  "arguments": {},
  "request_fields": {"account": "account_key", "scope": "scope", "start": "start", "end": "end", "cursor": "cursor"},
  "response_fields": {"account_key": "account", "scope": "scope", "start": "window.start", "end": "window.end", "items": "items", "next_cursor": "pagination.next", "pagination_exhausted": "pagination.exhausted"}
}
```

Response paths select ACTUAL returned values. They do not echo requested account/window into evidence. Items must already expose normalized complete typed source_ids, source_revision and title. Missing/unsupported mappings, prose returns, account/scope/window mismatch, missing pagination and truncation remain failed/partial. Agent attestation never advances a watermark. All page items enter durable backlog before coverage. Selected/accepted/excluded/deferred/blocked lineage is separate from coverage and daily research budget. An exhausted/unknown research failure remains blocked, not silently given a third attempt by a new scan.

Installed profile SOUL.md and memories/MEMORY.md/USER.md are snapshotted only when present and contained within that profile. Broader approved document/capability context is supplied by the parent from its available tools. This is not a claim of complete hosted connector discovery or a credential inventory.

## Matching and immutable conversion

`DiscoveryConversion(rt,store)` exports `joined`, `match`, `prepare`, `apply`, `deliver_git`. Trusted Python methods are not an independent authorization boundary. Public mutation authority stays in the registered parent decision/immutable proposal paths.

Matching adapts the established helper's directional typed identity and decomposed broad-thread nomination guard. Complete decisive-message equality needs no nomination. Related-only dossier sections do not grant exact identity. One exact target plus verified useful delta permits auto enrichment; no delta is byte-preserving noop; semantic targets require choice; several exact targets conflict without mutation. Completed tasks are included. No title-similarity suppression.

Preparation persists UUID/path, exact accepted research revision, expected preimage and WHOLE postimage before writing a task. New and update conversions promote the exact accepted dossier immediately. Existing YAML comments/user metadata/sections/dossiers remain; no generic research is launched. Ordinary task_create/research behavior is unchanged. The selected approval batch is prepared before its first task write, so an invalid second date/area causes no task writes.

Apply locks/re-reads the exact task and verifies CAS. After interruption only the entire postimage hash plus UUID/path binding recognizes a lost local receipt. A dossier marker is not enough. Local task readback, Git committed-tree bytes and exact remote branch SHA are independent evidence. Git pending resumes without blindly writing a new task. Google is deferred with disabled reason. Phone is not autoenabled or called; the existing optional sync contract still controls that integration.

## Digests, replies and delivery

One atomic profile-local ledger allocates day numbers across streams sharing an origin. Immutable digest identity is run_id plus text hash; proposals bind run_id/unit_id/research_revision/targets/day/origin. New-only means the same accepted action/revision is not re-listed in another stream. New update/create proposals and failures/degraded coverage remain visible. Bare references select today's numbering, else the latest digest day. Earlier days require day or exact proposal_id; ignored proposals remain replyable seven days. Choosing one never dismisses others.

Delivery starts `prepared`; a write-ahead send intent is `pending`. An approved sender's actual message ID is stored before readback. Only exact readback of message ID, approved target and full digest text becomes `delivered`. Lost send receipt is `unknown`; repeating never resends or allocates new numbers. A known ID can retry READBACK only. The sender binding freezes with the pending intent. Scheduler/final-response delivery does not expose proof through digest preparation and remains unverified here.

A delivery binding names approved `send_tool`/`read_tool`, target, exact origin_session, literal arguments, send_fields (`target`/`text`), send_id_path, read_fields (`target`/`message_id`) and read_response paths for message_id/target/text. No public tool accepts agent-attested delivered=true. No universal external exactly-once guarantee is claimed.

## UI/backend record

`discovery_runs` returns time, day, public stream name, status, frozen source inventory, checked coverage, research attempt/evidence records, candidate/workstream records, immutable proposals, decisions, conversions, conflicts, failures, recovery and delivery. Proposal targets include task_id, exact path, status and read revision. `unit_id` and `proposal_id`, not titles, are action keys. Raw child capability tokens/launch handles are excluded from the projection. UI work is intentionally absent.

## Source correspondence and verification boundary

The matching algorithm corresponds to the established helper's `_task_exact_values`, `exact_task_matches`, `exact_task_matches_for_candidate` and decomposed nomination checks. Conversion adapts `claim_conversion`, `claim_existing_update`, `_inline_dossier_parts`, `_write_inline_dossier`, `enrich_existing_task` and staged recovery, with stronger whole-postimage binding. The discovery skill generalizes the actual original parent/child prompt's full source-first, canonical-task-first, ownership, decomposition, sufficiency, identity, semantic repair and post-join requirements. Existing portable full child schema and dossier renderer remain authoritative, not a smaller replacement schema.

Synthetic tests cover registered collection/context/research callbacks/parent acceptance/global join/proposal/compatibility approval, exact/semantic/completed targets, all-option selection, metadata/comments, CAS and lost local receipt, actual sandbox Git tree and bare-remote verification, immutable numbering/reply windows, sender/readback receipts and unknown-send refusal. Source semantic conversion regressions are transformed to generic seasonal-item fixtures. Unit fixtures are NOT live provider or model-semantic proof.

## Explicit remaining acceptance gaps

- Cross-session scheduled continuation/adoption is fail-closed, not automatically authorized from a model-supplied origin or job ID. The integration authorizer for a new parent and exact scheduled-origin evidence is not wired. Same-parent saved-run resume works.
- Generic source bindings require normalized items and actual structured account/window/pagination evidence. No provider-specific item normalization or private connector binding is bundled. Unmapped readers remain partial; actual provider canaries are still required.
- Stream creation includes requested approved reader toolsets, but changing source configuration does not yet reconcile existing cron toolsets. Scheduled runtime/origin delivery canaries and duplicate-send suppression between scheduler delivery and an explicit sender remain release gates. Do not enable both blindly.
- Origin `send` currently authorizes the origin session itself. Scheduled-parent explicit send authorization is not implemented. Default cron final-response delivery remains prepared/unverified in backend state, never falsely delivered.
- Changed edits to an already prepared immutable plan are rejected rather than ignored. Explicit unwritten-plan amendment/cancellation is not implemented; do not improvise state edits. Multi-proposal task merges are not implemented.
- Optional phone completion is deferred, not a targeted enabled-phone verification receipt. No device call occurred. Google deferral is intentional.
- Core pruning remains conservative because downstream candidate completion/delivery projection is not fully reconciled into its retention ledger. It retains artifacts rather than deleting unresolved work. Legacy freeform proposals are not migrated into accepted research.
- Actual positive model-driven local and Cloud runner canaries, full source-first semantic transcripts, all crash boundaries, independent contextual/delta integration review, and all evidence-matrix dispositions remain outstanding. Passing unit tests alone is not full parity or release acceptance.
