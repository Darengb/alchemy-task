"""Drive the REAL host session code for chat and delivery-thread sessions (synthetic profile).

Sessions are created by the gateway's own ``SessionStore`` and the host-opened delivery thread
is seeded by cron's own ``_seed_cron_thread_session`` (session row + mirrored digest), exactly
as a native continuable delivery does. Nothing here hand-writes session rows.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

JOB_NAME = 'alchemy-task: discovery {stream}'


class HostSessions:
    def __init__(self, home, monkeypatch):
        self.home = home
        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv('HERMES_HOME', str(home))  # cron mirror writes the profile's state.db
        gateway_session = pytest.importorskip('gateway.session')
        from gateway.config import GatewayConfig
        from hermes_state import SessionDB
        self._gs = gateway_session
        self.db = SessionDB(db_path=home / 'state.db')
        self.store = gateway_session.SessionStore(config=GatewayConfig(), sessions_dir=home / 'sessions')
        self.store._db = self.db

    def source(self, platform='telegram', **fields):
        from gateway.config import Platform
        return self._gs.SessionSource(platform=Platform(platform), **fields)

    def message(self, platform='telegram', **fields):
        """An inbound user turn as the platform adapter builds it; returns its session id."""
        entry = self.store.get_or_create_session(self.source(platform, **fields))
        self.store.update_session(entry.session_key)
        return entry.session_id

    def deliver_into_thread(self, *, platform, origin_chat, thread_id, text, stream='work', job_id='job-1', is_dm=False,
                            chat_name='general', scope_id=None):
        """Host native delivery of `text` for the stream's job into the thread the host opened.

        `chat_name` and `scope_id` are the delivering job's captured origin (the chat it was
        created in), which the host seeder records on the thread session."""
        from cron.scheduler_delivery import _seed_cron_thread_session
        _seed_cron_thread_session({'id': job_id, 'name': JOB_NAME.format(stream=stream)},
                                  SimpleNamespace(_session_store=self.store), platform, str(origin_chat),
                                  str(thread_id), text, chat_name=chat_name, is_dm=is_dm, scope_id=scope_id)

    def close(self):
        self.db.close()
