"""Task store: find, create and update Markdown tasks in the configured workspace."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import taskfile as tf
from .config import ConfigError, Settings, validate_area_name
from .locks import task_lock

try:  # Loading only; rendering always uses the pure SafeDumper for byte-stable output.
    _Loader = yaml.CSafeLoader  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover
    _Loader = yaml.SafeLoader

_FILENAME_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
PROTECTED_KEYS = {"task_id", "schema_version", "enrichment", "google_tasks", "google_tasks_conflicts",
                  "google_date_cleared", "dossier_ids", "reminders"}


class NeedsInput(Exception):
    """The agent must ask the user (or fix its call) before this can proceed."""

    def __init__(self, kind: str, message: str, **data: Any) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.data = data


@dataclass
class ScanResult:
    tasks: list[tf.TaskDoc] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    untagged: list[Path] = field(default_factory=list)


_parse_cache: dict[str, tuple[int, int, tf.TaskDoc | Exception]] = {}


def _cached_parse(path: Path) -> tf.TaskDoc:
    st = path.stat()
    key = str(path)
    hit = _parse_cache.get(key)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        if isinstance(hit[2], Exception):
            raise hit[2]
        return hit[2]
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if not text.startswith("---\n"):
            raise tf.TaskFormatError("no frontmatter")
        try:
            _, raw_fm, body = text.split("---", 2)
        except ValueError as exc:
            raise tf.TaskFormatError("unterminated frontmatter") from exc
        try:
            fm = yaml.load(raw_fm, Loader=_Loader) or {}
        except yaml.YAMLError as exc:
            raise tf.TaskFormatError("invalid YAML frontmatter") from exc
        if not isinstance(fm, dict):
            raise tf.TaskFormatError("frontmatter is not a mapping")
        doc: tf.TaskDoc | Exception = tf.TaskDoc(path=path, fm=fm, body=body.lstrip("\n"), raw=raw)
    except (tf.TaskFormatError, UnicodeDecodeError) as exc:
        doc = tf.TaskFormatError(str(exc))
    _parse_cache[key] = (st.st_mtime_ns, st.st_size, doc)
    if isinstance(doc, Exception):
        raise doc
    return doc


class TaskStore:
    def __init__(self, settings: Settings, data_dir: Path) -> None:
        self.s = settings
        self.data_dir = data_dir

    # ------------------------------------------------------------ discovery

    @property
    def root(self) -> Path:
        return self.s.root()

    def rel(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.root))

    def task_dirs(self) -> list[tuple[str, Path]]:
        return [(a, self.s.area_dir(a)) for a in self.s.known_areas()]

    def task_files(self) -> Iterable[Path]:
        for _, folder in self.task_dirs():
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*.md")):
                rel_parts = path.relative_to(folder).parts
                if any(p.startswith(".") for p in rel_parts) or path.name.lower() == "template.md":
                    continue
                yield path

    def scan(self) -> ScanResult:
        out = ScanResult()
        for path in self.task_files():
            try:
                doc = _cached_parse(path)
            except tf.TaskFormatError as exc:
                out.errors.append({"path": self.rel(path), "error": str(exc)})
                continue
            if tf.has_task_tag(doc.fm):
                out.tasks.append(doc)
            else:
                out.untagged.append(path)
        return out

    def area_of(self, path: Path) -> str | None:
        for area, folder in self.task_dirs():
            try:
                path.resolve().relative_to(folder.resolve())
                return area
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------ lookup

    def resolve(self, ref: str) -> tf.TaskDoc:
        """Find one task by task_id, workspace-relative path or exact title."""
        ref = str(ref or "").strip()
        if not ref:
            raise NeedsInput("task", "Say which task: give its task_id (from task_find) or exact title.")
        tasks = self.scan().tasks
        if tf.valid_task_id(ref):
            hits = [t for t in tasks if t.fm.get("task_id") == ref]
        elif ref.endswith(".md"):
            target = (self.root / ref).resolve() if not ref.startswith("/") else Path(ref).resolve()
            hits = [t for t in tasks if t.path.resolve() == target]
        else:
            hits = [t for t in tasks if tf.norm_title(t.title) == tf.norm_title(ref)]
            if not hits:
                ranked = self._rank(tasks, ref)[:5]
                raise NeedsInput("task", f"No task titled {ref!r}. Closest matches are listed; retry with a task_id.",
                                 candidates=[self.summary(t) for _, t in ranked])
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise NeedsInput("task", f"No task matches {ref!r}. Use task_find to look it up.")
        raise NeedsInput("task", f"{len(hits)} tasks match {ref!r}; retry with one task_id.",
                         candidates=[self.summary(t) for t in hits])

    def _rank(self, tasks: list[tf.TaskDoc], query: str) -> list[tuple[float, tf.TaskDoc]]:
        q = tf.norm_title(query)
        ranked = []
        for t in tasks:
            title = tf.norm_title(t.title)
            score = tf.title_similarity(query, t.title)
            if q and q in title:
                score += 0.5
            elif q and q in tf.norm_title(str(t.fm.get("project") or "")):
                score += 0.2
            if score > 0:
                ranked.append((score, t))
        ranked.sort(key=lambda x: (-x[0], _due_key(x[1])))
        return ranked

    def find(self, *, query: str = "", task_id: str = "", area: str = "", status: str = "open",
             due_before: str = "", due_after: str = "", limit: int = 20) -> list[tf.TaskDoc]:
        tasks = self.scan().tasks
        if task_id:
            return [t for t in tasks if t.fm.get("task_id") == task_id.strip()]
        if area:
            area = validate_area_name(area)
            tasks = [t for t in tasks if str(t.fm.get("area") or self.area_of(t.path) or "") == area]
        status = (status or "open").strip().lower()
        if status == "open":
            tasks = [t for t in tasks if not t.is_closed]
        elif status == "closed":
            tasks = [t for t in tasks if t.is_closed]
        elif status != "any":
            tasks = [t for t in tasks if t.status == status]
        before = tf.validate_date(due_before, "due_before")
        after = tf.validate_date(due_after, "due_after")
        if before:
            tasks = [t for t in tasks if (tf.norm_date(t.fm.get("due")) or "9999") <= before]
        if after:
            tasks = [t for t in tasks if (tf.norm_date(t.fm.get("due")) or "0000") >= after]
        if query.strip():
            ordered = [t for _, t in self._rank(tasks, query)]
        else:
            ordered = sorted(tasks, key=_due_key)
        return ordered[: max(1, min(int(limit or 20), 100))]

    def summary(self, doc: tf.TaskDoc, *, include_body: bool = False) -> dict[str, Any]:
        fm = doc.fm
        enrichment = fm.get("enrichment") if isinstance(fm.get("enrichment"), dict) else None
        out: dict[str, Any] = {
            "task_id": doc.task_id,
            "title": doc.title,
            "status": fm.get("status"),
            "priority": fm.get("priority"),
            "area": fm.get("area") or self.area_of(doc.path),
            "due": tf.norm_date(fm.get("due")),
            "scheduled": tf.norm_date(fm.get("scheduled")),
            "path": self.rel(doc.path),
        }
        if fm.get("project"):
            out["project"] = fm.get("project")
        if tf.norm_date(fm.get("completed")):
            out["completed"] = tf.norm_date(fm.get("completed"))
        out["research"] = (enrichment or {}).get("status") or "none"
        state = current_state_text(doc.body)
        if state:
            out["current_state"] = state[:600]
        if include_body:
            body = doc.body
            out["body"] = body if len(body) <= 12000 else body[:12000] + "\n…(truncated)"
        return out

    # ------------------------------------------------------------ create

    def create(self, *, title: str, area: str = "", due: str = "", undated: bool = False, scheduled: str = "",
               priority: str = "normal", project: str = "", notes: str = "", plan: str = "",
               subtasks: list[str] | None = None, contexts: list[str] | None = None, estimate: str = "",
               tags: list[str] | None = None, research: bool | None = None, research_skip_reason: str = "",
               confirm_new: bool = False, create_area: bool = False, status: str = "open",
               source: str = "") -> tf.TaskDoc:
        title = " ".join(str(title or "").split())
        if not title:
            raise NeedsInput("title", "A task needs a title.")
        if len(title) > 200:
            raise NeedsInput("title", "Title is too long (200 characters max); put detail in notes.")
        area = self._pick_area(area, create_area)
        due_v = tf.validate_date(due, "due")
        if not due_v and not undated:
            raise NeedsInput("due", "Ask the user when this is due (a date). Only pass undated=true if the user "
                             "explicitly said this task has no due date.")
        sched_v = tf.validate_date(scheduled, "scheduled")
        priority = (priority or "normal").strip().lower()
        if priority not in tf.PRIORITIES:
            raise NeedsInput("priority", f"priority must be one of {', '.join(tf.PRIORITIES)}")
        status = (status or "open").strip().lower()
        if status not in ("open", "in-progress", "waiting"):
            raise NeedsInput("status", "New tasks start as open, in-progress or waiting.")

        scan = self.scan()
        if not confirm_new:
            dupes = [t for t in scan.tasks if not t.is_closed and (
                tf.norm_title(t.title) == tf.norm_title(title) or tf.title_similarity(t.title, title) >= 0.6)]
            if dupes:
                raise NeedsInput(
                    "duplicate_check",
                    "Similar open tasks already exist. Update one of them with task_update, or ask the user; "
                    "retry with confirm_new=true only if this is genuinely different work.",
                    candidates=[self.summary(t) for t in dupes[:5]])

        do_research = self.s.research_by_default if research is None else bool(research)
        today = self.s.today()
        now = self.s.now_utc_iso()
        folder = self.s.area_dir(area)
        folder.mkdir(parents=True, exist_ok=True)
        path = _free_path(folder, f"{today}-{tf.slugify(title)}")

        tag_list = ["task"] + [t for t in (tags or []) if str(t).strip() and str(t).strip().lower() != "task"]
        ctx_list = [_context(c) for c in (contexts or []) if str(c).strip()]
        enrichment: dict[str, Any] = {"status": "pending" if do_research else "skipped", "attempts": 0,
                                      "updated": now}
        if not do_research:
            enrichment["reason"] = (research_skip_reason or "user asked for no research").strip().rstrip(".")[:300]
        fm: dict[str, Any] = {
            "title": title, "task_id": tf.new_task_id(), "schema_version": tf.SCHEMA_VERSION,
            "status": status, "priority": priority, "area": area, "project": project.strip() or None,
            "due": due_v, "scheduled": sched_v, "created": today, "completed": None, "recurrence": None,
            "tags": tag_list, "contexts": ctx_list, "estimate": (estimate or "").strip() or None,
            "reminders": [], "enrichment": enrichment,
        }
        parts = ["## Notes", "", notes.strip()] if notes.strip() else ["## Notes"]
        if plan.strip():
            parts += ["", "## Plan", "", plan.strip()]
        items = [s for s in (subtasks or []) if str(s).strip()]
        if items:
            parts += ["", "## Subtasks", ""] + [f"- [ ] {' '.join(str(s).split())}" for s in items]
        log = "Created" + (f" from {source.strip()}" if source.strip() else "") + "."
        log += " Research queued." if do_research else f" Research skipped: {enrichment['reason']}."
        if not due_v:
            log += " Undated at the user's request."
        parts += ["", "## Log", "", f"- {today}: {log}", ""]
        body = "\n".join(parts)
        data = tf.render(fm, body).encode("utf-8")
        with task_lock(self.data_dir, fm["task_id"], path):
            tf.atomic_write(path, data, expect=None)
        return tf.parse_file(path)

    def _pick_area(self, area: str, create_area: bool) -> str:
        known = self.s.known_areas()
        area = (area or "").strip().lower()
        if not area:
            if self.s.default_area:
                area = self.s.default_area
            elif len(known) == 1:
                area = known[0]
            else:
                raise NeedsInput("area", "Which area does this task belong to? Infer it from context when it is "
                                 "clear and tell the user what you chose.", known_areas=known)
        area = validate_area_name(area)
        if area not in known and not create_area:
            raise NeedsInput("area", f"{area!r} is not a known area. Use one of the known areas, or pass "
                             "create_area=true after the user confirms a new area.", known_areas=known)
        return area

    # ------------------------------------------------------------ update

    def update(self, ref: str, changes: dict[str, Any]) -> tuple[tf.TaskDoc, list[str], list[str]]:
        """Apply field changes. Returns (new doc, changed workspace paths, change notes)."""
        doc = self.resolve(ref)
        ok, why = tf.writable(doc.fm)
        if not ok:
            raise NeedsInput("unsupported", f"This task cannot be edited by Alchemy Task: {why}. Edit it by hand.")
        with task_lock(self.data_dir, doc.task_id, doc.path):
            doc = tf.parse_file(doc.path)  # re-read under the lock
            fm = dict(doc.fm)
            body = doc.body
            notes: list[str] = []
            old_path = doc.path
            new_path = doc.path
            today = self.s.today()

            def setf(key: str, value: Any, label: str | None = None) -> None:
                old = fm.get(key)
                if old == value or (old in (None, "") and value in (None, "")):
                    return
                fm[key] = value
                shown_old = tf.norm_date(old) or old
                notes.append(f"{label or key}: {shown_old if shown_old not in (None, '') else 'none'} → "
                             f"{value if value not in (None, '') else 'none'}")

            if "title" in changes and changes["title"] is not None:
                title = " ".join(str(changes["title"]).split())
                if not title:
                    raise NeedsInput("title", "Title cannot be empty.")
                setf("title", title)
                if changes.get("rename_file"):
                    m = _FILENAME_DATE.match(old_path.name)
                    prefix = m.group(1) if m else today
                    new_path = _free_path(old_path.parent, f"{prefix}-{tf.slugify(title)}", exclude=old_path)

            for key in ("due", "scheduled"):
                if key in changes and changes[key] is not None:
                    raw = str(changes[key]).strip()
                    if raw.lower() in ("", "none", "null", "clear"):
                        if key == "due" and not changes.get("undated"):
                            raise NeedsInput("due", "Clearing the due date needs undated=true, and only when the "
                                             "user said the task has no due date.")
                        setf(key, None)
                    else:
                        setf(key, tf.validate_date(raw, key))

            if changes.get("priority") is not None:
                p = str(changes["priority"]).strip().lower()
                if p not in tf.PRIORITIES:
                    raise NeedsInput("priority", f"priority must be one of {', '.join(tf.PRIORITIES)}")
                setf("priority", p)
            for key in ("project", "estimate"):
                if key in changes and changes[key] is not None:
                    setf(key, str(changes[key]).strip() or None)
            if changes.get("contexts") is not None:
                setf("contexts", [_context(c) for c in changes["contexts"] if str(c).strip()])
            if changes.get("tags_add") or changes.get("tags_remove"):
                tags = tf.tag_values(fm.get("tags"))
                for t in changes.get("tags_add") or []:
                    if str(t).strip() and str(t).strip() not in tags:
                        tags.append(str(t).strip())
                remove = {str(t).strip().lower() for t in changes.get("tags_remove") or []} - {"task"}
                tags = [t for t in tags if t.lower() not in remove]
                if "task" not in {t.lower() for t in tags}:
                    tags.insert(0, "task")
                setf("tags", tags)

            if changes.get("area"):
                area = validate_area_name(changes["area"])
                if area not in self.s.known_areas():
                    raise NeedsInput("area", f"{area!r} is not a known area.", known_areas=self.s.known_areas())
                if area != fm.get("area"):
                    setf("area", area)
                    new_path = _free_path(self.s.area_dir(area), new_path.stem, exclude=old_path)

            reason = " ".join(str(changes.get("reason") or "").split())
            if changes.get("status"):
                new = str(changes["status"]).strip().lower()
                if new not in tf.STATUSES:
                    raise NeedsInput("status", f"status must be one of {', '.join(tf.STATUSES)}")
                old = str(fm.get("status") or "").strip().lower()
                old_closed = old in tf.CLOSED_STATUSES
                if old_closed and new not in tf.CLOSED_STATUSES and not changes.get("reopen"):
                    raise NeedsInput("reopen", f"This task is {old}. Reopening must be explicit: retry with "
                                     "reopen=true if the user wants it reopened.")
                if new in ("cancelled", "waiting") and not reason:
                    raise NeedsInput("reason", "Give a reason: why it was cancelled, or what or whom it is waiting on.")
                setf("status", new)
                if new == "done":
                    completed = tf.validate_date(changes.get("completed"), "completed") or \
                        tf.norm_date(fm.get("completed")) or today
                    setf("completed", completed)
                elif old_closed and new not in tf.CLOSED_STATUSES:
                    setf("completed", None)
            elif changes.get("completed"):
                setf("completed", tf.validate_date(changes["completed"], "completed"))

            if changes.get("notes_append"):
                body = tf.append_to_section(body, "Notes", str(changes["notes_append"]))
                notes.append("notes added")

            log_msg = " ".join(str(changes.get("log") or "").split())
            if reason and changes.get("status"):
                log_msg = f"{log_msg} Reason: {reason}".strip() if log_msg else f"Reason: {reason}"
            if not notes and not log_msg:
                return doc, [], []
            summary = "; ".join(n for n in notes if n != "notes added")
            entry = log_msg or ("Updated " + summary if summary else "Updated notes")
            if log_msg and summary:
                entry = f"{log_msg} ({summary})"
            if not tf.has_task_tag(fm):
                fm["tags"] = ["task", *tf.tag_values(fm.get("tags"))]
            body = tf.append_log(body, entry, today)
            data = tf.render(fm, body).encode("utf-8")
            tf.atomic_write(old_path, data, expect=doc.raw)
            changed = [self.rel(old_path)]
            if new_path != old_path:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                os.link(old_path, new_path)  # fails if the target exists
                old_rel = self.rel(old_path)
                os.unlink(old_path)
                changed = [old_rel, self.rel(new_path)]
                notes.append(f"moved to {self.rel(new_path)}")
        return tf.parse_file(new_path), changed, notes

    def write_body_block(self, ref: str, start: str, end: str, block: str, log: str, *, top: bool = False,
                         fm_updates: dict[str, Any] | None = None) -> tuple[tf.TaskDoc, list[str]]:
        """Upsert a plugin-owned managed block (e.g. Current state) and append a log line."""
        doc = self.resolve(ref)
        ok, why = tf.writable(doc.fm)
        if not ok:
            raise NeedsInput("unsupported", f"This task cannot be edited by Alchemy Task: {why}.")
        with task_lock(self.data_dir, doc.task_id, doc.path):
            doc = tf.parse_file(doc.path)
            fm = dict(doc.fm)
            fm.update(fm_updates or {})
            body = tf.upsert_block(doc.body, start, end, block, top=top)
            if log:
                body = tf.append_log(body, log, self.s.today())
            tf.atomic_write(doc.path, tf.render(fm, body).encode("utf-8"), expect=doc.raw)
        return tf.parse_file(doc.path), [self.rel(doc.path)]


def current_state_text(body: str) -> str:
    start, end = tf.CURRENT_STATE_START, tf.CURRENT_STATE_END
    if body.count(start) != 1 or body.count(end) != 1:
        return ""
    inner = body[body.index(start) + len(start): body.index(end)]
    return inner.strip()


def _context(value: Any) -> str:
    text = str(value).strip()
    return text if text.startswith("@") else f"@{text}"


def _due_key(t: tf.TaskDoc) -> tuple[str, int]:
    order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    return (tf.norm_date(t.fm.get("due")) or "9999-99-99", order.get(str(t.fm.get("priority") or "normal"), 2))


def _free_path(folder: Path, stem: str, exclude: Path | None = None) -> Path:
    candidate = folder / f"{stem}.md"
    n = 2
    while candidate.exists() and (exclude is None or candidate.resolve() != exclude.resolve()):
        candidate = folder / f"{stem}-{n}.md"
        n += 1
    return candidate
