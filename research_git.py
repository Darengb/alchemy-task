"""Read-only git tools for research workers.

Workers can find Git repositories under approved roots (the user's home folder and the task workspace) and run
``git log``, ``git show``, ``git grep`` and ``git ls-files`` in them. Every call is a fixed argument list run
without a shell, with a timeout, an output cap, no pager, no system git config and repo-config hooks that could
run programs (fsmonitor, external diff, textconv) switched off. Credential files are never read (catalog rule 11):
paths that look like keys, tokens or secrets are refused outright and excluded from whole-repo reads.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .runtime import Runtime

OUTPUT_CAP = 20000
TIMEOUT = 20
FIND_DEPTH = 5
FIND_LIMIT = 300
FIND_SECONDS = 15
LOG_DEFAULT, LOG_MAX = 30, 200

SECRET_NAMES = (".env", ".env.*", "auth.json", "*.pem", "*.key", "id_rsa*", "id_ed25519*", ".netrc",
                ".git-credentials", "credentials*", "secrets*")
SECRET_DIRS = (".ssh", ".aws", ".hermes")          # plus .config/gh
SKIP_DIRS = {"node_modules", "venv", ".venv", "env", "site-packages", "__pycache__", "dist", "build", "target",
             "Library", "snap"}
_EXCLUDES = tuple(f":(exclude,glob,icase)**/{n}" for n in SECRET_NAMES) + tuple(
    f":(exclude,glob,icase)**/{d}/**" for d in (*SECRET_DIRS, ".config/gh"))
_REV = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./@^~{}:+-]*$")
_GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_PAGER": "cat", "PAGER": "cat", "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C"}
_SAFE_CONFIG = ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=",
                "-c", "core.pager=cat", "-c", "color.ui=false")


class Refused(Exception):
    pass


def is_secret_path(path: str) -> bool:
    """True if any part of *path* names a credential file or a credential folder."""
    parts = [p for p in re.split(r"[\\/]+", str(path or "").strip().lower()) if p and p not in (".", "~")]
    for i, part in enumerate(parts):
        if part in SECRET_DIRS or (part == ".config" and i + 1 < len(parts) and parts[i + 1] == "gh"):
            return True
        if any(fnmatch.fnmatchcase(part, pat) for pat in SECRET_NAMES):
            return True
    return False


def refuse_file_read(tool_name: str, args: Any) -> str | None:
    """Guard for Hermes's own file tools in research children: a refusal message, or None to allow.

    Meant to be called from the research ``pre_tool_call`` hook for ``read_file`` and ``search_files``. Never
    raises. Hermes's search already skips hidden and gitignored files by default.
    """
    try:
        if tool_name not in ("read_file", "search_files") or not isinstance(args, dict):
            return None
        for key in ("path", "file_glob", "pattern" if tool_name == "search_files" and
                    args.get("target") == "files" else ""):
            if key and args.get(key) and is_secret_path(str(args[key])):
                return "Refused: research workers do not read credential files or folders (keys, tokens, .env)."
        return None
    except Exception:  # noqa: BLE001 - a guard must never throw
        return "Refused: could not check this path."


# ------------------------------------------------------------------ roots and repos

def roots(rt: Runtime | None = None) -> list[Path]:
    out: list[Path] = []
    cands = [Path.home()]
    try:
        ws = (rt or Runtime()).settings.workspace_root
        if ws:
            cands.append(Path(ws).expanduser())
    except Exception:  # noqa: BLE001 - home alone is still a valid root
        pass
    for c in cands:
        try:
            r = c.resolve()
        except OSError:
            continue
        if r.is_dir() and r not in out:
            out.append(r)
    return out


def _inside(path: Path, base: list[Path]) -> bool:
    return any(path == r or r in path.parents for r in base)


def _secret_under_root(path: Path, base: list[Path]) -> bool:
    """Credential check on the part of *path* below its approved root (the root itself was chosen by the user)."""
    for r in base:
        if path == r or r in path.parents:
            return is_secret_path(str(path.relative_to(r)))
    return True


def _repo(arg: Any) -> Path:
    text = str(arg or "").strip()
    if not text:
        raise Refused("repo is required (an absolute path from research_git_find_repos)")
    if text.startswith("-"):
        raise Refused("repo must be a path, not an option")
    p = Path(text).expanduser()
    if not p.is_absolute():
        raise Refused("repo must be an absolute path")
    p = p.resolve()
    if not _inside(p, roots()):
        raise Refused("repo is outside the approved roots (home folder and task workspace)")
    if _secret_under_root(p, roots()):
        raise Refused("repo is inside a credential folder")
    if not p.is_dir():
        raise Refused("repo not found")
    top = _git(p, ["rev-parse", "--show-toplevel"]).strip()
    if not top:
        raise Refused("not a git repository")
    top_p = Path(top).resolve()
    if not _inside(top_p, roots()) or _secret_under_root(top_p, roots()):
        raise Refused("repo is outside the approved roots (home folder and task workspace)")
    return top_p


def _path(arg: Any) -> str:
    text = str(arg or "").strip()
    if not text:
        return ""
    if text.startswith(("-", ":")):
        raise Refused("path must be a plain path inside the repo (no options or pathspec magic)")
    if text.startswith(("/", "~")) or ".." in re.split(r"[\\/]+", text):
        raise Refused("path must be relative and stay inside the repo")
    if is_secret_path(text):
        raise Refused("Refused: that looks like a credential file; research workers do not read those")
    return text


def _rev(arg: Any, default: str = "") -> str:
    text = str(arg or "").strip() or default
    if not text:
        return ""
    if not _REV.match(text):
        raise Refused("rev must be a commit, branch, tag or range (no options or spaces)")
    if ":" in text:
        _path(text.split(":", 1)[1])
    return text


def _git(repo: Path, argv: list[str], cap: int = OUTPUT_CAP) -> str:
    out, _ = _git_capped(repo, argv, cap)
    return out


def _git_capped(repo: Path, argv: list[str], cap: int = OUTPUT_CAP) -> tuple[str, bool]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_GIT_ENV)
    try:
        proc = subprocess.run(["git", *_SAFE_CONFIG, "-C", str(repo), *argv], capture_output=True,
                              timeout=TIMEOUT, env=env, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        raise Refused(f"git took longer than {TIMEOUT} seconds; narrow the request") from None
    except OSError as exc:
        raise Refused(f"git is not available: {exc}") from None
    if proc.returncode not in (0, 1):  # grep exits 1 for "no match"
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise Refused("git: " + (err[-1] if err else f"exit {proc.returncode}")[:300])
    text = proc.stdout.decode("utf-8", "replace")
    return (text[:cap], True) if len(text) > cap else (text, False)


def _result(repo: Path, argv: list[str]) -> dict[str, Any]:
    out, cut = _git_capped(repo, argv)
    res = {"ok": True, "repo": str(repo), "output": out, "truncated": cut}
    if cut:
        res["hint"] = f"Output cut at {OUTPUT_CAP} characters; narrow with path, rev or max_count."
    return res


def _spec(path: str) -> list[str]:
    return ["--", path or ".", *_EXCLUDES]


def _run(fn):
    def handler(args: dict[str, Any] | None = None, **_: Any) -> str:
        try:
            return json.dumps(fn(args or {}), ensure_ascii=False)
        except Refused as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "error": f"git read failed: {type(exc).__name__}"})
    handler.__name__ = fn.__name__
    return handler


# ------------------------------------------------------------------ tools

def _find(args: dict[str, Any]) -> dict[str, Any]:
    base = roots()
    start = base
    if args.get("root"):
        r = Path(str(args["root"])).expanduser()
        r = r.resolve() if r.is_absolute() else Path("/nonexistent")
        if not _inside(r, base) or _secret_under_root(r, base):
            raise Refused("root is outside the approved roots (home folder and task workspace)")
        start = [r]
    try:
        depth = max(1, min(int(args.get("max_depth") or FIND_DEPTH), 8))
    except (TypeError, ValueError):
        depth = FIND_DEPTH
    found: list[str] = []
    deadline = time.monotonic() + FIND_SECONDS
    stopped = ""
    for root in start:
        stack = [(root, 0)]
        while stack:
            if len(found) >= FIND_LIMIT:
                stopped = "limit"
                break
            if time.monotonic() > deadline:
                stopped = "time"
                break
            d, level = stack.pop()
            try:
                entries = sorted(os.scandir(d), key=lambda e: e.name, reverse=True)
            except OSError:
                continue
            if any(e.name == ".git" for e in entries) and str(d) not in found:
                found.append(str(d))
            if level >= depth:
                continue
            for e in entries:
                if e.name.startswith(".") or e.name in SKIP_DIRS or is_secret_path(e.name):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append((Path(e.path), level + 1))
                except OSError:
                    continue
    for root in start:  # the workspace itself (or a chosen root) can be a repo
        if (root / ".git").exists() and str(root) not in found:
            found.insert(0, str(root))
    res: dict[str, Any] = {"ok": True, "roots": [str(r) for r in base], "repos": found, "count": len(found),
                           "max_depth": depth}
    if stopped:
        res["hint"] = ("Stopped early (" + ("result limit" if stopped == "limit" else "time limit") +
                       "); pass root= a narrower folder to see more.")
    return res


def _log(args: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(args.get("repo"))
    path, rev = _path(args.get("path")), _rev(args.get("rev"))
    try:
        n = max(1, min(int(args.get("max_count") or LOG_DEFAULT), LOG_MAX))
    except (TypeError, ValueError):
        n = LOG_DEFAULT
    argv = ["log", "--no-color", "--no-ext-diff", "--no-textconv", f"--max-count={n}",
            "--format=commit %H%nAuthor: %an%nDate:   %ad%n%n    %s%n", "--date=iso"]
    if args.get("patch"):
        argv.append("--patch")
    else:
        argv.append("--stat")
    if args.get("grep"):
        argv.append("--grep=" + str(args["grep"]))   # one argv item: data, not an option
    if rev:
        argv.append(rev)
    return _result(repo, argv + _spec(path))


def _show(args: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(args.get("repo"))
    rev, path = _rev(args.get("rev"), "HEAD"), _path(args.get("path"))
    if ":" in rev:
        return _result(repo, ["show", "--no-color", "--no-textconv", rev])
    if path:  # the file as it was at rev
        return _result(repo, ["show", "--no-color", "--no-textconv", f"{rev}:{path}"])
    return _result(repo, ["show", "--no-color", "--no-ext-diff", "--no-textconv", "--stat", "--patch", rev,
                          *_spec("")])


def _grep(args: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(args.get("repo"))
    pattern = str(args.get("pattern") or "")
    if not pattern:
        raise Refused("pattern is required")
    path, rev = _path(args.get("path")), _rev(args.get("rev"))
    argv = ["grep", "--no-color", "-n", "-I", "--no-textconv"]
    if args.get("ignore_case"):
        argv.append("-i")
    if args.get("fixed"):
        argv.append("-F")
    argv += ["-e", pattern]
    if rev:
        argv.append(rev)
    return _result(repo, argv + _spec(path))


def _ls_files(args: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(args.get("repo"))
    path = _path(args.get("path"))
    res = _result(repo, ["ls-files", "--", path or ".", *_EXCLUDES])
    res["output"] = "".join(line for line in res["output"].splitlines(keepends=True)
                            if not is_secret_path(line.strip()))
    return res


t_git_find_repos = _run(_find)
t_git_log = _run(_log)
t_git_show = _run(_show)
t_git_grep = _run(_grep)
t_git_ls_files = _run(_ls_files)

_REPO = {"type": "string", "description": "Absolute repo path from research_git_find_repos."}
_PATH = {"type": "string", "description": "Optional path inside the repo, relative to its top."}
_RO = " Read-only; credential files (.env, keys, tokens) are refused."
TOOLS = (
    ({"name": "research_git_find_repos", "description": "Alchemy Task research agents only: list Git "
      "repositories under the approved roots (the user's home folder and the task workspace). Skips hidden "
      "folders, node_modules and virtualenvs. Pass root to look deeper in one folder." + _RO,
      "parameters": {"type": "object", "properties": {
          "root": {"type": "string", "description": "Optional absolute folder inside an approved root."},
          "max_depth": {"type": "integer", "minimum": 1, "maximum": 8}}}}, t_git_find_repos),
    ({"name": "research_git_log", "description": "Alchemy Task research agents only: git log for one repo "
      "(newest first, with changed-file stats; patch=true adds diffs)." + _RO,
      "parameters": {"type": "object", "properties": {
          "repo": _REPO, "path": _PATH, "rev": {"type": "string", "description": "Optional branch, tag or range."},
          "max_count": {"type": "integer", "minimum": 1, "maximum": LOG_MAX},
          "grep": {"type": "string", "description": "Optional: only commits whose message matches."},
          "patch": {"type": "boolean"}}, "required": ["repo"]}}, t_git_log),
    ({"name": "research_git_show", "description": "Alchemy Task research agents only: git show a commit "
      "(default HEAD), or with path, one file as it was at that commit." + _RO,
      "parameters": {"type": "object", "properties": {
          "repo": _REPO, "rev": {"type": "string"}, "path": _PATH}, "required": ["repo"]}}, t_git_show),
    ({"name": "research_git_grep", "description": "Alchemy Task research agents only: git grep tracked files "
      "for a pattern (with line numbers; output is capped, so narrow with path)." + _RO,
      "parameters": {"type": "object", "properties": {
          "repo": _REPO, "pattern": {"type": "string"}, "path": _PATH,
          "rev": {"type": "string", "description": "Optional commit to search instead of the working tree."},
          "ignore_case": {"type": "boolean"}, "fixed": {"type": "boolean", "description": "Plain text, not regex."}},
          "required": ["repo", "pattern"]}}, t_git_grep),
    ({"name": "research_git_ls_files", "description": "Alchemy Task research agents only: list the files git "
      "tracks in a repo, optionally under one path." + _RO,
      "parameters": {"type": "object", "properties": {"repo": _REPO, "path": _PATH}, "required": ["repo"]}},
     t_git_ls_files),
)
