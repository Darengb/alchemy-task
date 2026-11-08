"""Validator backstop for hand-edited task files.

It assigns missing task IDs and schema versions (one-line edits that keep
every other byte) and reports problems. It never rewrites user content.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import taskfile as tf
from .locks import task_lock
from .store import TaskStore

_KNOWN_STATUSES = set(tf.STATUSES) | tf.CLOSED_STATUSES


def validate(store: TaskStore, *, apply: bool = False) -> dict[str, Any]:
    scan = store.scan()
    report: dict[str, Any] = {
        "tasks": len(scan.tasks),
        "fixed_identity": [],
        "needs_identity": [],
        "duplicate_task_ids": {},
        "unsupported": [],
        "malformed": scan.errors,
        "unknown_status": [],
        "missing_due": 0,
        "done_without_completed": [],
        "area_mismatch": [],
        "untagged_in_task_folders": [store.rel(p) for p in scan.untagged][:50],
    }
    by_id: dict[str, list[str]] = defaultdict(list)
    changed_paths: list[str] = []
    for doc in scan.tasks:
        rel = store.rel(doc.path)
        fm = doc.fm
        ok, why = tf.writable(fm)
        if not ok:
            report["unsupported"].append({"path": rel, "error": why})
        if tf.valid_task_id(fm.get("task_id")):
            by_id[fm["task_id"]].append(rel)
        elif ok:
            if apply:
                fixed = _fill_identity(store, doc)
                if fixed:
                    report["fixed_identity"].append({"path": rel, "task_id": fixed})
                    by_id[fixed].append(rel)
                    changed_paths.append(rel)
            else:
                report["needs_identity"].append(rel)
        if ok and tf.task_id_state(fm) == "valid" and tf.schema_state(fm) == "missing":
            if apply:
                if _fill_identity(store, doc):
                    changed_paths.append(rel)
                    report["fixed_identity"].append({"path": rel, "task_id": fm["task_id"]})
            else:
                report["needs_identity"].append(rel)
        status = str(fm.get("status") or "").strip().lower()
        if status not in _KNOWN_STATUSES:
            report["unknown_status"].append({"path": rel, "status": fm.get("status")})
        if not tf.norm_date(fm.get("due")) and status not in tf.CLOSED_STATUSES:
            report["missing_due"] += 1
        if status == "done" and not tf.norm_date(fm.get("completed")) and not fm.get("completedDate"):
            report["done_without_completed"].append(rel)
        folder_area = store.area_of(doc.path)
        if folder_area and fm.get("area") and str(fm.get("area")) != folder_area:
            report["area_mismatch"].append({"path": rel, "area": fm.get("area"), "folder": folder_area})
    report["duplicate_task_ids"] = {k: v for k, v in by_id.items() if len(v) > 1}
    report["changed_paths"] = changed_paths
    report["problems"] = sum(len(report[k]) for k in (
        "unsupported", "malformed", "unknown_status", "done_without_completed", "area_mismatch")) + \
        len(report["duplicate_task_ids"]) + len(report["needs_identity"])
    return report


def _fill_identity(store: TaskStore, doc: tf.TaskDoc) -> str | None:
    with task_lock(store.data_dir, doc.task_id, doc.path):
        fresh = tf.parse_file(doc.path)
        text = fresh.raw.decode("utf-8")
        new_text, tid = tf.fill_identity_text(text)
        if tid is None or new_text == text:
            return None
        try:
            tf.atomic_write(doc.path, new_text.encode("utf-8"), expect=fresh.raw)
        except tf.ConcurrentEditError:
            return None
        return tid


def summarize(report: dict[str, Any]) -> str:
    lines = [f"{report['tasks']} tasks checked."]
    if report["fixed_identity"]:
        lines.append(f"Assigned IDs to {len(report['fixed_identity'])} task(s).")
    labels = {
        "needs_identity": "need an ID (run with apply)",
        "unsupported": "have an unsupported schema or malformed ID (left untouched)",
        "malformed": "could not be parsed",
        "unknown_status": "have an unknown status",
        "done_without_completed": "are done without a completed date",
        "area_mismatch": "sit in a different area folder than their area field",
    }
    for key, label in labels.items():
        if report[key]:
            lines.append(f"{len(report[key])} {label}.")
    if report["duplicate_task_ids"]:
        lines.append(f"{len(report['duplicate_task_ids'])} task ID(s) are used by more than one file.")
    if report["untagged_in_task_folders"]:
        lines.append(f"{len(report['untagged_in_task_folders'])} note(s) in task folders lack the task tag (ignored).")
    if report["problems"] == 0:
        lines.append("No problems found.")
    return " ".join(lines)
