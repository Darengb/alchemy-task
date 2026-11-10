"""Read-only guard shared by task research and discovery research children.

Dependency-free on purpose (stdlib only), so discovery can load it without the rest of the plugin.
"""
from __future__ import annotations

import fnmatch
import os
import re
from typing import Any

# Tools a research child may never call: writes, execution and side effects. Frozen, matched by
# exact name only (no argument parsing). Everything else passes (reads, web, research tools).
WRITE_BLOCKED_TOOLS = frozenset({
    "write_file", "patch", "skill_manage", "terminal", "execute_code", "process_manage",
    "memory", "send_message", "cronjob", "cronjob_manage", "delegate_task", "clarify",
    "text_to_speech", "image_generate", "computer_use", "browser_vault",
    "task_create", "task_update", "task_checkpoint", "task_work_start", "task_ios", "task_setup",
    "task_research", "task_research_sweep",
    "discovery_submit", "discovery_decide", "discovery_stream", "discovery_start", "discovery_config",
    "discovery_research_run", "discovery_research_accept", "discovery_join", "discovery_actions",
    "discovery_recover", "discovery_reconcile", "discovery_release_hold",
})


# MCP and hosted-connector tools are allowed for research children only when the tool part of the name starts
# with a read verb; everything else (sends, creates, flag changes, generic "call") is refused. Browser,
# kanban and Home Assistant tools are refused outright. Fail closed: unknown verbs are blocked.
READ_VERBS = ("get", "list", "read", "search", "query", "fetch", "describe", "find", "view", "lookup",
              "retrieve", "show", "count", "info", "browse", "inspect", "summarize", "summarise", "preview")
_PREFIX_BLOCKED = ("browser", "kanban", "ha_")


def is_write_like(tool_name: Any) -> bool:
    """True for tool names a read-only research child must not call. Never raises."""
    try:
        name = str(tool_name or "")
        if name in WRITE_BLOCKED_TOOLS:
            return True
        low = name.lower()
        if low.startswith(_PREFIX_BLOCKED):
            return True
        if low.startswith("mcp_") or low.startswith("connectors__"):
            tool = re.split(r"__", low)[-1] if "__" in low else low[4:]
            raw = re.split(r"__", name)[-1] if "__" in name else name[4:]
            words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", raw)
            parts = name.split("__")
            app = parts[1].lower() if len(parts) >= 3 else ""
            if app and len(words) > 1 and words[0].lower() == app:
                words = words[1:]  # connector tools often repeat the app name: GMAIL_FETCH_EMAILS
            first = words[0].lower() if words else ""
            if first in READ_VERBS:
                return False
            # noun-first read tools such as notion-search or catalog_search: allowed only when the LAST word is a
            # read verb and no write word appears anywhere in the name.
            low_words = [w.lower() for w in words]
            write_words = {"create", "update", "delete", "remove", "send", "post", "set", "put", "write", "add",
                           "edit", "move", "call", "run", "exec", "execute", "publish", "upload", "invite", "approve",
                           "cancel", "archive", "merge", "push", "submit", "reply", "forward", "trigger", "start",
                           "stop", "toggle", "enable", "disable", "assign", "close", "open", "reset", "pay", "charge"}
            if low_words and low_words[-1] in READ_VERBS and not write_words.intersection(low_words):
                return False
            return True
        return False
    except Exception:  # noqa: BLE001 - a guard must never throw; fail closed
        return True


SECRET_NAMES = (".env", ".env.*", "*.env", "auth.json", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
                "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*", ".netrc", ".npmrc", ".pypirc", ".pgpass",
                ".git-credentials", "credentials", "credentials.json", "credentials.y*ml", "credentials.ini",
                "credentials.toml", "credentials.db", "*credentials.json", "*secret", "*secrets", "*secret.json",
                "*secrets.json", "secrets.*", "*.secrets", "client_secret*", "*token", "*tokens", "*token.json",
                "*tokens.json", "*token.txt", "*.token", "*_history",
                ".history", "cookies", "cookies-journal", "login data", "login data-journal", "web data",
                "key4.db", "logins.json", "kubeconfig", "service-account*.json", "*.kdbx")
SECRET_DIRS = (".ssh", ".aws", ".hermes", ".gnupg", ".supabase", ".docker", ".kube", ".azure", ".password-store",
               ".mozilla", "keyrings")
HOME_SECRET_DIRS = ("private",)   # top-level folders in the user's home kept out of research
# Two-part folders: .config/gh, .config/gcloud, .config/google-chrome, .config/chromium, .git/config file
SECRET_PAIRS = {(".config", "gh"), (".config", "gcloud"), (".config", "google-chrome"), (".config", "chromium"),
                (".config", "hub"), (".git", "config")}

# Masks common secret formats in git output (Hermes redacts its own file tools; git output bypasses that).
_SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abposr]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sbp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|glpat-[A-Za-z0-9_\-]{20,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})")
_SECRET_ASSIGN = re.compile(r"(?i)\b([A-Z0-9_]{0,40}(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)[A-Z0-9_]{0,40}\s{0,5}[:=]\s{0,5})"
                            r"(['\"]?)[^\s'\"]{8,}\2")


def redact(text: str) -> str:
    try:
        text = _SECRET_VALUE.sub("[redacted]", text)
        return _SECRET_ASSIGN.sub(lambda m: m.group(1) + "[redacted]", text)
    except Exception:  # noqa: BLE001
        return "[output withheld: redaction failed]"


def _secret_text(path: str) -> bool:
    parts = [p for p in re.split(r"[\\/]+", str(path or "").strip().lower()) if p and p not in (".", "~")]
    for i, part in enumerate(parts):
        if part in SECRET_DIRS or (i + 1 < len(parts) and (part, parts[i + 1]) in SECRET_PAIRS):
            return True
        if any(fnmatch.fnmatchcase(part, pat) for pat in SECRET_NAMES):
            return True
    return False


def is_secret_path(path: str) -> bool:
    """True if *path*, or the file it really points to (symlinks, '..', '~'), names a credential file or folder."""
    try:
        if _secret_text(path):
            return True
        expanded = os.path.expanduser(str(path or ""))
        if not os.path.isabs(expanded):
            # Relative paths resolve against the tool's working directory, not ours (the gateway runs inside
            # ~/.hermes): judge them by their text only.
            return False
        real = os.path.realpath(expanded)
        if _secret_text(real):
            return True
        home = os.path.realpath(os.path.expanduser("~"))
        rel = os.path.relpath(real, home) if real.startswith(home + os.sep) else ""
        return bool(rel) and rel.split(os.sep, 1)[0].lower() in HOME_SECRET_DIRS
    except Exception:  # noqa: BLE001 - cannot tell: treat as secret
        return True


def refuse_file_read(tool_name: str, args: Any) -> str | None:
    """Guard for Hermes's own file tools in research children: a refusal message, or None to allow.

    Meant to be called from the research ``pre_tool_call`` hook for ``read_file`` and ``search_files``. Never
    raises. Hermes's search already skips hidden and gitignored files by default.
    """
    try:
        if tool_name not in ("read_file", "search_files") or not isinstance(args, dict):
            return None
        refusal = "Refused: research workers do not read credential files or folders (keys, tokens, .env)."
        if args.get("path") and is_secret_path(str(args["path"])):
            return refusal
        globs = [args.get("file_glob")]
        if tool_name == "search_files" and args.get("target") == "files":
            globs.append(args.get("pattern"))
        if any(g and _secret_text(str(g)) for g in globs):
            return refusal
        return None
    except Exception:  # noqa: BLE001 - a guard must never throw
        return "Refused: could not check this path."
