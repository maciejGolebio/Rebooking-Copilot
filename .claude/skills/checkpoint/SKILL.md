---
name: checkpoint
description: Timebox control. Starts, pauses, resumes or stops the timer, changes the budget, or checks progress against the phase plan and proposes cuts. Use it at phase boundaries, and whenever the [timebox] context line shows 75% or more used.
argument-hint: "[start <minutes> | budget <minutes> | pause | resume | stop | status]"
---

# /checkpoint $ARGUMENTS

- **`start <min>` / `budget <min>` / `pause` / `resume` / `stop`:** run `python3 .claude/hooks/timebox.py $ARGUMENTS`
  and print the result. `start` never resets a running timer (that needs `--force`). Use `budget` to change the target.
- **Pause only for real breaks.** Don't pause while waiting for the assessors' reply; work carries on with the stated
  defaults. Every pause and its reason goes into the time note.
- **No argument, or `status`:**
  1. Run `python3 .claude/hooks/timebox.py status`.
  2. Compare it with the phase plan in `docs/TIMELOG.md`. List what's done, in progress and remaining.
  3. If you're behind, propose a cut list: what to stub, what to only describe in DESIGN.md, and what to drop.
     Ask with AskUserQuestion (header "Cuts", multiSelect). Record the accepted cuts in DESIGN.md §8.
  4. Append a row to the "Checkpoints" table in `docs/TIMELOG.md` and fill "Actual" for any phase that's finished.
