# Discovery dashboard backend handoff

## Pin and verification

Reviewed implementation pin: **`892048c2ab185ea199ec472b062f183635c78244`**, integrated unchanged into **`discovery-faithful-port`**. This documentation update follows the source commit, so the pin has no self-hash cycle. Use this implementation pin or a later feature-branch commit containing it; do not pin the superseded initial `d6d724b` implementation.

- Parent independently ran the full post-fix suite: **433 passed in 488.47 seconds**, including all 403 baseline tests and 30 dashboard/remediation cases.
- Independent focused delta review passed: **30 dashboard/remediation tests** plus **four positive resume/conversion checks**. The actual installed-host ASGI probe uses real discovery/import/mount, canonical HTTP authentication, host-issued native tickets and secondary-profile plugin-host IPC.
- Review's two reproduced defects are fixed: pending/dismissed unwritten plans cannot be applied through resume, and slow task/Git work no longer blocks unrelated HTTP requests. Regression tests first failed before the fixes and now pass.
- Plugin validation passed. It retains the existing process-inspection caution and two documented host-version-sensitive imports, `PluginManifest` and `web_deps.late` for the canonical auth guard. Auth-focused review found no demonstrated owner/profile/verified-child bypass on the exercised installed host. These are tested host seams, not a universal stable auth SDK; rerun the mounted-host probe on host upgrades.

## UI contract

Base namespace: `/api/plugins/alchemy-task/`.

- `GET runs`, optional `stream`, `day_from`, `day_to`.
- `GET runs/{run_id}`.
- `POST proposals/{proposal_id}/approve`.
- `POST proposals/{proposal_id}/dismiss`.
- `POST runs/{run_id}/units/{unit_id}/resume`.

See **UI/backend record** in [discovery-backend-contract.md](discovery-backend-contract.md) for exact request/response/error shapes. Current proposal `state`, timezone-aware `expired`, `result.task_id`/title/`operation` (`created` or `updated`)/receipt state, run summary counts/degraded state and existing-task outcomes are available in list/detail responses. Dashboard approvals require an exact persisted proposal ID. Expired approval needs literal `allow_expired:true`; chat numbering and its seven-day expiry remain unchanged. Duplicate approval returns the saved receipt, including pending delivery. Resume reuses the saved plan and refuses pending/dismissed proposal-backed plans before any task or Git write.

## Shared namespace integration

Discovery owns only `dashboard/discovery_api.py` and its subrouter. Preserve the UI branch's existing `dashboard/plugin_api.py` task/settings routes; it already conditionally includes `.dashboard.discovery_api` when present. Both loaders use the same source-specific package naming convention. Include the discovery router once and merge the backend manifest's `api`/name fields into the UI manifest without dropping frontend fields. Do not replace the UI's shared loader with this branch's discovery-only bootstrap.

The candidate worktree/branch is retained temporarily for UI integration and broader discovery release reconciliation; the canonical task remains open. No main-branch merge, installation, service restart, production cutover, Cloud dashboard canary, browser login or real SaaS/message send is claimed. Git tests used local synthetic bare remotes.
