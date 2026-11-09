"""Fixtures for the end-to-end outcome suite: one synthetic profile, workspace and bare remote per test."""
import datetime as dt

import pytest

from e2e.host import build_host, plugin_settings
from e2e.world import World, isolate_env, write_host_config

DAY1 = dt.datetime(2026, 11, 3, 23, 30, tzinfo=dt.timezone.utc)  # 18:30 New York, a Tuesday


def pytest_collection_modifyitems(items):
    for item in items:
        if '/e2e/' in str(item.fspath).replace('\\', '/'):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture
def world(tmp_path, monkeypatch):
    hermes_home = isolate_env(tmp_path, monkeypatch)
    w = World(tmp_path / 'world', hermes_home)
    write_host_config(hermes_home, plugin_settings(w.ws))
    return w


@pytest.fixture
def host_factory(world):
    """Each call is a fresh host process view of the same profile (state, config and cron survive)."""
    def make():
        return build_host(cron_path=world.root / 'fake-cron.json')
    return make
