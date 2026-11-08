#!/usr/bin/env python3
"""Shared rendering and managed-block helpers for TaskNote dossiers."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse
from .discovery_identity import canonical_source_id, _component, UserError


class DossierError(ValueError):
    """A dossier payload or managed block is unsafe or malformed."""


GENERIC_FIELDS = {
    "recommended_approach",
    "useful_context",
    "dependencies_and_risks",
    "open_questions",
    "sources",
}
def content_revision(value: Any) -> str:
    """Return a stable revision for JSON-shaped dossier content."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bounded_strings(value: Any, field: str, *, limit: int = 50, chars: int = 2000) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise DossierError(f"{field} must be a bounded list")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise DossierError(f"{field} items must be strings")
        text = item.strip()
        if not text:
            continue
        if len(text) > chars:
            raise DossierError(f"{field} item is too long")
        output.append(text)
    return output


def _safe_source(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"title", "url", "relevance"}:
        raise DossierError("source has wrong fields")
    source: dict[str, str] = {}
    for field in ("title", "url", "relevance"):
        item = value[field]
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 2000:
            raise DossierError(f"source {field} is invalid")
        source[field] = item.strip()
    parsed = urlparse(source["url"])
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DossierError("source URL must be http or https")
    return source


def normalize_generic_research(payload: Any) -> dict[str, Any]:
    """Validate and normalize the compact generic research contract."""
    if not isinstance(payload, Mapping) or set(payload) != GENERIC_FIELDS:
        raise DossierError("research payload has wrong fields")
    normalized: dict[str, Any] = {
        field: _bounded_strings(payload[field], field)
        for field in (
            "recommended_approach",
            "useful_context",
            "dependencies_and_risks",
            "open_questions",
        )
    }
    sources = payload["sources"]
    if not isinstance(sources, list) or len(sources) > 50:
        raise DossierError("sources must be a bounded list")
    normalized["sources"] = [_safe_source(source) for source in sources]
    return normalized


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def render_generic_dossier(payload: Any) -> tuple[str, str]:
    """Render one generic TaskNote research dossier."""
    normalized = normalize_generic_research(payload)
    revision = content_revision(normalized)
    sections = [
        "## Research dossier",
        f"**Content revision:** `{revision}`",
    ]
    for title, field in (
        ("Recommended approach", "recommended_approach"),
        ("Useful context", "useful_context"),
        ("Dependencies and risks", "dependencies_and_risks"),
        ("Open questions", "open_questions"),
    ):
        values = normalized[field]
        if values:
            sections.append(f"### {title}\n\n{_bullets(values)}")
    sources = normalized["sources"]
    if sources:
        source_lines = [
            f"- [{source['title']}]({source['url']}) - {source['relevance']}"
            for source in sources
        ]
        sections.append("### Sources\n\n" + "\n".join(source_lines))
    body = "\n\n".join(sections)
    block = (
        "<!-- task-research-dossier:start -->\n"
        f"{body}\n"
        "<!-- task-research-dossier:end -->"
    )
    return revision, block


def render_discovery_dossier(
    research: Mapping[str, Any],
    *,
    dossier_id: str,
    candidate_source_ids: list[Any],
) -> tuple[str, str]:
    """Render the established inline discovery dossier format from validated data."""
    try:
        _component(dossier_id, "dossier id")
        decisive = [canonical_source_id(x) for x in candidate_source_ids]
        related = [canonical_source_id(x) for x in research.get("related_source_ids", [])]
    except UserError as exc:
        raise DossierError(str(exc)) from exc
    revision = content_revision({key: research[key] for key in sorted(research)})

    def bullets(values: list[Any]) -> str:
        return "\n".join(f"- {value}" for value in values) if values else "- None recorded"

    owners = [
        f"{owner['name']} - {owner['role']}"
        for owner in research["owner_and_collaborators"]
    ]
    decisions = research["decisions_and_open_questions"]
    consulted = [
        f"{source['source']} - {source['result']}"
        for source in research["sources_consulted"]
    ]
    sources = list(
        dict.fromkeys(
            [
                *research["source_links"],
                *research["related_context_links"],
                *decisive,
                *consulted,
            ]
        )
    )
    summary_details = research["new_information"] or [
        research["substantive_next_action"]
    ]
    body = "\n\n".join(
        [
            "## Research Dossier",
            f"**Dossier ID:** `dossier:{dossier_id}`\n\n**Content revision:** `{revision}`",
            f"### Summary\n\n{research['title']}\n\n{bullets(summary_details)}",
            f"### Current Understanding\n\n{research['current_understanding']}",
            f"### Next Action\n\n{research['substantive_next_action']}",
            f"### Owners/Collaborators\n\n{bullets(owners)}",
            "### Decisions/Open Questions\n\n"
            f"#### Decisions\n{bullets(decisions['decisions'])}\n\n"
            f"#### Open Questions\n{bullets(decisions['open_questions'])}",
            f"### Dependencies/Risks\n\n{bullets(research['dependencies_and_risks'])}",
            f"### Implementation Context\n\n{bullets(research['implementation_context'])}",
            f"### Execution Classification\n\n{research['execution_classification']}",
            f"### Decisive Source Identities\n\n{bullets(decisive)}",
            f"### Related Source Identities\n\n{bullets(related)}",
            f"### Sources/Related Context\n\n{bullets(sources)}",
            f"### Sources Unavailable\n\n{bullets(research['sources_unavailable'])}",
        ]
    )
    block = (
        f"<!-- discovery-dossier:start {dossier_id} -->\n"
        f"{body}\n"
        f"<!-- discovery-dossier:end {dossier_id} -->"
    )
    return revision, block


def upsert_managed_block(
    body: str,
    *,
    start_marker: str,
    end_marker: str,
    block: str,
) -> tuple[str, bool]:
    """Append or replace one exact managed block while preserving other bytes."""
    if (not start_marker or not end_marker or start_marker == end_marker
            or block.count(start_marker) != 1 or block.count(end_marker) != 1
            or not block.startswith(start_marker) or not block.endswith(end_marker)
            or block.index(end_marker) < block.index(start_marker)):
        raise DossierError("malformed replacement block markers")
    starts = body.count(start_marker)
    ends = body.count(end_marker)
    if starts != ends or starts > 1:
        raise DossierError("malformed managed block markers")
    if starts == 0:
        return body.rstrip() + "\n\n" + block + "\n", True
    begin = body.index(start_marker)
    if body.index(end_marker) < begin:
        raise DossierError("reversed managed block markers")
    finish = body.index(end_marker, begin) + len(end_marker)
    if body[begin:finish] == block:
        return body, False
    return body[:begin] + block + body[finish:], True
