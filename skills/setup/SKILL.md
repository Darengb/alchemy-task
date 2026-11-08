---
name: setup
description: Use when the user wants to set up or change Alchemy Task ("set up my tasks").
---

# Setting up Alchemy Task

Setup is a short conversation. You hold it; `task_setup` checks and saves each decision. Never write the
plugin's settings any other way. Call `task_setup` with `action: status` first and after each step: its
receipt says what is done and what is next. Setup can stop and resume at any time.

Keep it light: one question at a time, recommend a default, explain briefly why it matters.

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
  `save` it with `create_workspace: true`. Inside a Nous Cloud agent the Hermes home is `/opt/data`.

## 3. Areas

Areas group tasks (for example work, personal, a side business). Look at what the user already has
(existing area folders, their skills, how they talk about their work) and propose a short list; two or
three is typical. Save `areas` and, if one is clearly the default, `default_area`. Only discuss separate Hermes
profiles or bots if the user mentions them or their skills clearly show them; never ask them to create a
profile for Alchemy Task.

## 4. Git delivery

Every task change is committed and pushed so it syncs to their other devices. Call `git_check`.

- If it is ready, say so.
- No remote yet: they create an empty **private** repository (for example at github.com/new) and give you
  the URL; pass it as `remote_url`.
- Fresh Cloud agents have no Git login: save `git_transport: deploy_key`, call `git_check`, show the public
  key and the link it returns, and ask them to add it with **Allow write access**. Run `git_check` again.
- If SSH cannot work, the fallback is `git_transport: token`: they enter a fine-grained token limited to that
  repository in the plugin settings (Desktop or the agent dashboard). Never ask them to paste a token in chat.
- `none` keeps local history only; say clearly that tasks are then not backed up.

## 5. What happens automatically, and the scheduled jobs

Tell them plainly, once:
- Every new task is researched in the background on their model (it uses their tokens), unless they say no
  research is needed. Research only reads; it never changes anything.
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
