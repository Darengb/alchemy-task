"""Git delivery: path-scoped commits and verified pushes.

Rules (see README "Git delivery"):
- Commit only the task paths this plugin changed (``git commit --only``).
- A push counts only when the remote branch SHA equals local HEAD.
- Never autostash, reset or force. Rebase onto the remote only when no tracked
  file outside the commit is dirty; otherwise report "push pending".
- Never leave commits unpushed silently: every delivery and ``retry`` pushes
  whenever HEAD is ahead of the last confirmed remote SHA.
- Run git without prompts, with a minimal explicit environment.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import TOKEN_ENV, TRANSPORTS, Settings
from .locks import workspace_lock

GIT_TIMEOUT = 60
# GitHub's published SSH host keys (https://api.github.com/meta, checked 2026-11-08).
GITHUB_HOST_KEYS = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl",
    "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=",
)
_REPO_PROGRAM_KEYS = r"^(core\.sshcommand|core\.askpass|credential\..*helper|core\.fsmonitor|core\.hookspath)$"
_PASSTHROUGH_ENV = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SSH_AUTH_SOCK",
                    "XDG_CONFIG_HOME", "GIT_CONFIG_NOSYSTEM")


class GitError(RuntimeError):
    pass


class GitDelivery:
    def __init__(self, settings: Settings, data_dir: Path, token: str | None = None) -> None:
        self.s = settings
        self.data_dir = data_dir
        self.token = token
        if settings.git_transport not in TRANSPORTS:
            raise GitError(f"git_transport must be one of {', '.join(TRANSPORTS)}")

    # ------------------------------------------------------------ plumbing

    @property
    def key_dir(self) -> Path:
        return self.data_dir / "git"

    @property
    def deploy_key(self) -> Path:
        return self.key_dir / "deploy_key"

    def _state_path(self) -> Path:
        return self.data_dir / "git-receipts.json"

    def load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self._state_path().read_text())
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        os.replace(tmp, path)

    def env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in _PASSTHROUGH_ENV if os.environ.get(k)}
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never", "SSH_ASKPASS_REQUIRE": "never",
                    "GIT_OPTIONAL_LOCKS": "0"})
        mode = self.s.git_transport
        if mode == "deploy_key":
            self._write_known_hosts()
            env["GIT_SSH_COMMAND"] = (
                f"ssh -F /dev/null -i {self.deploy_key} -o IdentitiesOnly=yes -o IdentityAgent=none "
                f"-o BatchMode=yes -o StrictHostKeyChecking=yes "
                f"-o UserKnownHostsFile={self.key_dir / 'known_hosts'} -o ConnectTimeout=15")
            env.pop("SSH_AUTH_SOCK", None)
        elif mode == "token" and self.token:
            env[TOKEN_ENV] = self.token
            helper = ('!f() { test "$1" = get || exit 0; echo username=x-access-token; '
                      f'echo "password=${TOKEN_ENV}"; }}; f')
            # Reset every helper that could also receive (and store) the token, then add ours.
            pairs = [("credential.helper", ""), ("credential.helper", helper)]
            host = self._remote_https_host()
            if host:
                pairs = [("credential.helper", ""), (f"credential.https://{host}.helper", ""),
                         (f"credential.https://{host}.helper", helper)]
            env["GIT_CONFIG_COUNT"] = str(len(pairs))
            for i, (key, value) in enumerate(pairs):
                env[f"GIT_CONFIG_KEY_{i}"] = key
                env[f"GIT_CONFIG_VALUE_{i}"] = value
        return env

    def _remote_https_host(self) -> str:
        try:
            proc = subprocess.run(["git", "remote", "get-url", self.s.git_remote], cwd=str(self.s.root()),
                                  env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/")},
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        url = proc.stdout.strip()
        if url.startswith("https://"):
            return url[len("https://"):].split("/", 1)[0].split("@")[-1]
        return ""

    def _write_known_hosts(self) -> None:
        self.key_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.key_dir, 0o700)
        lines = []
        for key in GITHUB_HOST_KEYS:
            lines.append(f"github.com {key}")
            lines.append(f"[ssh.github.com]:443 {key}")
        path = self.key_dir / "known_hosts"
        text = "\n".join(lines) + "\n"
        if not path.exists() or path.read_text() != text:
            path.write_text(text)

    def git(self, *args: str, check: bool = True, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
        cmd = ["git"]
        if not self.s.git_run_hooks:
            cmd += ["-c", "core.hooksPath=/dev/null"]
        cmd += list(args)
        try:
            proc = subprocess.run(cmd, cwd=str(self.s.root()), env=self.env(), stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout, start_new_session=True)
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"git {args[0]} timed out after {timeout}s") from exc
        except FileNotFoundError as exc:
            raise GitError("git is not installed") from exc
        if check and proc.returncode != 0:
            raise GitError(f"git {args[0]} failed: {_short(proc.stderr or proc.stdout)}")
        return proc

    # ------------------------------------------------------------ inspection

    def is_repo(self) -> bool:
        try:
            out = self.git("rev-parse", "--show-toplevel", check=False)
        except GitError:
            return False
        return out.returncode == 0 and Path(out.stdout.strip()).resolve() == self.s.root()

    def branch(self) -> str:
        if self.s.git_branch:
            return self.s.git_branch
        out = self.git("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        if out.returncode != 0:
            raise GitError("workspace is not on a branch (detached HEAD)")
        return out.stdout.strip()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def has_remote(self) -> bool:
        out = self.git("remote", "get-url", self.s.git_remote, check=False)
        return out.returncode == 0 and bool(out.stdout.strip())

    def remote_sha(self, branch: str) -> str | None:
        out = self.git("ls-remote", self.s.git_remote, f"refs/heads/{branch}", check=False, timeout=45)
        if out.returncode != 0:
            raise GitError(f"cannot reach remote: {_short(out.stderr)}")
        line = out.stdout.strip().split("\n")[0] if out.stdout.strip() else ""
        return line.split()[0] if line else None

    def repo_programs(self) -> list[str]:
        out = self.git("config", "--local", "--name-only", "--get-regexp", _REPO_PROGRAM_KEYS, check=False)
        return [k for k in out.stdout.split() if k]

    def _identity_args(self) -> list[str]:
        out = self.git("config", "user.email", check=False)
        if out.returncode == 0 and out.stdout.strip():
            return []
        return ["-c", "user.name=Alchemy Task", "-c", "user.email=alchemy-task@localhost"]

    # ------------------------------------------------------------ delivery

    def deliver(self, paths: list[str], message: str) -> dict[str, Any]:
        """Commit ``paths`` (workspace-relative) and push. Never raises for
        push problems; returns a receipt describing what happened."""
        receipt: dict[str, Any] = {"committed": False, "pushed": False}
        if not self.is_repo():
            receipt["error"] = "workspace is not a Git repository; changes are saved but not versioned"
            receipt["state"] = "no_git"
            return receipt
        try:
            with workspace_lock(self.data_dir, "git"):
                receipt.update(self._commit(paths, message))
                receipt.update(self._push_locked())
        except Exception as exc:  # noqa: BLE001 - report, never crash the task write
            receipt["error"] = _short(str(exc))
            receipt.setdefault("state", "error")
        return receipt

    def _commit(self, paths: list[str], message: str) -> dict[str, Any]:
        paths = sorted(set(p for p in paths if p))
        if not paths:
            return {"committed": False}
        self.git("add", "-A", "--", *paths)
        pending = self.git("diff", "--cached", "--name-only", "--", *paths).stdout.split()
        if not pending:
            return {"committed": False, "note": "already committed"}
        for attempt in range(5):
            proc = self.git(*self._identity_args(), "commit", "--only", "--quiet",
                            "-m", message, "--", *paths, check=False)
            if proc.returncode == 0:
                return {"committed": True, "commit": self.head()}
            err = proc.stderr + proc.stdout
            if "index.lock" in err and attempt < 4:
                time.sleep(0.5 * (attempt + 1))
                continue
            # Someone else's sweep may have committed it between add and commit.
            if not self.git("diff", "--cached", "--name-only", "--", *paths).stdout.split() and \
                    not self.git("status", "--porcelain", "--", *paths).stdout.strip():
                return {"committed": False, "note": "already committed"}
            raise GitError(f"commit failed: {_short(err)}")
        raise GitError("commit failed: index locked")

    def retry(self) -> dict[str, Any]:
        if not self.is_repo():
            return {"pushed": False, "state": "no_git"}
        try:
            with workspace_lock(self.data_dir, "git"):
                return self._push_locked()
        except Exception as exc:  # noqa: BLE001
            return {"pushed": False, "state": "error", "error": _short(str(exc))}

    def _push_locked(self) -> dict[str, Any]:
        state = self.load_state()
        if self.s.git_transport == "none" or not self.has_remote():
            state.update({"state": "local_only", "head": self.head(), "checked_at": _now()})
            self._save_state(state)
            return {"pushed": False, "state": "local_only",
                    "note": "no remote configured: history is local to this machine"}
        if self.s.git_transport == "system" and not self.s.git_allow_repo_programs:
            progs = self.repo_programs()
            if progs:
                return self._pending(state, "blocked", f"repo-local Git config sets {', '.join(progs)}; "
                                     "enable git_allow_repo_programs to push with it")
        branch = self.branch()
        head = self.head()
        try:
            remote = self.remote_sha(branch)
        except GitError as exc:
            return self._pending(state, "push_pending", str(exc))
        if remote == head:
            return self._confirmed(state, head, already=True)
        push = self.git("push", "--quiet", self.s.git_remote, f"HEAD:refs/heads/{branch}", check=False, timeout=90)
        if push.returncode != 0 and _rejected_non_ff(push.stderr):
            dirty = self.git("status", "--porcelain", "--untracked-files=no").stdout.strip()
            if dirty:
                return self._pending(state, "diverged", "remote has new commits and the workspace has uncommitted "
                                     "changes to tracked files; commit or stash them, then run /task push")
            pull = self.git("pull", "--rebase", "--no-autostash", "--quiet", self.s.git_remote, branch,
                            check=False, timeout=90)
            if pull.returncode != 0:
                self.git("rebase", "--abort", check=False)
                return self._pending(state, "diverged", f"rebase onto the remote failed: {_short(pull.stderr)}")
            head = self.head()
            push = self.git("push", "--quiet", self.s.git_remote, f"HEAD:refs/heads/{branch}", check=False,
                            timeout=90)
        # Judge by the remote SHA, not the exit code (a post-commit hook may push concurrently).
        for wait in (0, 1, 2, 4):
            time.sleep(wait)
            try:
                remote = self.remote_sha(branch)
            except GitError:
                remote = None
            if remote == head:
                return self._confirmed(state, head)
        err = _short(push.stderr or push.stdout) if push.returncode != 0 else "remote does not show the new commit"
        return self._pending(state, "push_pending", _explain_push_error(err))

    def _confirmed(self, state: dict[str, Any], head: str, already: bool = False) -> dict[str, Any]:
        state.update({"state": "pushed", "pushed_sha": head, "head": head, "last_push_at": _now(),
                      "last_error": None, "attempts": 0, "checked_at": _now()})
        self._save_state(state)
        out = {"pushed": True, "state": "pushed", "remote_sha": head}
        if already:
            out["note"] = "remote already up to date"
        return out

    def _pending(self, state: dict[str, Any], kind: str, error: str) -> dict[str, Any]:
        try:
            head = self.head()
        except GitError:
            head = None
        state.update({"state": kind, "head": head, "last_error": error, "checked_at": _now(),
                      "attempts": int(state.get("attempts") or 0) + 1})
        self._save_state(state)
        return {"pushed": False, "state": kind, "error": error,
                "note": "saved and committed locally; Alchemy Task retries the push automatically"}

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"transport": self.s.git_transport}
        if not self.is_repo():
            out["state"] = "no_git"
            return out
        state = self.load_state()
        try:
            out["branch"] = self.branch()
            out["head"] = self.head()
            out["remote"] = self.s.git_remote if self.has_remote() else None
            if out["remote"]:
                counted = self.git("rev-list", "--count", f"{self.s.git_remote}/{out['branch']}..HEAD", check=False)
                if counted.returncode == 0:
                    out["unpushed_commits_vs_last_fetch"] = int(counted.stdout.strip() or 0)
        except GitError as exc:
            out["error"] = str(exc)
        out["last_receipt"] = state
        if state.get("pushed_sha"):
            behind = state.get("pushed_sha") != out.get("head")
        else:  # no receipt yet: fall back to the last fetched remote ref
            behind = out.get("unpushed_commits_vs_last_fetch", 1) != 0
        out["needs_push"] = bool(out.get("head")) and behind and self.s.git_transport != "none" \
            and bool(out.get("remote"))
        return out

    # ------------------------------------------------------------ deploy key

    def ensure_deploy_key(self, comment: str) -> str:
        """Create (once) an ed25519 deploy key in plugin data; return the public key."""
        self.key_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.key_dir, 0o700)
        if not self.deploy_key.exists():
            proc = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f",
                                   str(self.deploy_key)], stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=30, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
            if proc.returncode != 0:
                raise GitError(f"ssh-keygen failed: {_short(proc.stderr)}")
        os.chmod(self.deploy_key, 0o600)
        self._write_known_hosts()
        return Path(str(self.deploy_key) + ".pub").read_text().strip()


def _rejected_non_ff(stderr: str) -> bool:
    text = stderr.lower()
    return "fetch first" in text or "non-fast-forward" in text or "[rejected]" in text


def _explain_push_error(err: str) -> str:
    low = err.lower()
    if "permission denied" in low or "authentication failed" in low or "403" in low:
        return f"the remote refused the credentials ({err})"
    if "host key verification failed" in low:
        return f"the Git host's identity could not be verified ({err})"
    if "could not resolve host" in low or "timed out" in low or "connection" in low:
        return f"the remote is unreachable right now ({err})"
    return err


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _now() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
