from __future__ import annotations

import dataclasses
import os
import stat

from alchemy_task.core.gitops import GitDelivery
from alchemy_task.core.store import TaskStore

from helpers import git


def remote_head(ws):
    return git(ws, "ls-remote", "origin", "refs/heads/main").stdout.split()[0]


def local_head(ws):
    return git(ws, "rev-parse", "HEAD").stdout.strip()


def make_task(settings, data_dir, title="Order new chairs"):
    store = TaskStore(settings, data_dir)
    doc = store.create(title=title, area="work", due="2026-11-20", research=False)
    return store, store.rel(doc.path)


def test_deliver_commits_only_task_path_and_pushes(settings, data_dir, workspace):
    # An unrelated staged change and an unrelated dirty file must be left alone.
    (workspace / "notes.md").write_text("staged\n")
    git(workspace, "add", "notes.md")
    (workspace / "areas/work/tasks/.keep").write_text("dirty\n")
    _, rel = make_task(settings, data_dir)
    receipt = GitDelivery(settings, data_dir).deliver([rel], "task: create")
    assert receipt["committed"] and receipt["pushed"], receipt
    assert remote_head(workspace) == local_head(workspace)
    shown = git(workspace, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert shown == [rel]
    status = git(workspace, "status", "--porcelain").stdout
    assert "A  notes.md" in status and " M areas/work/tasks/.keep" in status


def test_remote_ahead_rebases_then_pushes(settings, data_dir, workspace, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    (other / "from-phone.md").write_text("x\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "phone edit")
    git(other, "push", "-q", "origin", "main")
    _, rel = make_task(settings, data_dir)
    receipt = GitDelivery(settings, data_dir).deliver([rel], "task: create")
    assert receipt["pushed"], receipt
    assert (workspace / "from-phone.md").exists()
    assert remote_head(workspace) == local_head(workspace)


def test_remote_ahead_with_dirty_tracked_file_reports_pending(settings, data_dir, workspace, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "remote.git"), str(other))
    (other / "from-phone.md").write_text("x\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "phone edit")
    git(other, "push", "-q", "origin", "main")
    (workspace / "areas/work/tasks/.keep").write_text("user is mid-edit\n")
    _, rel = make_task(settings, data_dir)
    gd = GitDelivery(settings, data_dir)
    receipt = gd.deliver([rel], "task: create")
    assert receipt["committed"] and not receipt["pushed"] and receipt["state"] == "diverged"
    assert (workspace / "areas/work/tasks/.keep").read_text() == "user is mid-edit\n"  # never stashed
    assert gd.status()["needs_push"]
    # Once the user commits their edit, the retry converges.
    git(workspace, "commit", "-q", "-am", "user edit")
    assert gd.retry()["pushed"]
    assert not gd.status()["needs_push"]


def test_offline_push_retried_later(settings, data_dir, workspace, tmp_path):
    remote = tmp_path / "remote.git"
    moved = tmp_path / "remote-away.git"
    os.rename(remote, moved)
    _, rel = make_task(settings, data_dir)
    gd = GitDelivery(settings, data_dir)
    receipt = gd.deliver([rel], "task: create")
    assert receipt["committed"] and receipt["state"] == "push_pending"
    os.rename(moved, remote)
    # A later write with nothing new to commit still pushes the earlier commit.
    assert gd.retry()["pushed"]
    assert remote_head(workspace) == local_head(workspace)


def test_post_commit_hook_push_race_judged_by_remote_sha(settings, data_dir, workspace):
    hook = workspace / ".git/hooks/post-commit"
    hook.write_text("#!/bin/sh\ngit push --quiet origin main >/dev/null 2>&1 &\n")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    _, rel = make_task(settings, data_dir)
    receipt = GitDelivery(settings, data_dir).deliver([rel], "task: create")
    assert receipt["pushed"], receipt


def test_hooks_disabled_in_owned_workspace(settings, data_dir, workspace):
    hook = workspace / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    _, rel = make_task(settings, data_dir)
    blocked = GitDelivery(settings, data_dir).deliver([rel], "task: create")
    assert not blocked["committed"] and "commit failed" in blocked["error"]
    owned = dataclasses.replace(settings, git_run_hooks=False)
    assert GitDelivery(owned, data_dir).deliver([rel], "task: create")["pushed"]


def test_local_only_and_not_a_repo(settings, data_dir, workspace, tmp_path):
    none = dataclasses.replace(settings, git_transport="none")
    _, rel = make_task(settings, data_dir)
    r = GitDelivery(none, data_dir).deliver([rel], "task: create")
    assert r["committed"] and r["state"] == "local_only"
    plain = tmp_path / "plain"
    (plain / "areas/work/tasks").mkdir(parents=True)
    s2 = dataclasses.replace(settings, workspace_root=str(plain))
    store = TaskStore(s2, data_dir)
    doc = store.create(title="Water plants", area="work", due="2026-11-20", research=False)
    assert GitDelivery(s2, data_dir).deliver([store.rel(doc.path)], "x")["state"] == "no_git"


def test_repo_local_transport_program_blocks_push(settings, data_dir, workspace):
    git(workspace, "config", "core.sshCommand", "ssh -i /tmp/whatever")
    _, rel = make_task(settings, data_dir)
    r = GitDelivery(settings, data_dir).deliver([rel], "task: create")
    assert r["committed"] and r["state"] == "blocked"
    allowed = dataclasses.replace(settings, git_allow_repo_programs=True)
    assert GitDelivery(allowed, data_dir).retry()["pushed"]


def test_rename_commits_both_paths(settings, data_dir, workspace):
    store, rel = make_task(settings, data_dir)
    gd = GitDelivery(settings, data_dir)
    gd.deliver([rel], "create")
    doc, paths, _ = store.update(rel, {"title": "Order ergonomic chairs", "rename_file": True})
    r = gd.deliver(paths, "rename")
    assert r["pushed"], r
    assert git(workspace, "status", "--porcelain", "--", *paths).stdout == ""
    tree = git(workspace, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
    assert paths[1] in tree and paths[0] not in tree


def test_rename_of_never_committed_task(settings, data_dir, workspace):
    store, rel = make_task(settings, data_dir, title="Buy printer ink")  # created, never delivered
    doc, paths, _ = store.update(rel, {"title": "Buy printer toner", "rename_file": True})
    r = GitDelivery(settings, data_dir).deliver(paths, "rename")
    assert r["committed"] and r["pushed"], r
    tree = git(workspace, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
    assert paths[1] in tree and paths[0] not in tree


def test_deploy_key_env_and_token_env(settings, data_dir):
    dk = dataclasses.replace(settings, git_transport="deploy_key")
    gd = GitDelivery(dk, data_dir)
    pub = gd.ensure_deploy_key("alchemy-task@test")
    assert pub.startswith("ssh-ed25519 ")
    assert oct(gd.deploy_key.stat().st_mode & 0o777) == "0o600"
    env = gd.env()
    assert "StrictHostKeyChecking=yes" in env["GIT_SSH_COMMAND"] and "SSH_AUTH_SOCK" not in env
    assert "github.com ssh-ed25519" in (gd.key_dir / "known_hosts").read_text()
    tok = GitDelivery(dataclasses.replace(settings, git_transport="token"), data_dir, token="secret-value")
    env = tok.env()
    assert env["GIT_CONFIG_VALUE_0"] == "" and "secret-value" not in env["GIT_CONFIG_VALUE_1"]
    assert env["ALCHEMY_TASK_GIT_TOKEN"] == "secret-value"
