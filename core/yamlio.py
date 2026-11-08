"""YAML through ruamel.yaml, which ships with Hermes (no extra dependency).

- Writes use round-trip mode, so comments, quoting, key order and layout the
  user wrote by hand survive an edit. Long values are never wrapped and empty
  values render as ``null``, which matches the common PyYAML ``safe_dump`` form.
- Fast reads (scans, lookups) use the safe loader and return plain Python types.
"""
from __future__ import annotations

import io
import re
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

__all__ = ["YAMLError", "dump", "load_rt", "safe_load"]


def _null(representer: Any, _data: Any) -> Any:
    return representer.represent_scalar("tag:yaml.org,2002:null", "null")


_INDENTED_SEQ = re.compile(r"^[^\s#][^\n]*:[ \t]*(?:#[^\n]*)?\n(?:[ \t]*#[^\n]*\n)*( +)- ", re.M)


def seq_offset(text: str) -> int:
    """Indentation of list items under a key in ``text`` (0 for ``- x``, 2 for ``  - x``)."""
    m = _INDENTED_SEQ.search(text)
    return len(m.group(1)) if m else 0


def _rt(offset: int = 0) -> YAML:
    y = YAML()  # round-trip
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=2 + offset, offset=offset)
    y.representer.add_representer(type(None), _null)
    return y


def load_rt(text: str) -> Any:
    """Load for editing: a mapping that remembers comments and formatting."""
    return _rt().load(text)


def safe_load(text: str) -> Any:
    """Load plain data (fast; C extension when available)."""
    return YAML(typ="safe").load(text)


_BLANK_KEY = re.compile(r"^([A-Za-z_][\w-]*):[ \t]*(?:#.*)?$")


def blank_keys(text: str) -> set[str]:
    """Top-level keys written with no value at all (``key:``), as template-made files do."""
    lines = text.split("\n")
    out = set()
    for i, line in enumerate(lines):
        m = _BLANK_KEY.match(line)
        if not m:
            continue
        nxt = next((n for n in lines[i + 1:] if n.strip() and not n.lstrip().startswith("#")), "")
        if not nxt[:1].isspace() and not nxt.startswith("-"):
            out.add(m.group(1))
    return out


def dump(data: Any, *, seq_offset: int = 0, keep_blank: set[str] | frozenset[str] = frozenset()) -> str:
    out = io.StringIO()
    _rt(seq_offset if seq_offset in (0, 2) else 0).dump(data, out)
    text = out.getvalue()
    if keep_blank:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            for key in keep_blank:
                prefix = f"{key}: null"
                if (line == prefix or line.startswith(prefix + " ")) and data.get(key) is None:
                    rest = line[len(prefix):]
                    lines[i] = f"{key}:" + (" " * 5 + rest if rest.strip() else "")
        text = "\n".join(lines)
    return text
