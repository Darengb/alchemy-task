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

## Creating

- Clean up phone-typed wording into a short imperative title. Put context, links and the user's reasoning in
  `notes`.
- **Due date:** if the user gave none, ask. Pass `undated: true` only when they said the task has no due date.
  Convert relative dates ("Friday") to `YYYY-MM-DD` in the user's timezone; `task_find` returns `today`.
- `scheduled` is when the user plans to work on it; `due` is the deadline. Do not copy one into the other
  unless the user said so ("due today" sets both).
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

## When a tool says `ok: false`

Read `needs` and `message`: ask the user for the missing piece (`due`, `area`, `reason`, `reopen`), pick from
`candidates` (`task`, `duplicate_check`), or run setup (`setup`). Then call again. Never work around the tools by
writing task files directly.

## Reporting back

Confirm briefly: title, area, due date, and anything you inferred that the user may want to correct. If the
result says the push is pending, mention that it is saved and will sync.
