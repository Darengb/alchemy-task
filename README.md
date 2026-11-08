# Alchemy Task

Alchemy Task turns messy operator work into tracked, researched, finished tasks. Tell your Hermes agent what
needs doing in plain language. It files a task with a stable ID, commits and pushes it to your Git repo,
researches it in the background, and keeps it current while you work on it.

> Status: in development for the Hermes plugin hackathon (November 2026). This README grows with each component.

## What works today

- **Task tools for your agent:** `task_create`, `task_update` and `task_find`. The agent uses them instead of
  editing files. They check for duplicates, ask for a due date when none was given, route each task to its
  area folder, and enforce status rules: done records the completion date, reopening must be explicit, and
  cancelled or waiting needs a reason.
- **Plain Markdown you own:** one file per task with YAML frontmatter, readable in any editor and compatible
  with Obsidian and TaskNotes. Edits touch only the fields they change: your comments, layout, unknown fields,
  own sections and blocks written by other tools are preserved byte for byte. YAML is handled by ruamel.yaml,
  which ships with Hermes, so the plugin installs no Python dependencies.
- **Git delivery you can trust:** every change is a path-scoped commit. A push only counts once the remote
  branch matches your commit. If the remote moved, Alchemy Task rebases when that is safe, and it never
  stashes, resets or force-pushes your work. If a push can't go through, the task is still saved and the push
  is retried.
- **Background research on every new task:** right after a task is created, a research agent starts in the
  background on your own model. It reads your skills (how you already do things), checks which tools and
  integrations your Hermes has, researches the web, and writes a dossier into the task: the recommended
  approach, context, risks, open questions, sources, and an **access plan**. The plan says whether Hermes can
  do the task now, what access is missing and how to set it up. When it finishes, your agent mentions it in
  the same chat and offers to set up missing access now or when you start the task. Say "no research needed"
  to skip it, or "research it again" to refresh it.
- **Bounded and safe research:** the research agent can only search the web and read your skills and the
  names of your tools. It cannot run commands or change files, accounts or settings. Each run is limited to
  30 tool calls and 10 minutes, with up to 3 attempts. Results from a superseded run are discarded, and the
  dossier is written into the task's latest content, so research never overwrites edits made while it ran.
- **Validator:** `/task validate` checks hand-edited files, reports problems and assigns missing IDs with
  one-line edits that keep your comments and formatting.

## Commands

| Command | What it does |
|---|---|
| `/task status` | Workspace, areas, task counts, timezone and Git delivery state |
| `/task validate [apply]` | Check task files; `apply` assigns missing IDs |
| `/task push` | Retry pushing committed task changes |
| `/task setup` | Start setup (or say "set up my tasks") |

## Task format

```yaml
---
title: Email the hall manager to confirm the load-in time
task_id: 822802fd-0b02-4f45-b7f9-991baf4e8c48   # permanent; survives renames and moves
schema_version: 1
status: open            # open | in-progress | waiting | done | cancelled
priority: normal        # low | normal | high | urgent
area: personal
due: '2026-11-10'
scheduled: null         # when you plan to do it (separate from due)
created: '2026-11-08'
completed: null
tags:
- task
enrichment:             # background research state
  status: pending
---

## Notes

## Log

- 2026-11-08: Created. Research queued.
```

Tasks live at `<workspace>/areas/<area>/tasks/YYYY-MM-DD-slug.md` by default (configurable with `task_dir`).

## Settings

Settings live under `plugins.entries.alchemy-task.settings` and appear in the Desktop plugin settings form.
Setup fills them in for you.

| Key | Default | Meaning |
|---|---|---|
| `workspace_root` | | Folder (a Git repository) holding your tasks |
| `task_dir` | `areas/{area}/tasks` | Where each area's tasks live |
| `areas` | existing folders | Area names |
| `default_area` | | Area used when none can be inferred |
| `timezone` | Hermes timezone | Used for dates and log lines |
| `research_by_default` | `true` | Research every new task unless the user opts out |
| `git_transport` | `system` | `system`, `deploy_key`, `token` or `none` |
| `git_remote` / `git_branch` | `origin` / current | Where to push |
| `git_run_hooks` | `true` | Run the repository's Git hooks |
| `git_token` | | Secret (`ALCHEMY_TASK_GIT_TOKEN`), token method only |

## Disclosures

- **Files outside plugin data:** reads and writes Markdown task files in the configured workspace's task
  folders only, not the rest of the repository.
- **Shell commands:** runs local `git` subprocesses in the workspace (add, commit of task paths only, fetch,
  rebase, push, ls-remote) with a minimal environment and no interactive prompts. In `deploy_key` mode it
  runs `ssh-keygen` once.
- **Network:** Git traffic goes only to the remote you configure.
- **Credentials:** in `system` mode your own Git and SSH configuration authenticates the push, and the plugin
  never reads your keys or credential helpers. It refuses to push when the repository's own config names
  transport programs, unless you enable `git_allow_repo_programs`. In `deploy_key` mode it generates an
  ed25519 key (unencrypted, mode 0600) and a pinned GitHub `known_hosts` file in its plugin data directory.
  In `token` mode it reads `ALCHEMY_TASK_GIT_TOKEN` through Hermes's secret API and passes it to git only
  through the child process environment, after resetting other credential helpers so the token is never
  written to disk.
- **Background agents and model use:** after each task is created (and from the optional research sweep job),
  the plugin starts a Hermes research subagent through the public subagent lifecycle API. It runs on your
  configured model, with only the `web` toolset and the plugin's read-only research tools, so it spends your
  model tokens and sends search queries derived from the task text to your configured web search provider.
- **Reads outside plugin data:** research agents read your skills through Hermes's skill tools, the names
  and availability of your toolsets, tools and MCP servers (never keys or credentials), and Markdown notes the
  task links to inside the workspace.
- **Chat context:** when research finishes, a one-line note is added to your next message in the chat where
  the task was created, so your agent can tell you about it.
- **Scheduled job (created only with your approval during setup):** a research sweep every 30 minutes. A
  pre-check script copied into `$HERMES_HOME/scripts/` runs first and starts the agent only when a task is
  waiting for research, so idle runs cost nothing.
- **Plugin state:** locks, push receipts, active research runs, a one-hour capability cache and pending chat
  notes live in the plugin's profile-scoped data directory.
- No telemetry.

## Development

```bash
cd tests && python -m pytest -q        # needs pytest and ruamel.yaml
hermes plugins validate /path/to/alchemy-task
```

Tests use synthetic fixtures only.

## License

MIT
