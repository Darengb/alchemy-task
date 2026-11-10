"""research_capabilities reports missing access by name (toolset env vars, skill hints), never by value."""
from __future__ import annotations

import dataclasses
import json

import pytest

from alchemy_task import research_agent as ra
from alchemy_task import runtime

SECRET_VALUE = "sk-live-THIS-MUST-NEVER-APPEAR-123"


class State:
    def __init__(self, data_dir):
        self.data_dir, self._d = data_dir, {}

    def get(self, key, default=None):
        return json.loads(json.dumps(self._d.get(key, default)))

    def set(self, key, value):
        self._d[key] = json.loads(json.dumps(value))


SKILLS = [
    {"name": "stripe-refunds", "category": "billing", "description": "Use when refunding. Needs STRIPE_API_KEY."},
    {"name": "notion-sync", "category": "", "description": "Use when syncing Notion; requires an OAuth login."},
    {"name": "ascii-art", "category": "creative", "description": "Use when drawing banners."},
]


class Ctx:
    def __init__(self, settings, data_dir):
        self._s = dataclasses.asdict(settings)
        self.state = State(data_dir)
        self.skills = list(SKILLS)

    def get_config(self, key, default=None):
        return self._s.get(key, default)

    def dispatch_tool(self, name, args):
        assert name == "skills_list"
        return json.dumps({"success": True, "skills": self.skills})


@pytest.fixture
def ctx(settings, data_dir, monkeypatch):
    monkeypatch.setenv("FAL_KEY", SECRET_VALUE)          # even if a value exists in the environment ...
    monkeypatch.setenv("STRIPE_API_KEY", SECRET_VALUE)
    toolsets = {
        "web": {"available": True, "tools": ["web_search"], "requirements": ["FIRECRAWL_API_KEY"]},
        "image_gen": {"available": False, "tools": ["image_generate"], "requirements": ["FAL_KEY"]},
        "weird": {"available": False, "tools": ["w"], "requirements": [SECRET_VALUE, {"name": "WEIRD_TOKEN"},
                                                                       "lower case value"]},
        "mcp-linear": {"available": False, "tools": ["linear_x"], "requirements": ["LINEAR_API_KEY"]},
        ra.RESEARCH_TOOLSET: {"available": True, "tools": ["research_submit"]}}
    state = {"toolsets": toolsets}
    monkeypatch.setattr(ra, "_registry_toolsets", lambda: state["toolsets"])
    c = Ctx(settings, data_dir)
    c.registry_state = state
    runtime.bind(c)
    yield c
    runtime.bind(None)


def caps(refresh=False):
    raw = ra.t_capabilities({"refresh": refresh})
    assert SECRET_VALUE not in raw
    return json.loads(raw), raw


def test_missing_key_reported_by_name(ctx):
    data, raw = caps()
    by = {t["toolset"]: t for t in data["toolsets"]}
    assert by["image_gen"]["available"] is False and by["image_gen"]["needs_env"] == ["FAL_KEY"]
    assert "needs_env" not in by["web"]           # available toolsets do not nag
    missing = {m["toolset"]: m for m in data["missing_access"]}
    assert missing["image_gen"]["needs_env"] == ["FAL_KEY"]
    assert missing["mcp-linear"]["needs_env"] == ["LINEAR_API_KEY"]
    assert data["mcp_servers"][0]["server"] == "linear" and data["mcp_servers"][0]["needs_env"] == ["LINEAR_API_KEY"]


def test_values_never_appear(ctx):
    data, raw = caps()
    weird = next(t for t in data["toolsets"] if t["toolset"] == "weird")
    assert weird["needs_env"] == ["WEIRD_TOKEN"]
    assert "lower case value" not in raw and SECRET_VALUE not in raw


def test_skill_access_hints(ctx):
    data, _ = caps()
    hints = {h["skill"]: h for h in data["skill_access_hints"]}
    assert "STRIPE_API_KEY" in hints["stripe-refunds"]["mentions"]
    assert "oauth" in [m.lower() for m in hints["notion-sync"]["mentions"]]
    assert "ascii-art" not in hints


def test_cache_and_refresh(ctx):
    first, _ = caps()
    assert first["cached_minutes_ago"] == 0
    ctx.registry_state["toolsets"] = {**ctx.registry_state["toolsets"],
                                      "image_gen": {"available": True, "tools": ["image_generate"],
                                                    "requirements": ["FAL_KEY"]}}
    cached, _ = caps()
    assert "image_gen" in {m["toolset"] for m in cached["missing_access"]}
    fresh, _ = caps(refresh=True)
    assert "image_gen" not in {m["toolset"] for m in fresh["missing_access"]}
    assert fresh["cached_minutes_ago"] == 0


def test_skill_listing_failure_does_not_break_inventory(ctx):
    ctx.dispatch_tool = lambda name, args: "not json"
    data, _ = caps(refresh=True)
    assert data["ok"] and data["skill_access_hints"] == []
