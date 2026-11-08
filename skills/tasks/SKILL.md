---
name: tasks
description: Use when creating, updating or finding the user's tasks with Alchemy Task.
---

# Working with Alchemy Task tasks

Tasks are Markdown files in the user's workspace, one file per task, grouped by area. Always go through the
tools; they validate fields, keep IDs stable, commit and push, and queue research.

| You want to | Call |
|---|---|
| Add a task | `task_find` (check for an existing one), then `task_create` |
| Change status, dates, title, area or notes | `task_update` with the `task_id` |
| Look something up | `task_find` (`include_body: true` to read one task in full) |
| Work on or continue a task | `task_work_start`, then `task_checkpoint` when you stop |

## Creating

- Clean up phone-typed wording into a short imperative title. Put context, links and the user's reasoning in
  `notes`.
- **Due date:** if the user gave none, ask. Pass `undated: true` only when they said the task has no due date.
  Pass dates the way the user said them ("Friday", "Nov 13", "next week") or as `YYYY-MM-DD`; the tool reads
  them in the user's timezone. Numeric forms like 11/13 are refused as ambiguous, so convert those yourself.
- **One date by default.** A task's due date and scheduled (work) date are the same date unless the user asks
  for different ones. Pass just `due`; the tool sets both. Pass `scheduled` too only when the user names a
  separate work day ("due Friday, I'll do it Tuesday").
- **Area:** infer it from context when it is clear and tell the user what you chose. If unsure, call without
  `area` to get the list, then ask.
- **Research** runs automatically. Pass `research: false` only when the user says no research is needed.
- **Duplicates:** when the tool reports similar open tasks, prefer updating the existing one. Use
  `confirm_new: true` only when the user confirms it is different work. Same brand or wording is not enough;
  compare what the work actually is.
- Add `subtasks` only for real child steps, never one that repeats the task title. Use `plan` when the work
  has several phases or takes more than about 30 minutes.

## Updating

- Pass only the fields that change, plus a one-sentence `log` saying what changed and why. Write it as a
  neutral record ("Emailed the hall manager; confirmed 9 AM load-in"), not addressed to the user.
- Done: `status: done` (the completed date is set for you). Cancelled or waiting: include `reason`.
- Reopening a done or cancelled task needs `reopen: true`, only when the user wants it reopened.
- A user correction ("actually it's due Thursday") updates the existing task; never create a second one.

## Working on a task

- "Work on X", "continue X", "let's do X" → `task_work_start`, then do the work using what it returns
  (current state and next step first, then research and notes).
- Call `task_checkpoint` when the work is finished (`done`, with `evidence` of what you checked), when you
  need the user (`waiting_user`), when it waits on someone else (`waiting_other`), when it is blocked, or
  before stopping partway (`in_progress`). Do not wait to be asked.
- `done` and `next_step` are concrete: "Drafted the intro and three sections" rather than "made progress".

## Research

- Every new task is researched in the background. The task's `research` field shows `pending`, `running`,
  `complete`, `failed` or `skipped`; `task_find` with `include_body: true` shows the dossier and access plan.
- "Research it again" → `task_research` with the task. Never call it right after `task_create`.
- When a note says research finished, tell the user in a sentence. If access is missing, offer to set it up
  now or when they start the task; setting up access is not permission to do the task.

## Plain-language requests (users rarely remember slash commands)

Map what people say to tools; never tell them to type a command when you can do it yourself.

| The user says something like | Do |
|---|---|
| "set up my tasks", "get Alchemy Task working", "start over with setup" | load `alchemy-task:setup` and follow it |
| "is everything working?", "what's set up?", "is it syncing?", "task status" | `task_setup` `status`; show its receipt text |
| "sync my tasks", "push my changes", "why isn't GitHub updated?" | `task_setup` `push` (then `status` if it fails) |
| "check my task files", "anything broken in my tasks?", "fix the IDs" | `task_setup` `check_files` (`fix: true` when they ask to fix) |
| "what are today's tasks", "what's on my plate today" | `task_find` `period: today` |
| "tasks for this week", "what's coming up" | `period: this_week` (on a weekend this covers the coming week) |
| "tasks for Monday", "what's on Friday" | `period: monday` / `friday` (the next one, or today) |
| "tomorrow", "next week" | `period: tomorrow` / `next_week` |
| "what's overdue", "what did I miss" | `period: overdue` |
| "show my open work", "what's in my bakery area" | `task_find` with status/area filters |
| "move X to Friday", "push X to next week", "X is now due Friday" | `task_update` `due` (both dates move) |
| "keep the deadline but I'll do X Tuesday" | `task_update` `scheduled` + `keep_separate: true` |
| "move all the overdue BFCM ones to Wednesday" | `task_update` per task, after listing which ones you will change |
| "research X again", "redo the research" | `task_research` with the task |
| "work on X", "pick up X", "continue X", "where was I on X?" | `task_work_start` |
| "I'm done with X", "X is finished", "drop X", "X is waiting on Sam" | `task_update` (or `task_checkpoint` inside a work session) |
| "set up a daily digest from my email", "add a discovery for work" | load `alchemy-task:discovery`; `discovery_stream` `create` |
| "change my digest to 7 PM", "make it weekdays only", "stop the work digest" | `discovery_stream` `update` / `remove` (confirm first) |
| "run my digest now", "check my email for tasks now" | `discovery_stream` `run_now` |
| "turn off Alchemy Task's schedules", "stop the background jobs", "uninstall" | confirm, then `task_setup` `teardown` with `user_confirmed: true`; for uninstalling, mention `hermes plugins remove alchemy-task` afterwards |
| "sync reminders", "sync iOS", "sync my iPhone", "update my Reminders" | `task_ios` (sync); report its message as given, including "waiting for your iPhone" |
| "put my tasks in Apple Reminders", "set up iPhone reminders" | `task_ios` `setup`: ask which areas, show the preview, then `user_approved: true` |
| "stop syncing reminders" | confirm, then `task_ios` `disable` (reminders stay on the phone) |
| "change my timezone / default area / workspace", "stop researching new tasks by default" | `task_setup` `save` with just that setting |
| "add a garden area", "I don't need the bakery area any more" | `task_setup` `save` `add_areas` / `remove_areas` |
| "make the discovery hourly", "change my digest to 9 AM", "weekdays only" | `discovery_stream` `update` with just `frequency` or `time` (a time on an hourly stream makes it daily at that time) |
| "I just connected Gmail, add it to discovery", "also check #launch in Slack" | load `alchemy-task:discovery`; check you can read it, agree the scope, then `discovery_stream` `update` `add_sources` (never resend the whole list) |
| "stop checking the newsletter folder" | `discovery_stream` `update` `remove_sources` |
| "push my tasks to a different GitHub repo" | `task_setup` `git_check` `remote_url` (+ `replace_remote` once they confirm) |

Change one setting at a time and keep everything else as it is. Confirm what changed, and for schedules say the
new time in the user's timezone.

Overdue follows Google Tasks: a task is overdue when its date has passed (its work date, when the user set a
separate one). Rescheduling takes it off the overdue list. When listing overdue tasks, offer to reschedule
them.

**Rescheduling.** "Move X to Friday", "push X to next week", "X is now due Friday": pass the new date as
`due` (or `scheduled`); the tool moves both together. Only when the user asks for two different days ("keep
the deadline, but I'll work on it Tuesday") pass both, or the one that changes plus `keep_separate: true`.
Pass dates as the user said them ("Friday", "Nov 13", "next week"); the tool reads them in the user's
timezone. Confirm the new date in the reply.

Let the tool work out the dates: pass `period` rather than computing dates yourself. Answer with the period's
tasks by day, saying whether each is scheduled for that day or due then, then the overdue ones (the tool lists
the most recent; mention the total). Keep it short: title, area when there are several, and the reason. Use
`agenda_from`/`agenda_to` only for other ranges ("the 20th to the 25th").

## Apple Reminders (optional)

Only open tasks get a new reminder (and not ones more than 14 days overdue). Title, due date and the checkbox
stay in sync both ways when the user syncs; notes, research and everything else stay in the task file. The phone
only answers while the Hermes app is open, so when the tool says it is waiting, tell the user to open the app
and sync again. Never call a sync done while the tool reports waiting. For a conflict (changed in both places),
show both values and ask which to keep, then `resolve`.

## When a tool says `ok: false`

Read `needs` and `message`: ask the user for the missing piece (`due`, `area`, `reason`, `reopen`), pick from
`candidates` (`task`, `duplicate_check`), or run setup (`setup`). Then call again. Never work around the tools by
writing task files directly.

## Reporting back

Confirm briefly: title, area, due date, and anything you inferred that the user may want to correct. If the
result says the push is pending, mention that it is saved and will sync.
