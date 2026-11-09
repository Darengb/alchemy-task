# Discovery backend contract

## Status and scope

This is an implemented, tested integration under final acceptance, not a deployment or full-parity claim. The parent independently ran all 399 tests at code revision `d8d72f70e4d18b4dfbd55c49c08416741c143c07`. Registered local and Cloud full-pipeline synthetic canaries passed at `4261525` and `d8d72f7` respectively, and registered raw collector transport passed at d8. A corrected actual native one-shot scheduled adoption also passed at d8 after supported profile-scoped plugin activation refreshed the canonical gateway registry. Native origin-post delivery and remaining source-obligation evidence still need separate qualification. UI is separate.

The installing profile owns all mutable discovery state under its plugin data directory. No bundled credentials, private collectors, cross-profile lookup, source mutation or new runtime dependency is introduced. Broad inherited source tools are procedurally read-only, not a mechanical sandbox. Registered task/integration entrypoints additionally refuse verified discovery-child writes.

## Registered tools

All handlers consume host `session_id`/`task_id` kwargs, never model-provided caller identity. New tools return `{ok,result}` or `{ok:false,error}`. Existing `discovery_start`, `discovery_submit`, `discovery_decide` retain the plugin's top-level receipt convention.

| Tool | Required inputs and effect |
| --- | --- |
| `discovery_stream` | Existing list/create/update/remove/run_now UX, origin chat, schedule, areas, source scopes and optional actual reader `toolsets`. |
| `discovery_config` | `action=source`, stream, config, user_approved; `action=identity`, account_key, explicit identity, user_approved; `action=delivery`, stream, binding, user_approved; or status. Never accepts credentials. |
| `discovery_start` | stream and configured/explicit mode (`production`, `shadow`, `research_only`); creates or resumes the same pending saved run/config/business date/window for its verified parent. Missing setup blocks. |
| `discovery_collect` | run_id, source_key; executes the approved configured reader, or records an explicitly partial envelope. Optional max_pages bounds one pass, never proves exhaustion. |
| `discovery_context` | run_id, optional approved context; freezes collected candidates, full all-status task bodies, complete installed-skill inventory/content, installing-profile SOUL/memory files, full discovery rubric and source/config context. |
| `discovery_research_run` | run_id, optional expected_revision; bounded public lifecycle FIFO. Requires operator-installed supported timeout evidence, not a fabricated native delegation field. |
| `discovery_research_fetch` | run_id, resource, revision, optional cursor/limit; child adds token/binding, parent omits both. Full lossless pages and durable page receipts. Use default 8192 or a content limit from 4 through 16384 bytes. |
| `discovery_research_submit` | run_id, token, binding, payload OR multipart upload action begin/part/commit. The registered payload exposes the full child schema with references resolving at the parameters root. Intermediate parts explicitly continue; full commit says stop. |
| `discovery_research_accept` | run_id, token, payload_sha256, assessment with boolean accepted, nonempty reason (maximum 500 characters), and textual observations for all exported CHECKLIST fields. Full parent payload reads required. |
| `discovery_actions` | run_id, cid, verified locator/outcome anchors for independent asks sharing source identities. |
| `discovery_reconcile` | run_id, cid, current accepted-outcome-bound decision/reason/accepted_unit_ids. |
| `discovery_join` | run_id, optional explicit degraded reasons; full selected-run barrier, never a live-attempt success. |
| `discovery_recover` | run_id, optional owner_restarted/adopt. Reconnect/fence unknown evidence without refund; new-owner adoption still needs an integration authorizer. |
| `discovery_release_hold` | run_id, explicit reason; deliberate release, not uncertain-attempt refund. |
| `discovery_match` | run_id, unit_id; post-join exact matching over all-status current full task files; complete target-body resources and ALL nominated semantic options. |
| `discovery_decision` | run_id, unit_id, decision=propose/auto/noop/conflict, substantive reason; auto/noop use exact target_task_id and expected_revision. Auto additionally requires parent useful_delta=true. |
| `discovery_digest` | run_id, action=prepare/get/delivery/send. Preparation freezes numbering/review. Native send returns exact final text and pending host metadata; verified-sender mode requires an approved sender plus exact-message readback mapping. |
| `discovery_submit` | Compatibility alias requiring saved run_id and completed research/join/decisions. Freeform candidates/research_notes are rejected, not silently imported. |
| `discovery_decide` | approve/dismiss references, optional day/stream and per-reference edits. Semantic items require choice=update/create; multiple options require target_task_id. No title resolution. |
| `discovery_conversion_recover` | run_id, unit_id; inspect/resume an exact conversion, or explicitly revise/cancel/bind_manual an unwritten plan with expected_plan_revision, reason and origin approval. No blind re-creation. |
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

Response paths select ACTUAL returned values. They do not echo requested account/window into evidence. Generic bindings may map actual item fields and configured source identity components; complete raw mail, transcript and Slack responses use the source-derived collector factory. Kind-specific policy, full-thread/primary callbacks, actual pagination and approved population scope are explicit configuration, not inferred provider access. See `discovery-collectors-contract.md`. Structured error mappings enable conditional quota handling only when the reader exposes actual status/headers/content and does not already own retries.

Missing/unsupported mappings, prose returns, account/scope/window mismatch, missing pagination and truncation remain failed/partial. Agent attestation never advances a watermark. A new run starts each source at its committed watermark; before a source has one, it starts at the earliest adapter-verified attempted window start (so a failed or partial first run's interval is read again), and only a source with no attempt at all starts 24 hours back. Every valid page enters durable backlog before coverage. Partial passes resume the original window and actual continuation; immutable pass receipts retain history rather than memoizing a failed pass forever. New scans revalidate exact approved source membership/scopes; resumed scans retain their frozen approved configuration. Source configuration reconciles the existing job's approved reader toolsets in place, preserving its binding.

Full primary bodies remain lossless `source-body-<candidate ID>` resources, indexed by `source-material`; the shared helper index stays compact. A child must fetch its entire assigned primary body and required inventory/config/skill resources before submission. Page receipts establish retrieval, not understanding. Selected/accepted/excluded/deferred/blocked lineage is separate from coverage and daily research budget. An exhausted/unknown research failure remains blocked, not silently given a third attempt by a new scan.

Each reserved attempt also freezes its own parent-issued action registry when present and generic typed-source templates as immutable required paged resources. The bootstrap names those resources without inlining large registries into the bounded context. Register verified action anchors before reserving the child that needs them. The child copies exact action IDs, locators, outcomes and assigned provider/scope mechanics, while obtaining decisive message IDs and all research facts from actual source evidence. Later attempts receive their own frozen contract; no launched attempt's contract is retroactively rewritten. Payload validation, semantic review and the two-attempt limit remain unchanged.

Installed profile SOUL.md and memories/MEMORY.md/USER.md are snapshotted only when present and contained within that profile. Broader approved document/capability context is supplied by the parent from its available tools. This is not a claim of complete hosted connector discovery or a credential inventory.

## Matching and immutable conversion

`DiscoveryConversion(rt,store)` exports `joined`, `match`, `prepare`, `apply`, `deliver_git`. Trusted Python methods are not an independent authorization boundary. Public mutation authority stays in the registered parent decision/immutable proposal paths.

Matching adapts the established helper's directional typed identity and decomposed broad-thread nomination guard. Complete decisive-message equality needs no nomination for a single action. Independently anchored same-message actions retain their action identity: sharing a message alone cannot grant another action's task automatic authority. Approved source URL/account mappings are consumed explicitly; unknown hosts/accounts are not inferred. Related-only dossier sections do not grant exact identity. One exact target plus verified useful delta permits auto enrichment; no delta is byte-preserving noop; semantic targets require choice; several exact targets conflict without mutation. Completed tasks are included and invalid exact canonical nominations fail precisely. No title-similarity suppression.

Preparation persists UUID/path, exact accepted research revision, expected preimage and WHOLE postimage before writing a task. New and update conversions promote the exact accepted dossier immediately. Existing YAML comments/user metadata/sections/dossiers remain; no generic research is launched. Ordinary task_create/research behavior is unchanged. The selected approval batch is prepared before its first task write, so an invalid second date/area causes no task writes.

Apply locks/re-reads the exact task and verifies CAS and current exact destination before the first write. After interruption only the entire postimage hash plus UUID/path binding recognizes a lost local receipt. A dossier marker is not enough. Origin-approved unwritten plans support CAS-bound amendments, cancellation and explicit binding to a manually created canonical task. Explicit proposal merges retain every accepted dossier under one task; sibling updates to one task compose a whole postimage without accepting arbitrary intervening edits. Supported user corrections update active task fields/Notes/Plan/checklist while preserving immutable research evidence.

Local task readback, Git committed-tree bytes and exact remote branch SHA are independent evidence. Git pending resumes without blindly writing a new task. A workspace with no Git remote ends with Git `local_only` (the committed tree holds the exact task bytes) and one that is not a Git repository ends with `no_git`, the same terminal outcomes core `task_create` reports; both let the conversion reach `complete`. Google is deferred with disabled reason. Disabled phone integration makes no calls; an already enabled mirror waits for the existing approved sync engine and requires exact target projection readback before completion. Observing that queue never overwrites the sync engine's mutable outbox. Production mode is required for task mutation and sending; shadow/research-only runs cannot use parent approval to bypass that boundary.

## Digests, replies and delivery

One atomic profile-local ledger allocates day numbers across streams sharing an origin. Business dates and default reply dates use the confirmed stream timezone; saved runs retain their original date. Immutable digest identity is run_id plus text hash; proposals bind run_id/unit_id/research_revision/targets/day/origin. New-only means the same accepted action/revision is not re-listed in another stream. Digests retain researched current state, next action, source links, semantic overlap/addition, automatic update outcomes, titled failures and degraded coverage. Pending Git/mirror work is visible without assigning new proposal numbers. Bare references select today's numbering, else the latest digest day. Earlier days require day or exact proposal_id; ignored proposals remain replyable seven days. Choosing one never dismisses others.

Streams have `delivery_owner=native_origin` by default. Native jobs use the approved `deliver` target (default `origin`) and `attach_to_session=true`; the scheduled final reply is the exact immutable prepared digest, never SILENT. Public `discovery_digest action=send` returns instruction and `final_text`/`digest_sha256` metadata only, never an alternate post. `discovery_runs.delivery` and public delivery status expose `state=host_pending`, `delivered=false`, `verification=awaiting_host`, `delivery_owner`, `deliver`, `job_id`, and `native_target_status`. Missing origin metadata is `unconfigured`. Preparation/final return is not host delivery evidence. Native cron owns its retry semantics; there is no universal exactly-once guarantee, no extra job and no reader prerequisite for native activation.

Optional `verified_sender` requires approval from the original/proven same origin and actual existing-message ID/target/full-text verification using the configured sender/reader pair. Strict fresh setup stays SETUP_BLOCKED/no-job until this succeeds. The SAME job changes to `deliver=local` and returns `[SILENT]`; the plugin sender alone owns all posts. An explicit send starts `prepared`, persists `inflight` intent and actual message ID, then requires exact readback before `delivered`. Lost receipt is `unknown`; retry never blindly resends or allocates new numbers; a known ID retries readback only. The binding freezes with intent. No public agent-attested delivered=true is accepted. No automatic fallback to native output.

`discovery_config action=delivery config.delivery_owner` accepts `native_origin` or `verified_sender` (a full approved binding defaults to the latter for compatibility). Owner changes preserve the job/origin/schedule and require public job readback. Switching back to native requires saved `origin_session` and approval; pending/unknown explicit sends block that switch. A verified binding includes actual `send_tool`/`read_tool`, `target`, saved `origin_session`, literal arguments, `send_fields`, `send_id_path`, `read_fields`, exact `read_response` mappings, scheduled approval/toolsets and existing verification message ID/text. Actual host delivery proof remains a separate acceptance gate; synthetic tool tests prove adapter behavior, not provider delivery.

## UI/backend record

`discovery_runs` returns time, day, public stream name, status, frozen source inventory, checked coverage, research attempt/evidence records, candidate/workstream records, immutable proposal content, decisions, conversions, conflicts, failures, recovery and delivery. Proposal targets include task_id, exact path, status and read revision. `unit_id` and `proposal_id`, not titles, are action keys. Raw child capability tokens/launch handles are excluded from the projection. The shared projector also supplies the current-state additions below; frozen digest text/items are never rewritten.

### Dashboard and desktop HTTP extension

`dashboard/plugin_api.py` mounts an isolated discovery router under `/api/plugins/alchemy-task`. It owns only these routes, so task UI routes can include `discovery_router` additively. The minimal `dashboard/manifest.json` declares the backend; merge its `api`/name fields with an existing UI manifest rather than replacing UI fields. No frontend is included.

| Method and full route | Input | Success body |
| --- | --- | --- |
| `GET /api/plugins/alchemy-task/runs` | Optional `stream`, inclusive ISO `day_from`, `day_to` query filters | `{ok:true,runs:[Run,...]}`, newest `time` first, run ID breaks ties |
| `GET /api/plugins/alchemy-task/runs/{run_id}` | Exact run ID | `{ok:true,...Run}` |
| `POST /api/plugins/alchemy-task/proposals/{proposal_id}/approve` | Object with explicit `choice:"create"|"update"`; optional `target_task_id`, `expected_revision`, `title`, `due`, `undated`, `area`, `priority`, `scheduled`, `allow_expired` | `{ok:true,receipt:ConversionReceipt}` |
| `POST /api/plugins/alchemy-task/proposals/{proposal_id}/dismiss` | Empty object or empty body | `{ok:true,proposal_id,state:"dismissed"}` |
| `POST /api/plugins/alchemy-task/runs/{run_id}/units/{unit_id}/resume` | Empty object or empty body | `{ok:true,receipt:ConversionReceipt}` |

No HTTP call needs a chat `session_id`. Authentication comes from the actual host's canonical sensitive-route guard, including its verified browser session, loopback session token, native profile-owner ticket or private plugin-host IPC admission. No new model tool or model-claimable owner flag exists. All handlers check admission before looking up state. Unknown query/body fields, including origin/authority assertions, are refused; they never create authority. The one exception is the host SPA's own `profile` query parameter: it is ignored when it names the profile serving the request (the host adds `?profile=<serving>` to every plugin request) and refused with `invalid_request` when it names any other profile. The host can route an independently authorized served profile to its own plugin host before the plugin handler runs. A native ticket cannot select another profile. A global dashboard owner token retains the host's global-owner semantics; it is not a profile-specific credential.

Each request constructs a fresh `Runtime`/`DiscoveryIntegration` from the public `PluginContext` settings/state facade and the host-bound `get_hermes_home()`. The API does not use model runtime `_ctx`, import-cached data roots, client-supplied homes or a made-up worker identity. The actual host's mount dependency binds the request profile, and private IPC binds secondary profiles in their own plugin host. This installed-host bridge uses `hermes_cli.web_deps.late("_require_token")` and `PluginManifest` alongside the public context facade. The catalog validator currently warns about those two imports; they are tested installed-host seams, not a claim of a separately documented stable auth SDK. A missing host guard fails closed, without a local substitute.

Approval resolves only an exact persisted `proposal_id`, never a number/day/title. It then uses the same `_decide_resolved` prepare, full-batch preflight, apply and Git path as chat `discovery_decide`. Production, joined research, exact destination, CAS and whole-postimage guards remain intact. Saved plans retain their task UUID/path and original requests. An existing conversion receipt is returned unchanged on duplicate approval, including `git_pending`/`phone_pending`, without new tasks or implicit delivery retry. Use the resume route for pending delivery. Resume requires an existing plan and calls the same conversion recovery path; it cannot create a replacement plan. Before any task or Git write, resume refuses a dismissed proposal with `already_resolved` and an unapproved pending proposal with `invalid_request` (409, approve first). This prevents an unwritten plan retained after a failed batch from becoming an alternate approval/expiry path. Approved proposal conversions and automatic existing-task outcomes remain resumable. Dismissed proposals cannot be approved. An approval affects only the selected proposal.

Handlers admit the request and parse asynchronous bodies before offloading synchronous state scans, locks and task/Git application work with `asyncio.to_thread`. The host's request-scoped profile/secret context propagates to that worker; slow Git or hooks do not block unrelated dashboard/Desktop/chat requests on the shared event loop.

### Current-state shapes

`Run` preserves the existing fields: `run_id`, `time`, `day`, `stream`, `status`, `mode`, `timezone`, `sources_checked`, `coverage`, `research`, `candidates`, `lineage`, `pilot_skipped`, `legacy_proposals`, `proposals`, `decisions`, `conversions`, `conflicts`, `failures`, `recovery`, `delivery`. It adds:

```json
{
  "summary": {"pending": 0, "approved": 0, "complete": 0, "dismissed": 0,
              "auto_updated": 0, "conflicts": 0, "failures": 0},
  "degraded": false,
  "outcomes": []
}
```

The four proposal counts read the current digest ledger. `auto_updated` counts locally applied existing-task outcomes (`local_verified`, `git_pending`, `phone_pending`, `complete`), excluding noops; pending remote delivery does not hide a completed local update. Conflicts/failures count the corresponding run arrays, with frozen digest failures included and title-enriched copies of the same failure counted once. `degraded` is true when failures exist or any checked source coverage status differs from `complete`. Every list record includes these fields without another detail request.

Every proposal preserves all frozen content, including `proposal_id`, `unit_id`, `run_id`, `ref`, `number`, `day`, `expires`, `kind`, `title`, `current_understanding`, `substantive_next_action`, `new_information`, `source_links`, `related_context_links`, `sources_unavailable`, `research_disposition`, `uncertainty`, and `targets`. Targets retain `task_id`, `title`, `path`, `status`, `revision` and any additional existing fields. Proposals add `state:"pending"|"approved"|"dismissed"|"complete"`, `expired:boolean`, and, for approved/complete items:

```json
{"result":{"task_id":"saved-task-id","title":"Saved resulting title",
           "operation":"created","state":"git_pending","receipt":{}}}
```

`operation` is `created` or `updated`, from the saved plan; `state` is the conversion receipt state, or `prepared` before a receipt exists. `receipt` is the existing conversion receipt, including independent local/Git/phone/Google evidence when available. `outcomes` retains each frozen existing-task outcome's `task_id`, `title`, `status`, `resume_action`, and all extra fields, then overlays the current conversion status/Git/phone receipt. Completed outcomes clear `resume_action`. `applied_at` is copied only when a saved receipt actually contains it; projection never invents a timestamp.

### Expiry and errors

Expiry compares the proposal's `expires` ISO date to the current date in the run's frozen stream timezone. The expiry date itself remains valid, as in chat. The dashboard may approve an expired exact proposal only with literal boolean `allow_expired:true`; this changes no production/CAS/destination/choice/plan guard. Duplicate approvals return their existing receipts even after expiry. Chat's original seven-day numbered/exact `resolve()` behavior is unchanged and does not gain an override.

Plugin-handled errors use `{ok:false,error:{code,message}}`. Stable codes are `needs_due`, `needs_area`, `stale_revision`, `already_resolved`, `expired`, `not_production`, `invalid_choice`, `target_required`; additional codes are `invalid_request`, `not_found`, `unauthorized`, and `forbidden`. Malformed JSON, non-object bodies, wrong field types and unsupported fields return structured `invalid_request` errors. HTTP status is 400 for input errors, 409 for stale/resolved/expiry/mode conflicts, 404 `not_found` for an unknown exact proposal or run, and 401/403 for plugin-handled auth refusal. Outer host middleware may reject a request earlier with its own canonical auth/profile/consent envelope; the plugin does not rewrite host responses.

Synthetic verification includes actual discovery/import/mount through `_mount_plugin_api_routes`, real canonical HTTP auth, real host-issued native tickets for two synthetic profiles, secondary-profile plugin-host IPC, unauthorized/spoofed admission denial, profile mismatch denial, current CAS before/after preparation, exact approval/dismissal, saved-plan delivery resume and unchanged chat regressions. This is installed-host ASGI evidence, not a deployment, browser login, real provider send or Cloud dashboard canary. Parent auth-focused review and the remediation delta review passed; the parent independently passed all 433 tests at implementation pin `892048c2ab185ea199ec472b062f183635c78244`. The reviewed implementation is integrated into `discovery-faithful-port`; see `discovery-dashboard-handoff.md` for the pin and shared UI-router integration instructions.

## Source correspondence and verification boundary

The matching algorithm corresponds to the established helper's `_task_exact_values`, `exact_task_matches`, `exact_task_matches_for_candidate` and decomposed nomination checks. Conversion adapts `claim_conversion`, `claim_existing_update`, `_inline_dossier_parts`, `_write_inline_dossier`, `enrich_existing_task` and staged recovery, with stronger whole-postimage binding. The discovery skill generalizes the actual original parent/child prompt's full source-first, canonical-task-first, ownership, decomposition, sufficiency, identity, semantic repair and post-join requirements. Existing portable full child schema and dossier renderer remain authoritative, not a smaller replacement schema.

Synthetic tests cover registered collection/context/research callbacks/parent acceptance/global join/proposal/compatibility approval, exact/semantic/completed targets, all-option selection, metadata/comments, CAS and lost local receipt, actual sandbox Git tree and bare-remote verification, immutable numbering/reply windows, sender/readback receipts and unknown-send refusal. Source semantic conversion regressions are transformed to generic seasonal-item fixtures. Unit fixtures are NOT live provider or model-semantic proof.

## Recovery and remaining acceptance

The d8 Cloud canary used one child, full source/task-body/skill/action-contract reads, semantic parent acceptance, global join, explicit create approval, accepted dossier promotion and exact bare-remote verification for all 38 resulting task files. Its explicit verified-sender fixture wrote one new synthetic message; repeats created no extra task or message. Parent REST-history and fresh target readback verification confirmed these facts. This does not establish a real provider post or native-origin delivery. The first actual scheduled local test fired but exposed no fixture tool because manual disk configuration had not refreshed the already-running canonical gateway registry. After supported public install/enable and profile-scoped plugin reload, a corrected actual native one-shot occurrence passed at d8: parent readback verified the native execution and fresh SessionDB tool call, same run/windows/config, adoption record, old `launch_unknown` fencing and retained budget charge without refund. All 86 engine blobs matched the d8 pin, and cleanup was verified. This proves one synthetic local scheduled-adoption case, not native origin posting or real SaaS acquisition.

A later empty-result correction reports `No new follow-ups found.` after a completed check with no new proposals or existing-task outcomes. Incomplete checks and failures stay explicit, and empty digests omit numbered-reply instructions. This correction does not retroactively change immutable saved digests.

Scheduled adoption uses the public host `current_cron_execution` identity, verified job/profile/origin binding and saved run authority. A model-supplied job/session identifier does not grant it. Unknown old attempts remain fenced/reserved; accepted siblings and original windows survive. Supervisor process-death reclamation checks the recorded process incarnation and preserves live-supervisor exclusion. The registered local host-crash continuation passed at the `4261525` pin; the corrected actual native one-shot at d8 separately proves scheduled adoption under a new host session. Expired leases of unknown incarnation retain the documented TTL takeover behavior.

End-state reconciliation projects review/backlog/conversion/delivery facts while retaining unresolved and replyable work. Old freeform proposals remain explicitly legacy/unresearched; they are not invented accepted dossiers. Conservative retention is not proof of cleanup timing.

Remaining work includes native origin-delivery evidence, the specifically unproved and partial source-obligation assertions, optional-surface qualifications and release cleanup/handoff. The 283-row evidence reconciliation distinguishes direct assertions, partial evidence, documentary facts and five unproved behaviors; aggregate test counts are not full-parity proof. Earlier primitive/transport canaries and unit tests are reused only for their exact scope. No production cutover, real-device test or universal live-provider access is claimed.
