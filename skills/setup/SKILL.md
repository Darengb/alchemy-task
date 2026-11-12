---
name: setup
description: Use when the user wants to set up or change Alchemy Task ("set up my tasks").
---

# Setting up Alchemy Task

Setup is a short conversation. You hold it; `task_setup` checks and saves each decision. Never write the
plugin's settings any other way. Call `task_setup` with `action: status` first and after each step: its
receipt says what is done and what is next. Setup can stop and resume at any time.

Keep it light: one question at a time, recommend a default, explain briefly why it matters.

## Discovery prerequisites

Discovery setup is separate from ordinary task creation. Load `alchemy-task:discovery` for the full source-first contract. Confirm approved source/account/scope/read-method mappings and actual reader toolsets, not credentials. Every reader is a read-only tool (connector, MCP server or another plugin's tool), never terminal, code or file tools; the discovery skill covers wrapping a user's own script as a read-only MCP server. Declare relevance rules and only their required identity fields. Name-independent public feeds do not need a personal name. Confirm needed account-specific identities using approved metadata, installing-profile memory/SOUL and documents; never infer names from email or read other profiles. Save with `discovery_config`, not hand-edited state.

Discovery research needs no timeout configuration: it runs as short calls inside the default Hermes tool deadline, so never ask the operator to raise host timeouts. If an operator has already lowered Hermes tool timeouts below about 330 seconds, tell them discovery research calls need the per-call budget lowered to match (see the runner contract); never raise timeouts for them. Discovery proposals promote their exact accepted dossier rather than queueing generic research. Ordinary direct task creation retains its existing research behavior.

Discovery delivery defaults to native Hermes cron origin delivery. Discover current public host cron/origin capabilities, explain that Hermes posts the exact prepared review here, and obtain ordinary stream approval. No extra messaging API or exact-reader setup is needed. Missing origin metadata and actual delivery remain unverified, not invented. Optional verified_sender mode is only for an available actual sender/exact-reader pair after explicit approval and existing-message verification; it alone uses a local-only job/SILENT final reply. The discovery skill has the full one-owner setup and same-job switch procedure.

## 1. Timezone (always first)

If the receipt says the timezone is unset or UTC, it was probably never configured (common on fresh Cloud
agents). Ask which city or timezone they are in; accept UTC only if they confirm it. Save it with
`save` + `timezone` (an IANA name such as `America/New_York`). If Hermes's own timezone was unset, also pass
`set_hermes_timezone: true`. Show times to the user in their timezone and 12-hour format, never UTC.

## 2. Workspace

Tasks are Markdown files in a Git repository. Ask whether they already keep notes in a repository (for
example an Obsidian vault).

- **Existing notes or vault:** get the folder path, then `inspect` it. If `tasks_found` > 0, reuse its layout.
  If tasks sit elsewhere (`task_folders_elsewhere`), set `task_dir` to match (it must contain `{area}`).
  Only the task folders are used; the rest of the vault is not read. The user's own Git setup pushes.
- **Fresh start:** propose a workspace in the Hermes data folder, for example `<hermes home>/tasks`, and
  agree the areas in the next step before calling `save` with `create_workspace: true` and those areas.
  Inside a Nous Cloud agent the Hermes home is `/opt/data`.

## 3. Areas

Ask: **"Do you have distinct areas of your life or projects that you'd like to keep separate?"**
Offer **Yes** and **No, keep everything together**, with no recommended answer.

- **Yes:** ask the open-ended follow-up: "What are they? For example, your job, a business or independent
  project, and personal life." Use their answer to propose area names and confirm them. Do not turn this
  follow-up into multiple choice or automatically subdivide their answer.
- **No:** use one area, `general`, as the default and move on without another organization question.
  If they already have a single area, reuse its name instead.

Areas follow the parts of life the user wants to manage separately. Projects within a full-time job
usually share that job's area; an independent business, music act or app may have its own area if the user
wants it separate. Email accounts, channels, departments and topics do not automatically become areas.
Multiple accounts can feed one area. Do not aim for a target number of areas or impose a maximum.
Reuse an existing layout without silently moving, merging or renaming existing tasks; ask before any
reorganization if their answer conflicts with that layout.

Save `areas` and, for a single area, set `default_area` to it so tasks need no area question. For multiple
areas, save a default only if the user chooses one or one is clearly established. Only discuss separate
Hermes profiles or bots if the user mentions them or their skills clearly show them; never ask them to
create a profile for Alchemy Task.

## 4. Git delivery

Every task change is committed and pushed so it syncs to their other devices. Call `git_check`.

- If it is ready, say so.
- No remote yet: they create an empty **private** repository (for example at github.com/new) and give you
  the URL; pass it as `remote_url`.
- Git cannot push yet (common on a fresh Cloud agent) and they want backup or sync: walk them through
  connecting GitHub with the `github-auth` skill. Prefer `gh auth login` in the browser, so no token is
  pasted into chat. The plugin pushes with this machine's own Git setup, so call `git_check` again once
  they are connected.
- `none` keeps local history only; say clearly that tasks are then not backed up.

## 5. What happens automatically, and the scheduled jobs

Tell them plainly, once:
- Every new task is researched in the background on their model (it uses their tokens), unless they say no
  research is needed. Research only reads; it never changes anything. Research model: research can run on a
  different, cheaper model; to set one, follow the Research model section of `alchemy-task:tasks`.
- Work sessions ("work on X") keep a Current state section in the task; if a chat stops without a
  checkpoint, Alchemy Task writes one itself.

Then call `jobs_preview` and show the job list (name, when, what it does, cost). Ask once: "Create these
jobs?" Only after a clear yes call `jobs_create` with `user_approved: true`. If they decline, everything
else still works; offer again later.

## 6. Finish

Call `status` and show the receipt text. Offer a first task ("tell me something you need to do"). Discovery
streams (daily task suggestions from their email or chat) are set up separately: offer them if they want
them, or say they can ask later.

## Changing settings later

The same tool handles changes ("switch my default area to home", "move my tasks to a new repo"). `teardown`
removes the scheduled jobs; task files and settings stay.
