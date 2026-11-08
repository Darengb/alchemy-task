"""Task file format: parse, render, identity, log lines and managed blocks.

Tasks are Markdown files with YAML frontmatter, framed as

    "---\n" + <frontmatter YAML> + "\n---\n\n" + body

Frontmatter is edited in ruamel.yaml round-trip mode (see ``yamlio``), so an
edit changes only the keys it touches; comments and layout survive.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import yamlio

SCHEMA_VERSION = 1
TASK_ID_KEY = "task_id"
SCHEMA_KEY = "schema_version"

STATUSES = ("open", "in-progress", "waiting", "done", "cancelled")
CLOSED_STATUSES = {"done", "completed", "complete", "cancelled", "canceled"}
PRIORITIES = ("low", "normal", "high", "urgent")

# Key order for new tasks. Existing files keep their own order; new keys append.
NEW_TASK_KEY_ORDER = (
    "title", "task_id", "schema_version", "status", "priority", "area", "project",
    "due", "scheduled", "created", "completed", "recurrence", "tags", "contexts",
    "estimate", "reminders", "enrichment",
)

_TASK_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Blocks owned by some writer. Nothing may be written inside them, and a Log
# append must stop before them.
MANAGED_START_RE = re.compile(r"^<!-- [a-z0-9-]+:start\b.*-->\s*$")
CURRENT_STATE_START = "<!-- task-current-state:start -->"
CURRENT_STATE_END = "<!-- task-current-state:end -->"


class TaskFormatError(ValueError):
    """The file is not a parseable task, or an edit would be unsafe."""


class ConcurrentEditError(RuntimeError):
    """The file changed between read and write."""


@dataclass
class TaskDoc:
    path: Path
    fm: dict[str, Any]
    body: str
    raw: bytes = field(repr=False, default=b"")
    seq_offset: int = 0  # list indentation style of the original file
    blank_keys: frozenset = frozenset()  # keys the file wrote as bare `key:`

    @property
    def task_id(self) -> str | None:
        value = self.fm.get(TASK_ID_KEY)
        return value if valid_task_id(value) else None

    @property
    def title(self) -> str:
        return str(self.fm.get("title") or "")

    @property
    def status(self) -> str:
        return str(self.fm.get("status") or "").strip().lower()

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES


# ------------------------------------------------------------------ parse/render

def split_raw(text: str) -> tuple[str, str]:
    """Split into (raw frontmatter, body) on the closing ``---`` *line*, so a
    ``---`` inside a value never cuts the frontmatter short."""
    if not text.startswith("---\n"):
        raise TaskFormatError("no frontmatter")
    idx = text.find("\n---", 3)
    while idx != -1 and text[idx + 4: idx + 5] not in ("\n", ""):
        idx = text.find("\n---", idx + 1)
    if idx == -1:
        raise TaskFormatError("unterminated frontmatter")
    return text[4: idx + 1], text[idx + 4:].lstrip("\n")


def split_text(text: str, *, rt: bool = False) -> tuple[dict[str, Any], str]:
    raw_fm, body = split_raw(text)
    try:
        fm = (yamlio.load_rt(raw_fm) if rt else yamlio.safe_load(raw_fm))
        if fm is None:
            fm = yamlio.load_rt("{}") if rt else {}
    except yamlio.YAMLError as exc:
        raise TaskFormatError(f"invalid YAML frontmatter: {exc.__class__.__name__}") from exc
    if not isinstance(fm, dict):
        raise TaskFormatError("frontmatter is not a mapping")
    return fm, body


def parse_file(path: Path, *, rt: bool = True) -> TaskDoc:
    """Parse a task file. ``rt=True`` (default) returns an editable mapping that
    keeps comments and formatting; use ``rt=False`` for fast read-only access."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TaskFormatError("not UTF-8") from exc
    fm, body = split_text(text, rt=rt)
    raw_fm = split_raw(text)[0]
    return TaskDoc(path=path, fm=fm, body=body, raw=raw, seq_offset=yamlio.seq_offset(raw_fm),
                   blank_keys=frozenset(yamlio.blank_keys(raw_fm)))


def render(fm: dict[str, Any], body: str, *, seq_offset: int = 0, keep_blank: frozenset = frozenset()) -> str:
    dumped = yamlio.dump(fm, seq_offset=seq_offset, keep_blank=keep_blank).rstrip()
    return f"---\n{dumped}\n---\n\n{body.lstrip(chr(10))}"


def is_canonical(doc: TaskDoc) -> bool:
    """True when loading and re-writing the file without changes is byte-identical."""
    text = doc.raw.decode("utf-8")
    fm, body = split_text(text, rt=True)
    raw_fm = split_raw(text)[0]
    return render(fm, body, seq_offset=yamlio.seq_offset(raw_fm),
                  keep_blank=frozenset(yamlio.blank_keys(raw_fm))).encode("utf-8") == doc.raw


def atomic_write(path: Path, data: bytes, *, expect: bytes | None) -> None:
    """Write via sibling temp file + os.replace. ``expect`` = bytes read earlier
    (None for a new file, which must not exist)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if expect is None:
            # Exclusive create: link fails if the target appeared meanwhile.
            try:
                os.link(tmp, path)
            except FileExistsError as exc:
                raise ConcurrentEditError(f"{path.name} already exists") from exc
            os.chmod(path, 0o644)
        else:
            if not path.exists() or path.read_bytes() != expect:
                raise ConcurrentEditError(f"{path.name} changed while it was being edited")
            os.chmod(tmp, path.stat().st_mode & 0o7777)
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


# ------------------------------------------------------------------ identity

def new_task_id() -> str:
    return str(uuid.uuid4())


def valid_task_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_TASK_ID_RE.match(value))


def task_id_state(fm: dict[str, Any]) -> str:
    value = fm.get(TASK_ID_KEY)
    if value in (None, ""):
        return "missing"
    return "valid" if valid_task_id(value) else "invalid"


def schema_state(fm: dict[str, Any]) -> str:
    value = fm.get(SCHEMA_KEY)
    if value in (None, ""):
        return "missing"
    if type(value) is not int or value < 1:
        return "invalid"
    if value > SCHEMA_VERSION:
        return "newer"
    return "current"


def writable(fm: dict[str, Any]) -> tuple[bool, str]:
    """Whether this plugin may write the task. Newer or malformed schemas and
    malformed IDs are reported, never rewritten."""
    if schema_state(fm) in ("newer", "invalid"):
        return False, f"unsupported schema_version {fm.get(SCHEMA_KEY)!r}"
    if task_id_state(fm) == "invalid":
        return False, f"malformed task_id {fm.get(TASK_ID_KEY)!r}"
    return True, ""


def tag_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            return [p.strip().strip("'\"") for p in s[1:-1].split(",") if p.strip()]
        return [s] if s else []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def has_task_tag(fm: dict[str, Any]) -> bool:
    return "task" in {t.lower() for t in tag_values(fm.get("tags"))}


def _fm_lines(text: str) -> tuple[list[str], int]:
    if not text.startswith("---\n"):
        raise TaskFormatError("no frontmatter")
    end = text.find("\n---", 3)
    if end == -1:
        raise TaskFormatError("unterminated frontmatter")
    return text[4:end + 1].split("\n")[:-1], end


def insert_fm_line(text: str, key: str, value: Any, after: tuple[str, ...]) -> str:
    """Add ``key: value`` as a one-line edit, keeping every other byte (comments,
    blank template lines). Fills a blank ``key:`` line if one exists."""
    lines, end = _fm_lines(text)
    rendered = yamlio.dump({key: value}).rstrip("\n")
    blank_re = re.compile(rf"^{re.escape(key)}:[ \t]*(?:#.*)?$")
    blank = [i for i, line in enumerate(lines) if blank_re.match(line)]
    if any(line.startswith(f"{key}:") for line in lines) and not blank:
        raise TaskFormatError(f"{key} already present")
    if blank:
        lines[blank[0]] = rendered
    else:
        pos = 0
        for anchor in after:
            idx = next((i for i, line in enumerate(lines) if line.startswith(f"{anchor}:")), None)
            if idx is not None:
                pos = idx + 1
                while pos < len(lines) and lines[pos][:1] in (" ", "\t", "-"):
                    pos += 1
                break
        lines.insert(pos, rendered)
    new = "---\n" + "\n".join(lines) + "\n" + text[end + 1:]
    parsed, _ = split_text(new)
    if parsed.get(key) != value:
        raise TaskFormatError(f"{key} insertion did not round-trip")
    return new


def fill_identity_text(text: str) -> tuple[str, str | None]:
    """Fill a missing task_id and/or schema_version with one-line edits.
    Returns (new_text, task_id or None if nothing changed)."""
    fm, _ = split_text(text)
    ok, _ = writable(fm)
    if not ok:
        return text, None
    changed = False
    tid = fm.get(TASK_ID_KEY) if valid_task_id(fm.get(TASK_ID_KEY)) else None
    if task_id_state(fm) == "missing":
        tid = new_task_id()
        text = insert_fm_line(text, TASK_ID_KEY, tid, ("title",))
        changed = True
    if schema_state(fm) == "missing":
        text = insert_fm_line(text, SCHEMA_KEY, SCHEMA_VERSION, (TASK_ID_KEY, "title"))
        changed = True
    return text, (tid if changed else None)


# ------------------------------------------------------------------ values

def norm_date(value: Any) -> str | None:
    """Accept date objects or YYYY-MM-DD strings; return ISO string or None."""
    if value in (None, ""):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        text = value.isoformat()[:10]
    else:
        text = str(value).strip()[:10]
    return text if _DATE_RE.match(text) else None


def validate_date(value: Any, name: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not _DATE_RE.match(text):
        raise TaskFormatError(f"{name} must be YYYY-MM-DD, got {value!r}")
    import datetime as _dt
    try:
        _dt.date.fromisoformat(text)
    except ValueError as exc:
        raise TaskFormatError(f"{name} is not a real date: {text}") from exc
    return text


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                       "nov", "dec"], start=1)}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_date_words(value: Any, today: str, name: str = "date") -> str | None:
    """Accept what people say: YYYY-MM-DD, today, tomorrow, a weekday ("friday", "next friday"), "in 3 days",
    "next week" (its Monday), or a month and day ("Nov 13", "13 November", "November 13th, 2026").
    Numeric day/month forms like 11/13 are refused because they are ambiguous across countries."""
    import datetime as _dt
    if value in (None, ""):
        return None
    text = " ".join(str(value).strip().lower().replace(",", " ").split())
    if _DATE_RE.match(text):
        return validate_date(text, name)
    base = _dt.date.fromisoformat(today)
    if text in ("today", "tonight"):
        return base.isoformat()
    if text == "tomorrow":
        return (base + _dt.timedelta(days=1)).isoformat()
    if text == "next week":
        return (base + _dt.timedelta(days=7 - base.weekday())).isoformat()
    m = re.match(r"^in (\d{1,3}) (day|days|week|weeks)$", text)
    if m:
        n = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
        return (base + _dt.timedelta(days=n)).isoformat()
    m = re.match(r"^(?:(next|this) )?(" + "|".join(_WEEKDAYS) + r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)$", text)
    if m:
        word = m.group(2)
        idx = next(i for i, d in enumerate(_WEEKDAYS) if d.startswith(word[:3]))
        ahead = (idx - base.weekday()) % 7
        if m.group(1) == "next" and ahead == 0:
            ahead = 7
        return (base + _dt.timedelta(days=ahead)).isoformat()
    m = re.match(r"^([a-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?(?: (\d{4}))?$", text) or \
        re.match(r"^(\d{1,2})(?:st|nd|rd|th)? ([a-z]{3,9})\.?(?: (\d{4}))?$", text)
    if m:
        a, b, year = m.groups()
        month_word, day = (a, b) if a.isalpha() else (b, a)
        month = _MONTHS.get(month_word[:3])
        if month:
            yr = int(year) if year else base.year
            try:
                cand = _dt.date(yr, month, int(day))
            except ValueError as exc:
                raise TaskFormatError(f"{name}: {value!r} is not a real date") from exc
            if not year and cand < base - _dt.timedelta(days=60):
                cand = _dt.date(yr + 1, month, int(day))  # "Jan 5" said in November means next year
            return cand.isoformat()
    raise TaskFormatError(f"{name}: could not read {value!r}; use a date like 2026-11-13, 'Nov 13' or 'Friday'")


def slugify(title: str, max_len: int = 60) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    text = re.sub(r"(\w)['’](\w)", r"\1\2", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if len(text) > max_len:
        cut = text[:max_len]
        text = cut.rsplit("-", 1)[0] if "-" in cut[20:] else cut
    return text.strip("-") or "task"


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def title_similarity(a: str, b: str) -> float:
    """Token Jaccard on normalized titles (cheap duplicate signal)."""
    stop = {"the", "a", "an", "to", "for", "and", "of", "on", "in", "with", "my"}
    ta = {t for t in norm_title(a).split() if t not in stop}
    tb = {t for t in norm_title(b).split() if t not in stop}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def content_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ body edits

def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    """(start, end) line indexes of a ``## heading`` section; end is exclusive and
    stops at the next ``## `` heading or managed-block start marker."""
    start = None
    in_comment = False
    for i, line in enumerate(lines):
        if start is None:
            if line.strip().lower() == f"## {heading}".lower():
                start = i
            continue
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            in_comment = True
            continue
        if line.startswith("## ") or MANAGED_START_RE.match(stripped):
            return start, i
    if start is None:
        return None
    return start, len(lines)


def append_log(body: str, message: str, day: str) -> str:
    """Append ``- YYYY-MM-DD: message`` at the end of the ``## Log`` section,
    before the next heading or managed block. Adds a Log section if missing."""
    message = " ".join(str(message).split())
    if not message:
        raise TaskFormatError("log message is empty")
    entry = f"- {day}: {message}"
    lines = body.split("\n")
    bounds = _section_bounds(lines, "Log")
    if bounds is None:
        return body.rstrip("\n") + f"\n\n## Log\n\n{entry}\n"
    start, end = bounds
    last = end - 1
    while last > start and not lines[last].strip():
        last -= 1
    insert_at = last + 1
    new_lines = lines[:insert_at]
    if insert_at == start + 1:
        new_lines.append("")
    new_lines.append(entry)
    rest = lines[insert_at:]
    if rest and rest[0].strip():
        new_lines.append("")
    new_lines.extend(rest)
    out = "\n".join(new_lines)
    if not out.endswith("\n"):
        out += "\n"
    return out


def append_to_section(body: str, heading: str, text: str, *, before: str = "Log") -> str:
    """Append free text at the end of ``## heading``; create the section (before
    ``## before`` when present, else at the end) if missing."""
    text = text.strip("\n")
    if not text.strip():
        return body
    lines = body.split("\n")
    bounds = _section_bounds(lines, heading)
    if bounds is None:
        target = _section_bounds(lines, before) if before else None
        block = [f"## {heading}", "", text, ""]
        if target is None:
            return body.rstrip("\n") + "\n\n" + "\n".join(block)
        idx = target[0]
        return "\n".join(lines[:idx] + block + lines[idx:])
    start, end = bounds
    last = end - 1
    while last > start and not lines[last].strip():
        last -= 1
    new_lines = lines[: last + 1] + [""] + text.split("\n")
    rest = lines[last + 1:]
    if rest and rest[0].strip():
        new_lines.append("")
    elif not rest:
        new_lines.append("")
    new_lines.extend(rest)
    return "\n".join(new_lines)


def upsert_block(body: str, start_marker: str, end_marker: str, block: str, *, top: bool = False) -> str:
    """Replace or insert one managed block (fail closed on malformed markers)."""
    starts, ends = body.count(start_marker), body.count(end_marker)
    if starts != ends or starts > 1:
        raise TaskFormatError("malformed managed block markers")
    if starts == 0:
        if top:
            return block + "\n\n" + body.lstrip("\n")
        return body.rstrip("\n") + "\n\n" + block + "\n"
    begin = body.index(start_marker)
    finish = body.index(end_marker, begin) + len(end_marker)
    return body[:begin] + block + body[finish:]
