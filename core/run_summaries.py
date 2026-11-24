"""One small saved index of per-run summaries, so dashboard reads never rebuild history.

The detailed run records (ledger, decisions, conversion receipts, digest ledger) stay the
source of truth. This index holds what the Tasks badge and the Discovery list need, written
whenever something it depends on changes (digest prepared, proposal decided, conversion
receipt written) and rebuilt from the detailed records when it is missing or unreadable.

``version`` increases on every change, so a client that already holds version N can be told
"unchanged". Expiry is date based: each summary keeps the expiry dates of its pending
proposals and readers compute what is expired for today, so midnight needs no write.

Stdlib only (plus discovery_state's file helpers): loaded without the research module.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .discovery_state import atomic_json, read_json

INDEX_NAME = 'run-summaries.json'
LOCK_NAME = 'run-summaries'
PROPOSAL_STATES = ('pending', 'approved', 'complete', 'dismissed')


def proposal_fields(run_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Summary fields that depend only on the digest ledger (proposal states)."""
    digest = (data.get('digests') or {}).get(run_id) or {}
    counts = dict.fromkeys(PROPOSAL_STATES, 0)
    expires = []
    for item in digest.get('items') or []:
        state = ((data.get('proposals') or {}).get(item.get('proposal_id')) or {}).get('state', 'pending')
        counts[state] = counts.get(state, 0) + 1
        if state == 'pending':
            expires.append(str(item.get('expires') or ''))
    return {'proposals': {'total': len(digest.get('items') or []), **counts},
            'pending_expires': sorted(expires),
            # Approved but not complete: the task write failed or is unfinished; the user can retry it.
            'unfinished_approvals': counts.get('approved', 0)}


def today_in(zone: str | None, default_zone: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        return now.astimezone(ZoneInfo(zone or default_zone)).date().isoformat()
    except (KeyError, ValueError):
        return now.astimezone(ZoneInfo(default_zone)).date().isoformat()


def view(summary: dict[str, Any], today: str) -> dict[str, Any]:
    """The summary as clients see it, with the date-dependent counts computed for ``today``."""
    expires = summary.get('pending_expires') or []
    pending = sum(1 for e in expires if not e or e >= today)
    unfinished = int(summary.get('unfinished_approvals') or 0) + int(summary.get('unfinished_outcomes') or 0)
    out = {k: v for k, v in summary.items() if k != 'pending_expires'}
    open_dates = sorted(e for e in expires if e and e >= today)
    out.update(pending=pending, expired=len(expires) - pending, unfinished=unfinished,
               next_expiry=open_dates[0] if open_dates else None,
               needs_attention=bool(pending or summary.get('attention') or summary.get('conflicts') or unfinished))
    return out


class RunSummaries:
    """Reads and writes ``<discovery state root>/run-summaries.json`` under its own lock.

    Lock order: callers may hold the digest-ledger lock when they take this one, never the reverse.
    """

    def __init__(self, store: Any):
        self.store = store
        self.path = store.state_root / INDEX_NAME

    def load(self) -> dict[str, Any] | None:
        """The index, or None when it is missing, unreadable or marked stale (callers rebuild)."""
        try:
            data = read_json(self.path)
        except (OSError, ValueError):
            return None
        if (not isinstance(data, dict) or type(data.get('version')) is not int or not isinstance(data.get('runs'), dict)
                or data.get('stale')):
            return None
        return data

    def version(self) -> int:
        data = self.load()
        return data['version'] if data else 0

    def _write(self, old: dict[str, Any] | None, runs: dict[str, Any], *, stale: bool = False) -> dict[str, Any]:
        base = old['version'] if old else self._raw_version()
        data = {'version': max(base + 1, time.time_ns() // 1_000_000), 'runs': runs}
        if stale:
            data['stale'] = True
        atomic_json(self.path, data)
        return data

    def _raw_version(self) -> int:
        try:
            raw = read_json(self.path)
            return int(raw.get('version') or 0) if isinstance(raw, dict) else 0
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def replace(self, compute: Callable[[], dict[str, Any]], *, if_missing: bool = False) -> dict[str, Any]:
        """Rebuild the whole index from ``compute()`` (run under the lock so no update is lost).
        ``if_missing``: another reader may have rebuilt it while this one waited; use that one."""
        with self.store._lock(LOCK_NAME):
            old = self.load()
            if if_missing and old is not None:
                return old
            runs = compute()
            if old and old['runs'] == runs:
                return old
            return self._write(old, runs)

    def update(self, compute: Callable[[], dict[str, Any]], *, drop: tuple[str, ...] = ()) -> dict[str, Any] | None:
        """Merge ``compute()`` ({run_id: summary}) into the index; None when there is no index yet
        (the next read rebuilds everything, which includes this change)."""
        with self.store._lock(LOCK_NAME):
            old = self.load()
            if old is None:
                return None
            runs = {k: v for k, v in old['runs'].items() if k not in drop}
            runs.update(compute())
            if runs == old['runs']:
                return old
            return self._write(old, runs)

    def patch_proposals(self, run_id: str, data: dict[str, Any]) -> None:
        """After a proposal decision: refresh that run's proposal fields from the digest ledger."""
        with self.store._lock(LOCK_NAME):
            old = self.load()
            if old is None:
                return
            if run_id not in old['runs']:
                # Unknown to the index: mark it stale so the next read rebuilds from the records.
                self._write(old, old['runs'], stale=True)
                return
            current = old['runs'][run_id]
            new = {**current, **proposal_fields(run_id, data)}
            if new != current:
                self._write(old, {**old['runs'], run_id: new})

    def invalidate(self) -> None:
        """Fail-open fallback when an update could not be applied: force a rebuild on the next read."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
