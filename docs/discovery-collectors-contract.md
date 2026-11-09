# Daily collector adaptation contract

## Scope and lifecycle

This is a source-derived collector layer, not a provider client. It contains no credentials, account routing constants, source SDK, username inference or live source reads. The real adapter boundary is exercised by synthetic tests: `make_daily_reader` -> `SourceAdapter.collect` -> actual `DiscoveryStore` backlog and coverage. No claim of deployed provider or model-driven acceptance follows from those tests.

Implementation branch: `discovery-daily-collectors`, base `0be48eb127e06340e9ed9490cac4636e5674f334`. This isolated worktree is retained for parent cherry-pick and independent integration review. No push or merge is authorized here. Only the collector module, its tests, this document and pure mail/transcript functions in `discovery_sources.py` are in scope. Saved-run continuation in the integration coordinator is separately owned.

## Exact exported interface

```python
make_daily_reader(config, read_page, *, snapshot_root,
                  read_thread=None, read_replies=None) -> callable
reader(config, start, end, cursor) -> normalized_page
SourceAdapter(store, config, read_page=reader).collect(
    stream, start=start, end=end, max_pages=None)
```

The incoming reader config must equal the factory's frozen config. `start` and `end` are timezone-qualified ISO strings. Preserve these strings and the approved account and scope exactly. `snapshot_root` must be a run-private, profile-owned directory outside the vault. Do not share a root among simultaneous writers. Reuse the same root for that window's mail and transcript sources and for sequential recovery of partial passes. Different windows, configs and scopes have independent state keys.

Common config: existing `source_key`, `account_key`, nonempty `scope`, `read_method`, plus `kind` in `mail`, `transcript`, `slack`, `generic`. The default kind is `generic` for existing integrations. Existing source relevance/confirmed-identity checks still run.

Approved raw callback responses for every source have these actual, structured fields:

```python
{
    'account_key': config['account_key'],
    'scope': config['scope'],
    'start': start, 'end': end,
    'items': [...],
    'next_cursor': None,             # or real nonempty continuation token
    'pagination_exhausted': True,    # bool, actual provider metadata
    # optional error / truncated: either makes the response unusable
}
```

Neither prose nor model completeness fields manufacture exhaustion. Missing, repeated or inconsistent pagination evidence fails closed. A provider binding must expose actual metadata from its tool result and map errors faithfully. The `generic` branch is a transparent callback for already-normalized candidate pages, so its existing SourceAdapter checks apply unchanged. The other branches return normalized top-level candidates, with complete `messages`, `source_revision`, `source_ids`, and `source_key`, not nested `candidate` wrappers.

## Mail and transcript

`read_page(config, start, end, cursor)` returns raw mailbox items. An item is either a reference with real `threadId`, or a full thread `{id, messages, complete: True}`. A full message has real `id`, integer-millisecond `internalDate` and full Gmail-shaped `payload` (headers/MIME/body). Explicit truncation refuses admission.

A standalone `transcript` reader may instead return full message items with `id`, real `threadId`, `internalDate` and full `payload`. Those messages need no redundant thread expansion: they are deduplicated and projected by actual message identity. A complete message is not proof of every historical message in its thread, so this direct-message route does not publish a reusable whole-mailbox thread snapshot. It still loads an available matching complete mailbox snapshot first, or reuses its own saved raw message pages on recovery. A sender-filtered message source must carry its genuinely narrower scope.

`read_thread(config, start, end, thread_id)` is optional if all raw items are already full threads. Otherwise it is required and returns the common response envelope with exactly one matching full thread. The callback must acquire all primary pages itself or expose incomplete pagination; this wrapper refuses an incomplete primary thread, rather than pretending its first page was full.

The listing is exhausted across all raw pages before any thread is admitted. Unique thread IDs are fetched once; repeated identical message IDs are deduplicated before sender/report predicates. Contradictory full bodies refuse the pass. Historical messages stay in the candidate. Ordinary mail retains the source latest-message lower-window predicate, without inventing an upper bound absent from the source algorithm. It uses the first nonempty subject and never clips bodies for a digest display limit.

Configurable admission inputs:

- `sender_domains`: normalized internal FROM domains, not recipient domains. No private default domain exists. `discovery_config action=source` refuses a `kind: mail` source without nonempty `sender_domains` unless the user explicitly approved `admit_all: true`. `discovery_start` applies the same check to saved sources and refuses with `needs_input` (no run is created) for a mail source saved without either, for example before this gate existed.
- `excluded_senders`: configured exact shared/support FROM addresses. Excluded-only threads do not qualify. One other internal sender suffices, including the owner. Case/whitespace are normalized.
- `owner_email` and `owner_report_pattern`: only one real owner message with a case-insensitive matching subject is excluded. The configured regex expresses the deployment's exact word boundaries. Replies, including another owner message, prevent this special exclusion. No private report words are baked in.
- `service_sender` for `kind=transcript`: exact normalized FROM comparison per message, inclusive per-message window, nonempty Suggested next steps, and one genuine message identity per candidate (`gmail:account:thread:message`). Multiple qualifying messages in one thread remain separate. Neighbor/non-service messages cannot borrow service admission.

`extract_body_text` retains plain-MIME preference and multipart recursion. HTML uses the source's block closing tags, BR and list-entry separators before tag stripping/entity unescape. Suggested sections stop at next headings/footers. A deliberate correction prevents an explicit empty section from falling through the inline fallback and swallowing a following Summary.

### Shared snapshots and recovery

After every raw listing page an atomic private `pass-<hash>.json` stores all raw items, page hashes/counts/cursors, and continuation. Each successful primary thread is saved too. On failure or bounded pass, no complete mailbox snapshot is published and no full watermark is earned. A new factory with the same config/root/window resumes the saved raw cursor, even if its adapter begins with `cursor=None`; it does not discard page one or redo successful mail primary acquisitions.

Only all-page, all-primary success of a `mail` source calls actual `publish_snapshot`; a `transcript` source only consumes a matching snapshot and never publishes one, because its listing is sender-filtered. The shared `mail-<hash>.json` key binds account, approved scope, and exact window. Both mail and transcript call actual `load_snapshot`; the latter performs zero redundant collector reads when a matching snapshot exists. Snapshot owner/mode/account/window/completeness checks remain active. All threads, including nonqualifying service notes, are included.

**Provider obligation:** scope describes the actual raw mailbox population. A transcript-only provider search must use a distinct scope from a whole-mailbox search. Never label a sender-filtered scan as the same broad mailbox scope, or reuse its snapshot as whole-mailbox evidence. The wrapper cannot independently audit a connector that lies about its actual scope.

### Quota contract

Optional trusted config `reader_policy={'structured_errors': True, 'owns_retries': False}` enables the existing source `QuotaReader` for mail page and thread callbacks. Otherwise no extra retry is added. Exceptions must have actual `resp.status`, header mapping and structured JSON `content`, not invented HTTP fields parsed from prose. Only 429 and the source's named transient 403 quota reasons retry. Other 403/401 failures do not.

Preserved semantics: nine attempts per request; one 240-second retry-sleep-decision budget shared by that factory/window's mail calls; `max(Retry-After, min(2**attempt,32)+jitter)`; HTTP-date headers supported. Healthy calls are not cut off by this budget. No whole-scan retry, token blanket policy or provider timeout is invented. A new window gets a fresh quota reader. A restarted factory is a new recovery invocation, not a persistent provider quota hold. Existing transport-owned retry/timeout policy must be documented and verified by the binding.

## Slack: seed search and exact primary recipe

`seed_queries` is a nonempty ordered list of approved queries supplied by setup. This can represent confirmed UID mention, confirmed UID sender and confirmed name/aliases without deriving personal identity from a username. There are no hardcoded private queries or channels.

The Slack raw `read_page` receives a copy of the config with `collector_request`:

```python
{'operation': 'search',
 'query': '<approved query> after:<local start date minus 1 day> before:<local end date plus 1 day>',
 'count': 20, 'sort': 'timestamp', 'sort_dir': 'asc'}
```

Use the original window offsets for local calendar padding. The callback's cursor is the actual provider cursor within that query. All query branches and their pages must exhaust before primary acquisition; the wrapper's outward continuation is an opaque `daily:<hash>` that retains query position. No fixed 200-match truncation is treated as exhaustion. Real seed `channel.id`/`channel_id`, timestamp spelling, text, optional `thread_ts`, and permalink query root are retained. Exact inclusive seed filtering precedes grouping. Repeated search identities merge useful full-prefix content; incompatible content is explicit failure, not arbitrary selection.

`read_replies(config, start, end, request)` is the approved primary callback. Requests are exactly:

- real thread: `{operation:'replies', channel, ts:root, limit:200, inclusive:True}`;
- channel block before: `{operation:'before', channel, latest:first_seed, limit:6, inclusive:True}`;
- channel block after: `{operation:'after', channel, oldest:last_seed, limit:10, inclusive:False}`;
- multi-seed block between: `{operation:'between', channel, oldest:first_seed, latest:last_seed, limit:100, inclusive:True}`.

Thread detection includes permalink `thread_ts`; top-level seeds cluster at <=1800 seconds, preserving exact timestamp spelling. Before/between/after records are merged in the source recipe order, deduped by genuine timestamp, then sorted chronologically. Seeds are retained as a fallback/context supplement, never renamed to fabricated IDs. Subset block deduplication preserves all real seed IDs and richer content, rather than silently losing a decisive seed. Context-only records are not promoted to decisive source IDs.

Thread and between responses require actual exhaustion metadata. Missing root, truncated thread, unknown pagination, or an unexpanded primary callback never earns complete coverage. A thread or between response whose pagination is not exhausted (for example one 200-reply page of a longer thread) does not fail the source: like the source daily, the returned page is kept, that block is flagged `partial: true` with a `partial_reason`, sibling blocks are kept, and the source receipt is recorded `partial`. Because every seed search/list page was exhausted and only per-thread primary context was truncated, the watermark still advances to the window end (the source daily reads one page per thread and moves on), so a busy thread is reported partial on the day it is seen and does not hold the window back. A per-thread content defect (thread root not returned, for example a deleted parent; a message without a real timestamp; a channel mismatch; contradictory primary or overlapping block content) or a structured provider-reported failure on that thread's own fetch (for example `{ok:false,error:'thread_not_found'}`, recorded as `provider error <code>`) skips only that thread or cluster, as the source logs and continues (slack_daily_followups.py fetch_thread loop): the receipt is `partial` with a `... skipped: <reason>` entry in its error and `primary_partial` list, siblings are kept, the skipped group never merges into a sibling block, and the watermark advances the same way. The digest coverage line names the reasons (`Coverage: <source>: partial: skipped thread: <reason>`). A seed search/list page that was not exhausted, a provider error on the seed search itself, a structured HTTP error mapped through `error_fields`, or a reader contract violation on any fetch (nonstructured response, account/scope/window mismatch, incomplete recipe) still fails the source and never advances the watermark. Before/after are finite count recipes, not whole-channel scans: the common envelope must additionally have `recipe_complete: True`, established by the binding from the actual bounded request. A next history cursor alone is not a failure when it merely points to history outside the requested finite neighbor count. The callback must not attest recipe completion if its response is itself truncated before that count/boundary.

Coverage means every approved seed-query page plus each required finite primary recipe completed, **not full channel history**. Slack primary branch responses are not separately cached; after a primary failure the saved seed searches are reused but primary recipes may be read again. Its transport retry policy remains the approved reader's responsibility. There is no copied cookie/client transport.

## Source correspondence and evidence

The originals were read directly, including scanner mains and regression suites, rather than treating the audit as implementation. Source workspace baseline: `5e69620137a585664c151813284937faa4ee79f6`. Original paths and private constants are intentionally absent here. Fingerprints identify the inspected algorithm inputs:

| Source input (SHA-256) | Concrete correspondence |
| --- | --- |
| Sender/report predicates `c5a60421c47e7e3d479618eef86d32f7bc4438ccacfde4a45a6e4051663f2be6`, lines 16-36 | `normalize_mail_threads`: normalized internal nonshared FROM-any predicate; exact single-message owner report count/case/reply truth table, configuration replaces private literals. |
| Mail collector `274b66790dae3885020ae0fc4be696a62b08fd744c91cb9187ae466b9498dbec`, lines 157-225 | Unique list thread IDs, complete acquisition before qualification, source first subject/latest lower bound, all-thread snapshot before independent transcript projection. Durable page receipts are a product adaptation. |
| Quota/snapshot library `a7cb23072231cee7e7b2be5a9e01c145357daa088684c9031b963079abb01f73`, lines 29-112 | Existing `QuotaReader`, `publish_snapshot`, `load_snapshot` now exercised by the factory. Explicit account/scope/window and callback request adaptation replace transport/account environment literals. |
| Transcript collector `6a6375bc97942b8624083dee0e367b66bd8bd86dbfeea44f0a0bdd283c67b3a1`, lines 77-196,232-265 | `_html_to_text` and `_normalize_text` verified AST-identical locally; MIME/suggested extraction and per-message sender/window/nonempty admission retained. Empty-section fallback corrected explicitly. |
| Slack collector `4425267cefa5f1193178c3117e9aedf88b110e626263156ca3d1adbd23cbce56`, lines 138-239,315-483 | Date padding/exact seeds/permalink thread root/1800-second clusters/200 replies/6-before/10-after/100-between/sorted subset-dedup recipe. Explicit partial evidence replaces the source's silent pagination/failure swallowing. No private client is copied. |
| Sender regression input `eceb9f45593db02d8dcbfad547e5715530f4d2661f6c7a2acd4e70b28b90bae9` | Portable truth-table fixtures change addresses/report words but preserve support-only/external/internal/owner/case/reply cases. |
| Quota regression input `20edbb0f400c062530f9d9ceebab5ff6c4782ba6b14460539d3ee4e929b0221d` | Portable factory cases cover same-request retry, nonquota refusal, nine-attempt ladder, primary failure/no success snapshot, service-note snapshot reuse and continuation. Existing quota utility tests remain active. |

The tests use actual factory/SourceAdapter/store execution with synthetic callback transports and fake quota time. They do not call private source scripts, external providers, live credentials or other profiles.

## Remaining integration ownership and limitations

The authoritative coordinator must bind this factory around its approved raw tool reader, pass the saved run-private root, supply the optional primary callbacks, consume Slack `collector_request`, and preserve the callback metadata contract. A reader unable to produce the contract is explicitly partial/failed. This branch does not claim that raw provider binding is finished or deployed. It does not change registration, integration, runner, SourceAdapter or state code.

The parent-owned saved-run pass-continuation gap is distinct: this layer retains raw private page state, but cannot cause an integration coordinator that permanently memoizes a partial receipt to call it again. The parent must reconcile that continuation separately. Independent contextual review, provider/host acceptance, integration cherry-pick and release gates remain open. No live daily/core/profile changes, new dependencies, sends or source calls occurred.
