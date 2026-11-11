"""Research model setting: config, setup save, launch, failure handling."""
from __future__ import annotations

import json

from alchemy_task.core.config import Settings

from test_setup import call, home, make_ctx  # noqa: F401


def test_config_round_trip_and_defaults():
    s = Settings.load(lambda k, d: {}.get(k, d))
    assert s.research_model == "" and s.research_provider == ""
    s = Settings.load(lambda k, d: {"research_model": "  deepseek/deepseek-v4-flash ",
                                     "research_provider": " openrouter "}.get(k, d))
    assert s.research_model == "deepseek/deepseek-v4-flash" and s.research_provider == "openrouter"


def test_setup_save_status_and_clear(home, workspace, data_dir):  # noqa: F811
    ctx = make_ctx(data_dir, workspace_root=str(workspace))
    st = call(action="status")
    assert st["receipt"]["research"]["model"] is None
    assert "Research model: main model" in st["text"]
    out = call(action="save", research_model=" glm-5-flash ", research_provider="openrouter")
    assert out["ok"], out
    assert ctx._s["research_model"] == "glm-5-flash" and ctx._s["research_provider"] == "openrouter"
    st = call(action="status")
    assert st["receipt"]["research"]["model"] == "glm-5-flash"
    assert st["receipt"]["research"]["provider"] == "openrouter"
    assert "Research model: glm-5-flash (openrouter)" in st["text"]
    out = call(action="save", research_model="", research_provider="")
    assert out["ok"] and ctx._s["research_model"] == "" and ctx._s["research_provider"] == ""
    assert "Research model: main model" in call(action="status")["text"]
    bad = call(action="save", research_model="x" * 201)
    assert not bad.get("ok") and "research_model" in bad["message"]
