"""Research workers can read the user's whole skills listing, page by page, and reference files."""
from __future__ import annotations

import dataclasses
import json

import pytest

from alchemy_task import research_agent as ra
from alchemy_task import runtime


def _skills(n=300):
    # Realistic-ish listing: varied categories and descriptions, total well over 54,000 chars.
    out = []
    for i in range(n):
        out.append({"name": f"skill-{i:03d}", "category": f"cat-{i % 7}",
                    "description": f"Use when doing thing number {i}. " + "x" * (120 + (i * 37) % 160),
                    "tags": ["a", "b"], "path": f"/somewhere/skill-{i:03d}/SKILL.md"})
    return out


class State:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir
        self._d = {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def set(self, key, value):
        self._d[key] = value


class Ctx:
    def __init__(self, settings, skills, files, data_dir=None):
        self._s = dataclasses.asdict(settings)
        self.state = State(data_dir)
        self.skills, self.files, self.calls = skills, files, []

    def get_config(self, key, default=None):
        return self._s.get(key, default)

    def dispatch_tool(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "skills_list":
            sk = self.skills
            if args.get("category"):
                sk = [s for s in sk if s["category"] == args["category"]]
            return json.dumps({"success": True, "skills": sk, "count": len(sk),
                               "categories": sorted({s["category"] for s in sk})})
        if name == "skill_view":
            key = (args.get("name"), args.get("file_path"))
            return json.dumps({"success": True, "content": self.files.get(key, "missing")})
        raise AssertionError(name)


@pytest.fixture
def ctx(settings, data_dir):
    files = {("skill-001", None): "main body", ("skill-001", "references/api.md"): "REFERENCE BODY"}
    c = Ctx(settings, _skills(), files, data_dir)
    runtime.bind(c)
    yield c
    runtime.bind(None)


def test_fixture_is_bigger_than_the_old_cut(ctx):
    assert len(json.dumps({"skills": ctx.skills})) > 54000


def test_paging_returns_every_skill_once_with_total(ctx):
    seen, page, pages_seen = [], 1, 0
    while page:
        raw = ra.t_skills_list({"page": page})
        assert len(raw) < 20000, "each page must stay well under the tool-result size"
        data = json.loads(raw)  # never cut mid-JSON
        assert data["ok"] and data["total"] == 300 and data["page"] == page
        for entry in data["skills"]:
            assert set(entry) <= {"name", "category", "description"}
            assert entry["description"].startswith("Use when")
        seen.extend(e["name"] for e in data["skills"])
        pages_seen += 1
        assert data["pages"] >= pages_seen
        page = data["next_page"]
    assert pages_seen > 1 and pages_seen == data["pages"]
    assert sorted(seen) == sorted(s["name"] for s in ctx.skills)
    assert len(seen) == len(set(seen))


def test_entries_are_complete_not_cut(ctx):
    by_name = {s["name"]: s for s in ctx.skills}
    page = 1
    while page:
        data = json.loads(ra.t_skills_list({"page": page}))
        for e in data["skills"]:
            assert e["description"] == by_name[e["name"]]["description"]
            assert e["category"] == by_name[e["name"]]["category"]
        page = data["next_page"]


def test_default_is_first_page_and_out_of_range_is_clean(ctx):
    first = json.loads(ra.t_skills_list({}))
    assert first["page"] == 1 and first["next_page"] == 2 and "page" in first["hint"].lower()
    beyond = json.loads(ra.t_skills_list({"page": 999}))
    assert beyond["skills"] == [] and beyond["next_page"] is None and beyond["total"] == 300
    bad = json.loads(ra.t_skills_list({"page": "zz"}))
    assert bad["page"] == 1


def test_category_filter_passes_through(ctx):
    data = json.loads(ra.t_skills_list({"category": "cat-3"}))
    assert ctx.calls[-1] == ("skills_list", {"category": "cat-3"})
    assert data["total"] == len([s for s in ctx.skills if s["category"] == "cat-3"])


def test_non_json_listing_is_paged_not_cut(ctx):
    big = "line\n" * 20000
    ctx.dispatch_tool = lambda name, args: big
    got, page = "", 1
    while page:
        data = json.loads(ra.t_skills_list({"page": page}))
        got += data["raw"]
        page = data["next_page"]
    assert got == big


def test_reference_file_is_readable(ctx):
    data = json.loads(ra.t_skill_view({"name": "skill-001", "file_path": "references/api.md"}))
    assert data["content"] == "REFERENCE BODY"
    assert ctx.calls[-1] == ("skill_view", {"name": "skill-001", "file_path": "references/api.md"})


def test_long_skill_view_is_paged_not_cut(ctx):
    big = "R" * 70000
    ctx.files[("skill-002", "references/big.md")] = big
    full = json.dumps({"success": True, "content": big})
    got, offset = "", 0
    while offset is not None:
        data = json.loads(ra.t_skill_view({"name": "skill-002", "file_path": "references/big.md", "offset": offset}))
        assert data["total_chars"] == len(full)
        got += data["content"]
        offset = data["next_offset"]
    assert got == full


def test_schema_tells_worker_to_page():
    schema = next(s for s, _ in ra.RESEARCH_TOOLS if s["name"] == "research_skills_list")
    assert "page" in schema["parameters"]["properties"]
    assert "next_page" in schema["description"]
    view = next(s for s, _ in ra.RESEARCH_TOOLS if s["name"] == "research_skill_view")
    assert "file_path" in view["parameters"]["properties"]
    assert "references/" in view["parameters"]["properties"]["file_path"].get("description", "")
