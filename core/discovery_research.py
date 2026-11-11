"""Daily-derived research contract; no optional validation dependency."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from .discovery_identity import (UserError, canonical_source_id, source_identity_covers,
    canonical_tasknote_relative_path, workstream_id, is_message_refinement)
RESEARCH_KEYS = {
    "candidate_id", "status", "disposition", "title", "current_understanding",
    "substantive_next_action", "owner_and_collaborators", "decisions_and_open_questions",
    "dependencies_and_risks", "implementation_context", "execution_classification",
    "exact_source_ids", "related_source_ids", "source_links", "related_context_links", "sources_consulted",
    "sources_unavailable", "existing_task_candidates", "new_information", "errors",
    "represented_candidate_ids",
}
OPTIONAL_RESEARCH_KEYS = {"existing_task_already_current", "digest_current_state", "digest_next_action", "digest_addition"}
DIGEST_FIELD_CHARS = 300
DISPOSITIONS = {"retain", "exclude_pure_chase", "exclude_resolved", "uncertain"}
EXECUTIONS = {"hermes_independent", "user_collaboration_or_approval", "other_owner_or_access", "no_action"}
ROLES = {"owner", "collaborator", "approver", "dependency"}
FORBIDDEN_KEY = re.compile(r"(?:^|_)(?:raw|body|bodies|transcript|cache|secret|token|cookie|credential|password)(?:_|$)", re.I)
CANARY = re.compile(r"(?:privacy|secret|token|transcript|raw[-_ ]?corpus)[-_ ]?canary|canary[-_ ]?(?:privacy|secret|token|transcript|raw)", re.I)
SECRET_VALUE = re.compile(r"(?:token|secret|password|cookie|authorization)\s*[:=]\s*[^\s&]+|\b(?:sk-|xox[baprs]-)[A-Za-z0-9-]{8,}", re.I)
MAX_CANDIDATES = 200
MAX_INDEX_BYTES = 256 * 1024
REQUESTED_SOURCE_IDS = 12
MAX_SOURCE_IDS = 15
MAX_TITLE_CHARS = 300
MAX_REASON_CHARS = 500
MAX_WORKSTREAMS = 12
MAX_ARRAY_ITEMS = 50
MAX_STRING_CHARS = 4000
MAX_BUNDLE_BYTES = 512 * 1024

def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()

def _str(value: Any, label: str, *, allow_empty: bool = True, limit: int = MAX_STRING_CHARS) -> str:
    if type(value) is not str or (not allow_empty and not value.strip()) or len(value) > limit:
        raise UserError(f"{label} must be a bounded string")
    return value

def _strings(value: Any, label: str) -> list[str]:
    if (not isinstance(value, list) or len(value) > MAX_ARRAY_ITEMS
            or any(type(x) is not str or len(x) > MAX_STRING_CHARS for x in value)):
        raise UserError(f"{label} must be a list of strings")
    return value

def _privacy_walk(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str or FORBIDDEN_KEY.search(key):
                raise UserError(f"forbidden privacy field at {path}.{key}")
            _privacy_walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _privacy_walk(child, f"{path}[{index}]")
    elif type(value) is str and (CANARY.search(value) or SECRET_VALUE.search(value)):
        raise UserError(f"raw-corpus canary or secret rejected at {path}")

def validate_research(payload: Any, cid: str, expected_sources: list[str]) -> dict[str, Any]:
    # Optional digest fields: older bundles without them stay valid.
    if isinstance(payload, dict): _privacy_walk(payload)
    if isinstance(payload, dict) and set(payload) & OPTIONAL_RESEARCH_KEYS:
        for key in set(payload) & OPTIONAL_RESEARCH_KEYS:
            if key == "existing_task_already_current":
                if type(payload[key]) is not bool: raise UserError(f"{key} must be a boolean")
            else:
                _str(payload[key], key, limit=DIGEST_FIELD_CHARS)
        rest = validate_research({k: v for k, v in payload.items() if k not in OPTIONAL_RESEARCH_KEYS}, cid, expected_sources)
        return {**rest, **{k: payload[k] for k in payload if k in OPTIONAL_RESEARCH_KEYS}}
    if not isinstance(payload, dict) or set(payload) != RESEARCH_KEYS:
        missing = sorted(RESEARCH_KEYS - set(payload)) if isinstance(payload, dict) else sorted(RESEARCH_KEYS)
        unknown = sorted(set(payload) - RESEARCH_KEYS) if isinstance(payload, dict) else []
        raise UserError(f"research schema keys mismatch; missing={missing}, unknown={unknown}")
    _privacy_walk(payload)
    if payload["candidate_id"] != cid or type(payload["candidate_id"]) is not str:
        raise UserError("research candidate_id does not match assigned candidate")
    if type(payload["status"]) is not str or payload["status"] not in {"complete", "incomplete", "failed"}:
        raise UserError("invalid research status")
    if type(payload["disposition"]) is not str or payload["disposition"] not in DISPOSITIONS:
        raise UserError("invalid research disposition")
    _str(payload["title"], "title", allow_empty=False, limit=MAX_TITLE_CHARS)
    for key in ("current_understanding", "substantive_next_action"):
        _str(payload[key], key)
    owners = payload["owner_and_collaborators"]
    if not isinstance(owners, list) or len(owners) > MAX_ARRAY_ITEMS: raise UserError("owner_and_collaborators must be a bounded list")
    for owner in owners:
        if not isinstance(owner, dict) or set(owner) != {"name", "role"} or type(owner["name"]) is not str or len(owner["name"]) > MAX_STRING_CHARS or type(owner["role"]) is not str or owner["role"] not in ROLES:
            raise UserError("invalid owner_and_collaborators entry")
    decisions = payload["decisions_and_open_questions"]
    if not isinstance(decisions, dict) or set(decisions) != {"decisions", "open_questions"}:
        raise UserError("invalid decisions_and_open_questions")
    _strings(decisions["decisions"], "decisions"); _strings(decisions["open_questions"], "open_questions")
    for key in ("dependencies_and_risks", "implementation_context", "source_links", "related_context_links", "sources_unavailable", "new_information", "errors"):
        _strings(payload[key], key)
    if type(payload["execution_classification"]) is not str or payload["execution_classification"] not in EXECUTIONS:
        raise UserError("invalid execution_classification")
    exact = payload["exact_source_ids"]
    if not isinstance(exact, list) or not exact or len(exact) > MAX_SOURCE_IDS or any(not isinstance(x, dict) for x in exact):
        raise UserError("exact_source_ids must be direct helper-compatible typed objects")
    canonical = [canonical_source_id(x) for x in exact]
    if any(
        not any(source_identity_covers(expected, reported) for reported in canonical)
        for expected in expected_sources
    ):
        raise UserError("exact_source_ids do not cover assigned candidate sources")
    related = payload["related_source_ids"]
    if not isinstance(related, list) or len(related) > MAX_SOURCE_IDS or any(not isinstance(x, dict) for x in related):
        raise UserError("related_source_ids must be helper-compatible typed objects")
    related_canonical = [canonical_source_id(x) for x in related]
    if len(related_canonical) != len(set(related_canonical)):
        raise UserError("related_source_ids must be unique")
    if len(canonical) + len(related_canonical) > MAX_SOURCE_IDS:
        raise UserError("workstream source identity count exceeds shared limit")
    consulted = payload["sources_consulted"]
    if (not isinstance(consulted, list) or len(consulted) > MAX_ARRAY_ITEMS
            or any(not isinstance(x, dict) or set(x) != {"source", "result"}
                   or type(x["source"]) is not str or len(x["source"]) > MAX_STRING_CHARS
                   or type(x["result"]) is not str or len(x["result"]) > MAX_STRING_CHARS for x in consulted)):
        raise UserError("invalid sources_consulted")
    existing = payload["existing_task_candidates"]
    if (not isinstance(existing, list) or len(existing) > MAX_ARRAY_ITEMS
            or any(not isinstance(x, dict) or set(x) != {"path", "match_basis"}
                   or type(x["path"]) is not str or len(x["path"]) > MAX_STRING_CHARS
                   or type(x["match_basis"]) is not str or x["match_basis"] not in {"exact", "related_only"} for x in existing)):
        raise UserError("invalid existing_task_candidates")
    for item in existing:
        canonical_tasknote_relative_path(item["path"])
    dependencies = payload["represented_candidate_ids"]
    if (not isinstance(dependencies, list) or len(dependencies) > MAX_ARRAY_ITEMS or len(dependencies) != len(set(dependencies))
            or any(type(x) is not str or not re.fullmatch(r"c_[0-9a-f]{20}", x) for x in dependencies)):
        raise UserError("represented_candidate_ids must be unique candidate IDs")
    return dict(payload)


def child_schema() -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parents[1] / 'schemas' / 'discovery-child-output.schema.json').read_text())


def _shape(value: Any, rule: dict[str, Any], root: dict[str, Any], path: str) -> None:
    """Evaluate the exact checked-in schema vocabulary, failing closed.

    This deliberately is not a general JSON Schema implementation. New schema
    keywords require extending this interpreter and its oracle regression tests.
    """
    known = {'$schema', '$id', '$defs', '$ref', 'description', 'type', 'additionalProperties', 'required', 'properties', 'items', 'maxItems', 'minItems', 'maxLength', 'minLength', 'pattern', 'uniqueItems', 'enum', 'const', 'oneOf', 'allOf', 'if', 'then'}
    if set(rule) - known:
        raise UserError('unsupported schema keywords: ' + ', '.join(sorted(set(rule) - known)))
    if '$ref' in rule:
        target = root
        ref = rule['$ref']
        if not ref.startswith('#/'):
            raise UserError('only local schema references supported')
        for key in ref[2:].split('/'):
            target = target[key.replace('~1', '/').replace('~0', '~')]
        _shape(value, target, root, path)
    if 'oneOf' in rule:
        matched = 0
        for variant in rule['oneOf']:
            try:
                _shape(value, variant, root, path)
                matched += 1
            except UserError:
                pass
        if matched != 1:
            raise UserError(f'{path}: expected exactly one typed variant')
    for nested in rule.get('allOf', []):
        _shape(value, nested, root, path)
    if 'if' in rule:
        try:
            _shape(value, rule['if'], root, path)
        except UserError:
            pass
        else:
            _shape(value, rule.get('then', {}), root, path)
    expected = rule.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool, 'null': type(None)}
    if expected and type(value) is not types[expected]:
        raise UserError(f'{path}: expected {expected}')
    if 'const' in rule and (type(value) is not type(rule['const']) or value != rule['const']):
        raise UserError(f'{path}: invalid constant')
    if 'enum' in rule and not any(type(value) is type(v) and value == v for v in rule['enum']):
        raise UserError(f'{path}: invalid enum')
    if isinstance(value, dict):
        if set(rule.get('required', [])) - set(value):
            raise UserError(f'{path}: missing required fields')
        properties = rule.get('properties', {})
        if rule.get('additionalProperties') is False and set(value) - set(properties):
            raise UserError(f'{path}: unknown fields')
        for key, nested in properties.items():
            if key in value:
                _shape(value[key], nested, root, path + '.' + key)
    if isinstance(value, list):
        if len(value) < rule.get('minItems', 0) or len(value) > rule.get('maxItems', len(value)):
            raise UserError(f'{path}: array bounds')
        if rule.get('uniqueItems') and len({json.dumps(v, sort_keys=True, ensure_ascii=False) for v in value}) != len(value):
            raise UserError(f'{path}: duplicate items')
        if 'items' in rule:
            for index, item in enumerate(value):
                _shape(item, rule['items'], root, f'{path}[{index}]')
    if isinstance(value, str):
        if len(value) < rule.get('minLength', 0) or len(value) > rule.get('maxLength', len(value)):
            raise UserError(f'{path}: string bounds')
        if 'pattern' in rule and re.search(rule['pattern'], value) is None:
            raise UserError(f'{path}: invalid pattern')


def validate_shape(payload: Any) -> dict[str, Any]:
    schema = child_schema()
    _shape(payload, schema, schema, 'bundle')
    _privacy_walk(payload)
    return copy.deepcopy(payload)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise UserError('duplicate JSON key')
        result[key] = value
    return result


def extract_json(value: str | dict[str, Any]) -> dict[str, Any]:
    """Tolerate prose/fences, not ambiguous objects, duplicates or truncation."""
    if isinstance(value, dict):
        raw = _json_bytes(value)
        if len(raw) > MAX_BUNDLE_BYTES:
            raise UserError('serialized research bundle exceeds shared limit')
        return copy.deepcopy(value)
    if type(value) is not str or len(value.encode('utf-8')) > MAX_BUNDLE_BYTES:
        raise UserError('research JSON exceeds shared limit or has wrong type')
    decoder = json.JSONDecoder(object_pairs_hook=_no_duplicate_keys, parse_constant=lambda x: (_ for _ in ()).throw(UserError('non-finite JSON')))
    objects = []
    offset = 0
    while offset < len(value):
        start = value.find('{', offset)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(value, start)
        except json.JSONDecodeError:
            offset = start + 1
            continue
        objects.append(obj)
        offset = end
    if len(objects) != 1 or not isinstance(objects[0], dict):
        raise UserError('expected one complete JSON object')
    return objects[0]


def validate_bundle(bundle: Any, cid: str, expected_sources: list[Any], *, other_sources: dict[str, list[Any]] | None = None, action_registry: list[dict[str, Any]] | None = None) -> list[tuple[str, dict[str, Any], list[str]]]:
    """Validate the entire daily bundle before materializing any independent unit.

    Return (workstream_id, normalized research, decisive canonical IDs) tuples.
    Optional registry is parent-verified, frozen against the assignment, not child
    authority. Related identities never supply assignment coverage or hashes.
    """
    bundle = extract_json(bundle)
    if bundle.get('candidate_id') != cid:
        raise UserError('research bundle must match the assigned candidate')
    workstreams = bundle.get('workstreams')
    if isinstance(workstreams, list) and len(workstreams) > MAX_WORKSTREAMS:
        raise UserError('workstream count exceeds shared limit')
    if isinstance(workstreams, list) and any(isinstance(w, dict) and w.get('research_status') in ('insufficient', 'failed') for w in workstreams):
        raise UserError('delivery-ineligible research_status requires a fresh research retry')
    # Preserve the helper error for the combined identity ceiling.
    for w in workstreams if isinstance(workstreams, list) else []:
        deps = w.get('represented_candidate_ids') if isinstance(w, dict) else None
        if isinstance(deps, list) and all(isinstance(x, str) for x in deps) and len(deps) != len(set(deps)):
            raise UserError('represented_candidate_ids must be unique candidate IDs')
        if isinstance(w, dict) and isinstance(w.get('exact_source_ids'), list) and isinstance(w.get('related_source_ids'), list) and len(w['exact_source_ids']) + len(w['related_source_ids']) > MAX_SOURCE_IDS:
            raise UserError('workstream source identity count exceeds shared limit')
    validate_shape(bundle)
    expected = [canonical_source_id(x) for x in expected_sources]
    others = {key: [canonical_source_id(x) for x in value] for key, value in (other_sources or {}).items() if key != cid}
    valid_units, seen_ids, seen_decisive_sets, seen_keys = [], set(), [], set()
    action_ids = set()
    for supplied in workstreams:
        exact = supplied['exact_source_ids']
        canonical = [canonical_source_id(x) for x in exact]
        if len(canonical) != len(set(canonical)):
            raise UserError('workstream exact_source_ids must be unique')
        if any(not any(source_identity_covers(assigned, reported) for assigned in expected) for reported in canonical):
            raise UserError('workstream source is outside assigned thread identity')
        if len(workstreams) > 1 and not any(is_message_refinement(x) for x in canonical):
            raise UserError('each decomposed workstream requires a decisive message identity')
        normalized = copy.deepcopy(supplied)
        action_id = None
        if 'action_key' in normalized:
            key = normalized.pop('action_key')
            anchor = normalized.pop('action_anchor')
            relation = normalized.pop('action_relation')
            if key in seen_keys:
                raise UserError('duplicate action key')
            seen_keys.add(key)
            entries = [entry for entry in action_registry or [] if entry.get('locator') == anchor['locator'] and entry.get('outcome') == anchor['outcome'] and sorted(entry.get('source_ids', [])) == sorted(set(expected))]
            if len(entries) != 1:
                raise UserError('action anchor lacks frozen parent verification')
            action_id = entries[0]['action_id']
            if action_id in action_ids:
                raise UserError('duplicate action outcome')
            if len(workstreams) > 1 and relation != 'independent':
                raise UserError('same_action must be reconciled before bundle acceptance')
            action_ids.add(action_id)
        wid = workstream_id(cid, exact, action_id=action_id) if action_id else workstream_id(cid, exact)
        if wid in seen_ids:
            raise UserError('duplicate workstream decisive identity')
        for previous, previous_action in seen_decisive_sets:
            overlap = any(source_identity_covers(left, right) or source_identity_covers(right, left) for left in previous for right in canonical)
            if overlap and not (action_id and previous_action and action_id != previous_action and set(previous) == set(canonical)):
                raise UserError('overlapping workstream decisive identity sets')
        for other_id, represented in others.items():
            if any(source_identity_covers(other, reported) or source_identity_covers(reported, other) for other in represented for reported in canonical):
                raise UserError(f'workstream identity is represented by another candidate: {other_id}')
        status = normalized.pop('research_status')
        normalized['status'] = {'sufficient': 'complete', 'insufficient': 'incomplete', 'failed': 'failed'}[status]
        normalized['represented_candidate_ids'] = [dep for dep in normalized['represented_candidate_ids'] if dep != cid]
        payload = validate_research({'candidate_id': wid, **normalized}, wid, expected)
        invalid = sorted(set(payload['represented_candidate_ids']) - set(others))
        if invalid:
            raise UserError('represented candidate is not a valid shared-index survivor: ' + ', '.join(invalid))
        if action_id:
            payload.update(action_id=action_id, action_anchor=supplied['action_anchor'], action_relation=supplied['action_relation'])
        valid_units.append((wid, payload, canonical))
        seen_ids.add(wid)
        seen_decisive_sets.append((canonical, action_id))
    return valid_units
