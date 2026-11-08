"""Portable typed identities adapted from the established daily helper."""
from __future__ import annotations
import contextlib
import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse
MAX_SOURCE_COMPONENT_CHARS = 256
COMPONENT = DOSSIER_COMPONENT = re.compile(r"[A-Za-z0-9._-]+")
MAX_STRING_CHARS = 4000
TASKNOTE_RELATIVE_PATH = re.compile(r"(?:[A-Za-z0-9][A-Za-z0-9._-]*/)+[A-Za-z0-9][A-Za-z0-9._-]*\.md")
class UserError(Exception):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details

def _component(value: Any, label: str, pattern: re.Pattern[str] = COMPONENT) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > MAX_SOURCE_COMPONENT_CHARS or not pattern.fullmatch(value):
        raise UserError(f"invalid {label}")
    return value

def canonical_tasknote_relative_path(value: Any) -> str:
    if (type(value) is not str or len(value) > MAX_STRING_CHARS
            or not TASKNOTE_RELATIVE_PATH.fullmatch(value)):
        raise UserError(
            "existing_task_candidates.path must be a canonical vault-relative "
            "TaskNote path: areas/<area>/tasks/<file>.md"
        )
    return value

def _notion(value: Any) -> str:
    if type(value) is not str:
        raise UserError("invalid Notion page id")
    if not re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value):
        raise UserError("Notion page_id must be a canonical UUID")
    compact = value.replace("-", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", compact):
        raise UserError("Notion page_id must be a canonical UUID")
    return f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}".lower()

def canonical_source_id(source: Any) -> str:
    """Validate and normalize one complete typed source identity."""
    if type(source) is str:
        if source != source.strip():
            raise UserError("source identity whitespace is invalid")
        value = source
        parts = value.split(":")
        if parts[0] == "slack" and len(parts) in (4, 5):
            for index, part in enumerate(parts[1:], 1):
                _component(part, f"Slack component {index}")
            return value
        if parts[0] == "gmail" and len(parts) in (3, 4):
            for index, part in enumerate(parts[1:], 1):
                _component(part, f"Gmail component {index}")
            return value
        if parts[0] == "source" and len(parts) in (5, 6):
            for part in parts[1:]: _component(part, "generic source component")
            return value
        if parts[0] == "notion" and len(parts) == 2:
            return f"notion:{_notion(parts[1])}"
        if parts[0] == "dossier" and len(parts) == 2:
            return f"dossier:{_component(parts[1], 'dossier id', DOSSIER_COMPONENT)}"
        raise UserError(f"malformed canonical source id: {source!r}")
    if not isinstance(source, dict):
        raise UserError("source id must be a typed object")
    unknown = set(source) - {"type", "identity", "workspace_id", "team_id", "workspace", "channel_id", "thread_root_ts", "message_ts", "account_slug", "account", "thread_id", "message_id", "page_id", "dossier_id", "source_key", "account_key", "object_kind", "object_id"}
    if unknown: raise UserError(f"unknown source identity keys: {sorted(unknown)}")
    kind = _component(source.get("type"), "source type").lower()
    identity = source.get("identity")
    if identity is not None:
        if not isinstance(identity, dict) or set(source) != {"type", "identity"}:
            raise UserError("typed identity must contain only type and identity")
        if "type" in identity:
            raise UserError("identity object must not repeat source type")
        source = {"type": kind, **identity}
    if kind == "source":
        required = {"type", "source_key", "account_key", "object_kind", "object_id"}
        if not required <= set(source) or set(source) - required - {"message_id"}:
            raise UserError("generic source requires complete scoped identity")
        fields = ["source_key", "account_key", "object_kind", "object_id"]
        if "message_id" in source: fields.append("message_id")
        return ":".join(["source", *[_component(source[k], k) for k in fields]])
    if kind == "slack":
        workspace_keys = set(source) & {"workspace_id", "team_id", "workspace"}
        allowed = {"type", "channel_id", "thread_root_ts", "message_ts", *workspace_keys}
        if len(workspace_keys) != 1 or set(source) - allowed:
            raise UserError("Slack identity has unknown or ambiguous components")
        workspace = source.get("workspace_id", source.get("team_id", source.get("workspace")))
        parts = ["slack", _component(workspace, "Slack workspace"), _component(source.get("channel_id"), "Slack channel"), _component(source.get("thread_root_ts"), "Slack root timestamp")]
        if "message_ts" in source:
            parts.append(_component(source["message_ts"], "Slack message timestamp"))
        return ":".join(parts)
    if kind == "gmail":
        account_keys = set(source) & {"account_slug", "account"}
        allowed = {"type", "thread_id", "message_id", *account_keys}
        if len(account_keys) != 1 or set(source) - allowed:
            raise UserError("Gmail identity has unknown or ambiguous components")
        account = source.get("account_slug", source.get("account"))
        parts = ["gmail", _component(account, "Gmail account"), _component(source.get("thread_id"), "Gmail thread")]
        if "message_id" in source:
            parts.append(_component(source["message_id"], "Gmail message"))
        return ":".join(parts)
    if kind == "notion":
        if set(source) != {"type", "page_id"}: raise UserError("Notion identity requires exactly page_id")
        return f"notion:{_notion(source.get('page_id'))}"
    if kind == "dossier":
        if set(source) != {"type", "dossier_id"}: raise UserError("dossier identity requires exactly dossier_id")
        return f"dossier:{_component(source.get('dossier_id'), 'dossier id', DOSSIER_COMPONENT)}"
    raise UserError(f"unknown source type: {kind!r}")

def source_identity_covers(assigned: str, reported: str) -> bool:
    """Return whether a reported identity preserves or refines an assigned source."""
    assigned, reported = canonical_source_id(assigned), canonical_source_id(reported)
    if assigned == reported:
        return True
    assigned_parts = assigned.split(":")
    reported_parts = reported.split(":")
    if assigned_parts[0] == "slack" and len(assigned_parts) == 4 and len(reported_parts) == 5:
        return reported_parts[:4] == assigned_parts
    if assigned_parts[0] == "gmail" and len(assigned_parts) == 3 and len(reported_parts) == 4:
        return reported_parts[:3] == assigned_parts
    if assigned_parts[0] == "source" and len(assigned_parts) == 5 and len(reported_parts) == 6:
        return reported_parts[:5] == assigned_parts
    return False

def candidate_id(source_ids: list[Any]) -> str:
    if not isinstance(source_ids, list):
        raise UserError("source_ids must be a list")
    ids = sorted(set(canonical_source_id(x) for x in source_ids))
    if not ids:
        raise UserError("candidate requires at least one typed source id")
    digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()[:20]
    return f"c_{digest}"

def workstream_id(parent_candidate_id: str, source_ids: list[Any], *, action_id: str | None = None) -> str:
    """Derive a stable unit identity from its assignment and decisive sources."""
    ids = sorted(set(canonical_source_id(x) for x in source_ids))
    if not ids:
        raise UserError("workstream requires at least one typed source id")
    material = [parent_candidate_id, ids]
    if action_id is not None: material.append(_component(action_id, "action id"))
    digest = hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()[:20]
    return f"w_{digest}"


def is_message_refinement(identity: str) -> bool:
    parts = canonical_source_id(identity).split(":")
    return (parts[0], len(parts)) in {("slack", 5), ("gmail", 4), ("source", 6)}


def freeze_actions(parent_id: str, source_ids: list[Any], anchors: list[dict[str, str]], *, existing: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Freeze parent-verified anchors. Changed anchors require explicit reconciliation.

    The caller supplies verified locator/outcome pairs, not raw child claims.
    Existing entries may be carried forward; an existing locator cannot be re-keyed.
    """
    sources = sorted(set(canonical_source_id(x) for x in source_ids))
    if not sources or not isinstance(anchors, list) or not anchors or len(anchors) > 12:
        raise UserError("actions require sources and 1..12 anchors")
    registry = {entry["locator"]: dict(entry) for entry in existing or []}
    seen_locators, seen_outcomes = set(), set()
    for anchor in anchors:
        if not isinstance(anchor, dict) or set(anchor) != {"locator", "outcome"}:
            raise UserError("action anchor requires locator and outcome")
        locator, outcome = anchor["locator"], anchor["outcome"]
        if not isinstance(locator, str) or not re.fullmatch(r"(?:message|bullet|section|paragraph|line|item):[A-Za-z0-9._/-]{1,240}", locator):
            raise UserError("unsupported action locator")
        if not isinstance(outcome, str) or not outcome.strip() or len(outcome) > 500:
            raise UserError("invalid action outcome")
        outcome_key = " ".join(outcome.casefold().split())
        if locator in seen_locators or outcome_key in seen_outcomes:
            raise UserError("duplicate action locator or outcome")
        seen_locators.add(locator); seen_outcomes.add(outcome_key)
        material = [parent_id, sources, locator, outcome_key]
        action_id = "a_" + hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()[:20]
        entry = {"locator": locator, "outcome": outcome, "action_id": action_id, "source_ids": sources}
        if locator in registry and registry[locator] != entry:
            raise UserError("changed action anchor requires semantic reconciliation")
        registry[locator] = entry
    if len({" ".join(x["outcome"].casefold().split()) for x in registry.values()}) != len(registry):
        raise UserError("duplicate frozen outcome")
    return sorted(registry.values(), key=lambda x: x["locator"])


def url_identities(text: str, *, slack_workspaces: dict[str, str] | None = None) -> set[str]:
    """Extract URLs only with confirmed Slack host/workspace mapping."""
    found = set()
    for url in re.findall(r"https?://[^\s)\]>]+", text):
        parsed = urlparse(url)
        match = re.fullmatch(r"/archives/([A-Za-z0-9._-]+)/p(\d+)", parsed.path)
        if match and parsed.hostname in (slack_workspaces or {}):
            channel, digits = match.groups()
            message = f"{digits[:-6]}.{digits[-6:]}" if len(digits) > 6 else digits
            root = parse_qs(parsed.query).get("thread_ts", [message])[0]
            with contextlib.suppress(UserError):
                base = canonical_source_id({"type": "slack", "workspace_id": slack_workspaces[parsed.hostname], "channel_id": channel, "thread_root_ts": root})
                found.update([base, canonical_source_id(base + ":" + message)])
        if parsed.hostname in {"notion.so", "www.notion.so"}:
            for page in re.findall(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?![0-9a-fA-F])", parsed.path):
                found.add(canonical_source_id("notion:" + page))
    return found


def extract_identities(value: Any, *, slack_workspaces: dict[str, str] | None = None) -> set[str]:
    """Boundary-delimited legacy evidence, never automatic related-context authority."""
    found = set()
    if isinstance(value, dict):
        if "type" in value:
            with contextlib.suppress(UserError): found.add(canonical_source_id(value))
        for child in value.values(): found.update(extract_identities(child, slack_workspaces=slack_workspaces))
    elif isinstance(value, list):
        for child in value: found.update(extract_identities(child, slack_workspaces=slack_workspaces))
    elif isinstance(value, str):
        for token in re.findall(r"(?<![A-Za-z0-9_.:-])(?:slack|gmail|notion|dossier|source):[A-Za-z0-9_.:-]+(?![A-Za-z0-9_.:-])", value):
            with contextlib.suppress(UserError): found.add(canonical_source_id(token))
        found.update(url_identities(value, slack_workspaces=slack_workspaces))
    return found
