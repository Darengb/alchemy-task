"""Read-only policy for discovery reader, read-back and sender bindings.

A binding's tool runs inside a scheduled discovery job, and its toolsets are added to that job. A run that
reads third-party mail must never pick up shell, code, file-write, browser, scheduling or delegation access
that way. So:

- a reader or read-back tool must pass ``is_write_like()`` (the same check research children use);
- no binding may bring a banned toolset, including the sender binding of ``verified_sender`` delivery, which
  keeps its send tool but not exec or write toolsets.
"""
from __future__ import annotations

from typing import Any, Iterable

from .discovery_identity import UserError
from .research_guard import is_write_like

# Hermes toolsets that give shell, code, file-write, browser/desktop control, scheduling or delegation.
BANNED_TOOLSETS = frozenset({
    "terminal", "code_execution", "file", "computer_use", "browser", "browser-cdp", "browser-use",
    "cronjob", "delegation", "kanban", "debugging", "coding", "desktop_ui", "discord_admin", "skills",
    "memory", "connections", "catalog", "project", "onboarding",
})
# Composite platform toolsets (hermes-cli, hermes-cron, hermes-telegram, ...) bundle terminal and file.
_BANNED_PREFIXES = ("hermes-", "browser")
_WRITE_HINTS = ("write", "exec", "shell", "terminal", "code", "admin", "cron", "schedul", "deleg")


def banned_toolset(name: Any) -> bool:
    """True for a toolset a discovery binding may never add to a scheduled run. Fail closed on non-text."""
    if not isinstance(name, str) or not name.strip():
        return True
    low = name.strip().lower()
    if low in BANNED_TOOLSETS or low.startswith(_BANNED_PREFIXES):
        return True
    if low.startswith("mcp-") or low.startswith("mcp_"):
        return False  # one MCP server's tools; each tool is checked by name
    return any(h in low for h in _WRITE_HINTS)


def allowed_reader_toolsets(toolsets: Iterable[Any] | None) -> list[str]:
    """The toolsets from ``toolsets`` that a binding may add, in order, de-duplicated, banned ones dropped."""
    out: list[str] = []
    for name in toolsets or ():
        if not banned_toolset(name) and name not in out:
            out.append(name)
    return out


def check_toolsets(toolsets: Iterable[Any] | None, *, what: str = "discovery readers") -> list[str]:
    bad = [str(t) for t in (toolsets or ()) if banned_toolset(t)]
    if bad:
        raise UserError(f"{what} must not add shell, code, file-write, browser or scheduling toolsets; "
                        f"remove {', '.join(sorted(set(bad)))}")
    return allowed_reader_toolsets(toolsets)


def check_binding(tool_name: Any, toolsets: Iterable[Any] | None = None, *, sender: bool = False) -> list[str]:
    """Refuse a reader/read-back binding whose tool is write-like, or any binding with a banned toolset.

    ``sender=True`` is for the send tool of verified_sender delivery: the tool itself may send, but its
    toolsets are held to the same rule. Returns the (already clean) toolsets list."""
    if not sender:
        if not isinstance(tool_name, str) or not tool_name or is_write_like(tool_name):
            raise UserError(f"discovery readers must be read-only tools; {tool_name!r} looks like it can write, "
                            "send or run something. Use a tool whose name starts with a read verb "
                            "(get, list, read, search, fetch, ...)")
    return check_toolsets(toolsets, what="discovery readers" if not sender else "discovery delivery bindings")


def _source_toolsets(stream: dict, configs: dict) -> list[str]:
    names = [t for s in stream.get("sources") or () for t in (s.get("toolsets") or ())]
    for config in (configs or {}).values():
        if not isinstance(config, dict):
            continue
        if any(s.get("name") == config.get("name") and s.get("scope") == config.get("scope")
               for s in stream.get("sources") or ()):
            names += list(config.get("toolsets") or ())
            names += list((config.get("binding") or {}).get("toolsets") or ())
    return names


def stream_reader_toolsets(stream: dict, source_configs: dict | None = None,
                           delivery_binding: dict | None = None) -> list[str]:
    """Union of a stream's approved reader toolsets (stream sources and their saved configs) and its delivery
    binding's sender/read-back toolsets, minus banned ones. Order kept, duplicates dropped.

    ``stream``: one record from discovery streams state ({'name', 'sources': [{'name','scope','toolsets'}]}).
    ``source_configs``: that stream's entry in ``discovery_sources`` state ({source_key: config}).
    ``delivery_binding``: that stream's entry in ``discovery_delivery`` state, or None."""
    names = _source_toolsets(stream, source_configs or {})
    names += list((delivery_binding or {}).get("toolsets") or ())
    return allowed_reader_toolsets(names)


def needs_read_only_reader(rt: Any) -> list[dict[str, str]]:
    """Existing streams whose source, binding or delivery needs a banned toolset or a write-like reader.
    Never raises; these streams are shown as 'needs a read-only reader' instead of crashing."""
    out: list[dict[str, str]] = []
    try:
        state = rt.ctx.state
        streams = state.get("streams", default={}) or {}
        configs = state.get("discovery_sources", default={}) or {}
        delivery = state.get("discovery_delivery", default={}) or {}
    except Exception:  # noqa: BLE001 - status must not fail
        return out
    if not isinstance(streams, dict):
        return out

    def add(stream: str, key: str, reason: str) -> None:
        row = {"stream": stream, "source_key": key, "reason": reason}
        if row not in out:
            out.append(row)

    for name, stream in sorted(streams.items()):
        if not isinstance(stream, dict):
            continue
        for src in stream.get("sources") or ():
            if not isinstance(src, dict):
                continue
            bad = sorted({str(t) for t in src.get("toolsets") or () if banned_toolset(t)})
            if bad:
                add(name, str(src.get("name") or ""), "needs toolset(s) " + ", ".join(bad))
            method = src.get("read_method")
            if isinstance(method, str) and method and is_write_like(method):
                add(name, str(src.get("name") or ""), f"read method {method} is not a read-only tool")
        mine = configs.get(name) if isinstance(configs, dict) else None
        for key, config in sorted((mine or {}).items()) if isinstance(mine, dict) else ():
            if not isinstance(config, dict):
                continue
            binding = config.get("binding") if isinstance(config.get("binding"), dict) else {}
            bad = sorted({str(t) for t in [*(config.get("toolsets") or ()), *(binding.get("toolsets") or ())]
                          if banned_toolset(t)})
            if bad:
                add(name, str(key), "needs toolset(s) " + ", ".join(bad))
            for tool in {config.get("read_method"), binding.get("tool")}:
                if isinstance(tool, str) and tool and is_write_like(tool):
                    add(name, str(key), f"reader {tool} is not a read-only tool")
        bind = delivery.get(name) if isinstance(delivery, dict) else None
        if isinstance(bind, dict):
            bad = sorted({str(t) for t in bind.get("toolsets") or () if banned_toolset(t)})
            if bad:
                add(name, "delivery", "needs toolset(s) " + ", ".join(bad))
            tool = bind.get("read_tool")
            if isinstance(tool, str) and tool and is_write_like(tool):
                add(name, "delivery", f"read-back {tool} is not a read-only tool")
    return out


def needs_read_only_reader_text(rt: Any) -> str:
    rows = needs_read_only_reader(rt)
    if not rows:
        return ""
    lines = [f"- {r['stream']} / {r['source_key']}: {r['reason']}" for r in rows]
    return ("Discovery streams that need a read-only reader (reconfigure these sources with read-only tools):\n"
            + "\n".join(lines))
