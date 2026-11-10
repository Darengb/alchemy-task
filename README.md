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
- **Official work sessions:** say "work on X" or "continue X". The chat is linked to the task, which turns
  in progress, and the agent gets the notes, research, access plan and current state with its next step, so
  you never re-explain. When the work finishes, needs you, waits on someone or is blocked, the agent records
  a checkpoint: a **Current state** section at the top of the task with what was done, the next step and
  what is needed from whom. Marking a task done requires evidence of what was checked.
- **Safety net:** if a linked chat ends or sits idle for 30 minutes without a checkpoint, Alchemy Task writes
  one itself from the conversation, using your checkpoint model (by default the same model as compression)
  or a free digest of the last exchange when no model call is available. Automatic checkpoints never mark a
  task done.
- **Discovery streams:** a scheduled digest of things that look like your tasks, found in sources your
  agent can already read: email, chat, meeting transcripts and notes, shared documents. Each stream has its
  own sources and scope, areas, schedule (6 PM by default, in your timezone) and chat, so a work stream and a
  side-business stream stay separate. A digest is a short numbered list with the reason for each item and
  which sources were checked; reply "1 and 3" and those become tasks, with their source recorded and the
  usual research. Nothing becomes a task without your reply, a message is never suggested twice (across
  streams too), and items already covered by an open task are skipped.
- **Apple Reminders (optional, beta):** with the Hermes mobile app on your iPhone, say "sync reminders" or run
  `/task ios`. Open tasks from the areas you choose appear in your default Reminders list (or another list you
  name); title, due date and the checkbox stay in sync both ways each time you sync, and everything else stays
  in the task file. Checking a reminder off marks the task done. Only open tasks get a new reminder, and not
  ones more than 14 days overdue. Your own reminders are never touched. Each reminder's notes show the task's
  summary and its next step.

  *Where it works:* tested end to end on a real iPhone with self-hosted Hermes, from a chat in the Hermes app:
  creating reminders in a chosen list, all-day due dates with no alert, renames and summary notes reaching the
  phone, and checking a reminder off on the phone marking the task done. On Nous Cloud agents the connector
  installs and runs on the server, but the current beta of the Hermes app does not yet offer Device Access for
  Cloud agents, so Reminders sync there waits on that app update.
- **Validator:** `/task validate` checks hand-edited files, reports problems and assigns missing IDs with
  one-line edits that keep your comments and formatting.
- **Tasks view in the web dashboard and the desktop app:** a **Tasks** tab (dashboard) and a **Tasks** page
  (desktop) show your tasks by month, week or day. On a phone, or in a narrow window, it opens on a scrolling
  list of days. Check a task off with one click (with Undo), drag it to another day, or pick a date; either way
  its due and scheduled dates move together. Click a task to read its notes, plan, subtasks and current state,
  tick subtasks, and edit everything in place. Today's list also shows your overdue tasks, folded under a
  count. The **Discovery** tab lists each run with its proposals: create a task, apply a proposal to the
  existing task it matched, or dismiss it. The gear opens settings for discovery schedules and task defaults.
  Every change goes through the same files, log lines and Git commits as a change made in chat, and an edit
  never overwrites a newer version of the task.

## Setup

Say **"set up my tasks"**. Your agent walks you through it in a few minutes, and every answer is checked and
saved by the plugin:

1. **Timezone** first. A fresh Cloud agent usually has none, so it asks rather than assuming UTC.
2. **Workspace:** point it at an existing notes repository (an Obsidian vault works; only the task folders are
   used) or start fresh in a new Git repository.
3. **Areas**, such as work and personal.
4. **Git delivery:** your own Git setup if it already pushes; otherwise Alchemy Task makes a deploy key
   for one repository and shows you where to add it on GitHub. Nothing secret goes through chat.
5. **Scheduled jobs**, listed with what they do and what they cost, created only after you say yes.

`/task status` shows the readiness of each part at any time. `/task teardown` removes the scheduled jobs
(run it before `hermes plugins remove`); task files and settings stay.

### Scheduled jobs

| Job | When | What it does | Cost |
|---|---|---|---|
| Research sweep | every 30 minutes | Researches tasks whose research could not start or stopped early | Free when nothing waits (a script checks first) |
| Task file check and push retry | hourly | Gives hand-made tasks an ID, pushes commits that failed to push, tells you about new file problems | Free (script, no model) |

Each job's small loader script is copied into `$HERMES_HOME/scripts/` (cron only runs scripts from there).

Each **discovery stream** is one more job, created only when you set the stream up (say "set up a
discovery stream" in the chat that should receive it). It runs one agent turn on your model per run and reads
only the sources and scopes you approved, with the tools you already have. Up to 50 suggestions a day per
stream get a quick extra check (configurable). That research runs in short tool calls of at most
five minutes each, inside Hermes' default tool deadline, so you never need to raise any timeout.

## Commands

| Command | What it does |
|---|---|
| `/task status` | Readiness of each part: timezone, workspace, areas, Git, jobs, discovery |
| `/task teardown` | Remove the scheduled jobs and their scripts (tasks and settings are kept) |
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
  also runs OpenSSH's key generator once, to create the deploy key described under Credentials.
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
- **Work-session transcripts and background thread:** for chats linked to a task, the plugin keeps a short
  digest of the last exchange, reads the chat's transcript through Hermes's session store when it writes an
  automatic checkpoint, and runs one background thread per profile that checks linked chats every 10
  minutes. Automatic checkpoints make one small model call (about 3,000 input and 300 output tokens) through
  the `alchemy_task_checkpoint` model slot, which you can point at a cheaper model.
- **Chat context:** in a chat linked to a task, a one-line reminder to checkpoint is added to each message;
  when research finishes, a one-line note is added to your next message in the chat where
  the task was created, so your agent can tell you about it.
- **Scheduled jobs (created only after you approve them during setup):** see the table above. Their loader
  scripts are written to `$HERMES_HOME/scripts/`; the hourly check messages the setup chat only when
  something changes. The research sweep's script starts the agent only when a task is waiting.
- **Discovery reads and writes:** discovery jobs read only the sources you approve for each stream, through
  your existing tools and connectors; the plugin itself connects to nothing. Digests are written into the
  chat where the stream was created by default native Hermes cron delivery (`delivery_owner=native_origin`,
  `deliver=origin`, attached to the origin session), preserving any explicitly approved other target.
  Its scheduled final reply is the exact immutable prepared digest; the plugin does not also send.
  No exact-message reader or messaging API setup is required for this ordinary path. Backend delivery
  remains `host_pending`, `delivered=false`, `verification=awaiting_host`; preparation/final return is not
  delivery proof, and absent origin metadata is reported unconfigured. Native host retry semantics apply.
  Optional `delivery_owner=verified_sender` requires approved actual sender/exact-reader mappings and
  existing-message verification. Only this strict mode remains SETUP_BLOCKED/no-job until configured;
  it switches the SAME job to local-only with a SILENT final reply and owns all posts. Approved same-origin
  mode changes preserve job/origin/schedule, never enabling both send paths. See the bundled discovery
  skill for setup. Same-chat new sessions require public host metadata, never model origin claims. Suggestions and source IDs retain their existing seven-/60-day policies.
- **Explicit research pilots and historical reviews:** shadow/research_only `pilot_limit` retains the full
  index with audited `pilot_skipped` units; production selection is unchanged. `discovery_replay` distinguishes
  saved-input replay (original date/window/typed identities/primary resources, distinct review) from CURRENT
  fresh validation and targeted supplements. These nonproduction operations never automatically mutate old
  tasks or send a digest. Hash/schema incompatibility refuses replay. User corrections support approved
  structured active recommendation overlays while keeping accepted source evidence/history immutable.
  Normal digest text uses task titles, bounded operational status and a review token, not task UUIDs or
  raw backend exception/cache paths. Full diagnostics remain in `discovery_runs`.
- **Apple Reminders sync (only if you turn it on):** runs only when you ask (`/task ios`, "sync reminders").
  It calls the Hermes mobile connector's tools (`mobile_devices`, `mobile_reminders_list`,
  `mobile_reminder_create`, `mobile_reminder_update`, `mobile_reminder_complete`, `mobile_request_result`) on
  the paired phone you choose, reads only the list you choose, and writes only reminders it created. Each new
  reminder's notes hold a short marker with the task's ID. Mappings and pending phone requests are stored in
  plugin data. The phone answers only while the Hermes app is open; there is no background sync. Requires the
  Hermes mobile app (beta) and its device-access connector. Reminders has no "only if unchanged" write, so if
  you edit the same reminder field on the phone in the moment between Alchemy Task reading and writing it,
  the phone edit can be overwritten; changes made at other times are merged or shown as conflicts.
- **Setup writes:** plugin settings through Hermes's plugin settings API; Hermes's own `timezone` only if you
  agree during setup; a new workspace folder and Git repository if you start fresh; a
  `.alchemy-task-owner` marker in the workspace (listed in `.git/info/exclude`) so two installs do not
  silently share one workspace.
- **Plugin state:** locks, push receipts, active research runs, a one-hour capability cache and pending chat
  notes live in the plugin's profile-scoped data directory.
- No telemetry.

## Development

```bash
cd tests && python -m pytest -q        # needs pytest and ruamel.yaml (the UI route tests also need fastapi, httpx)
hermes plugins validate /path/to/alchemy-task
```

The UI source is in `ui/src` (React, shared by both hosts). `node ui/build.mjs` writes the committed bundles
`dashboard/dist/` and `desktop/plugin.js` (it needs esbuild). `node ui/build.mjs --dev` also builds a preview
in `ui/dev/` that runs the real UI against an in-memory demo backend; serve that folder and open `index.html`.
`node --test ui/test/lib.test.mjs` tests the date and Markdown helpers, and `node ui/dev/desktop-smoke.mjs`
checks that the desktop plugin loads and registers.

Tests use synthetic fixtures only.

## License

MIT
