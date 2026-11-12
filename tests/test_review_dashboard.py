"""Review item 4: the dashboard uses only Hermes's published plugin APIs.

No dashboard-side auth guard (plugin routes sit behind the dashboard's auth), no hand-built
PluginContext, settings through hermes_cli.config, state through PluginState.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alchemy_task.dashboard import discovery_api, ui_common

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"


@pytest.fixture
def hermes_home(tmp_path):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    home = tmp_path / "hermes-home"
    home.mkdir()
    (home / "config.yaml").write_text(json.dumps({"plugins": {"entries": {"alchemy-task": {
        "settings": {"default_area": "work", "nested": {"value": 3}}, "config": {"legacy_only": "old"}}}}}))
    token = set_hermes_home_override(str(home))
    try:
        yield home
    finally:
        reset_hermes_home_override(token)


@pytest.mark.parametrize("needle", ["web_deps", "_require_token", "profile_matches_home", "PluginManifest",
                                    "PluginContext(", "hermes_cli.profiles", "save_plugin_setting"])
def test_dashboard_sources_avoid_private_hermes_surfaces(needle):
    for path in DASHBOARD.glob("*.py"):
        assert needle not in path.read_text(), f"{path.name} uses {needle}"


def test_host_context_reads_plugin_settings_from_load_config_readonly(hermes_home):
    ctx = ui_common.HostContext()
    assert ctx.get_config("default_area") == "work"
    assert ctx.get_config("nested.value") == 3
    assert ctx.get_config("legacy_only") == "old"
    assert ctx.get_config("missing", "fallback") == "fallback"
    with pytest.raises(ValueError):
        ctx.get_config("_private")


def test_host_context_writes_only_its_own_settings_subtree(hermes_home):
    from hermes_cli.config import load_config_readonly
    ctx = ui_common.HostContext()
    ctx.set_config("default_area", "home")
    ctx.set_config("research_model", "")
    assert ctx.get_config("default_area") == "home"
    assert ctx.get_config("research_model") == ""
    entry = load_config_readonly()["plugins"]["entries"]["alchemy-task"]
    assert entry["settings"]["nested"] == {"value": 3}  # siblings survive the merge
    assert entry["config"] == {"legacy_only": "old"}


def test_host_context_state_is_the_public_plugin_state(hermes_home):
    from hermes_cli.plugins_state import PluginState
    ctx = ui_common.HostContext()
    assert isinstance(ctx.state, PluginState)
    assert Path(ctx.state.data_dir).parent == hermes_home / "plugin-data"  # the same namespace the loader uses
    ctx.state.set("probe", {"ok": True})
    assert PluginState("alchemy-task").get("probe") == {"ok": True}
    assert ctx.current_cron_execution() is None
    assert isinstance(ctx.profile_name, str) and ctx.profile_name


def test_host_context_dispatches_through_the_public_registry(hermes_home, monkeypatch):
    from tools import registry as reg
    calls = []
    monkeypatch.setattr(reg.registry, "get_entry", lambda name, **kw: object())
    monkeypatch.setattr(reg.registry, "dispatch", lambda name, args, **kw: calls.append((name, args)) or "{}")
    assert ui_common.HostContext().dispatch_tool("cronjob_manage", {"action": "list"}) == "{}"
    assert calls == [("cronjob_manage", {"action": "list"})]


def test_runtime_builds_from_the_facade(hermes_home):
    rt = ui_common.runtime()
    assert isinstance(rt.ctx, ui_common.HostContext)
    from hermes_cli.plugins_state import PluginState
    assert rt.data_dir == PluginState("alchemy-task").data_dir
    assert rt.data_dir.parent == hermes_home / "plugin-data"


def test_profile_selector_must_name_the_request_home(hermes_home):
    from hermes_constants import profile_name_for_home
    own = profile_name_for_home(hermes_home)
    assert discovery_api._serving_profile(own) is (own is not None)
    assert discovery_api._serving_profile("someone-else") is False
    assert discovery_api._serving_profile("") is False


def test_skills_and_readme_describe_read_only_readers():
    root = DASHBOARD.parent
    discovery = (root / "skills" / "discovery" / "SKILL.md").read_text()
    assert "Readers are read-only tools" in discovery and "local MCP server that exposes only read tools" in discovery
    assert "## Files during a run" not in discovery and "scratch folder" not in discovery
    assert "never terminal, code or file tools" in (root / "skills" / "setup" / "SKILL.md").read_text()
    readme = (root / "README.md").read_text()
    assert "rely on Hermes's dashboard sign-in" in readme
    assert "has no terminal, code or file tools and cannot create or change scheduled" in readme
    for text in (discovery, readme):
        assert "\u2014" not in text
