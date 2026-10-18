#!/usr/bin/env python3
"""Timebox for the take-home (~2-3 h) + session status.

  timebox.py start [minutes] [--force]  start the clock (default 180); refuses to reset a running one without --force
  timebox.py budget <minutes>           change the budget, keep elapsed time
  timebox.py pause | resume             exclude real breaks (not waiting for the assessors; log pauses)
  timebox.py stop                       stop the clock and print the total
  timebox.py status                     human-readable status incl. remaining minutes
  timebox.py prompt-hook                UserPromptSubmit hook: one context line (silent without a timer)
  timebox.py session-hook               SessionStart hook: phase artifacts, timer, suggested next step

Minutes accept "150", "150m", "2h", "2h30m". State lives in .claude/state/timer.json (gitignored).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
STATE = ROOT / ".claude" / "state" / "timer.json"


class UsageError(Exception):
    pass


def parse_minutes(text):
    m = re.fullmatch(r"\s*(?:(\d+)h)?\s*(?:(\d+)m?)?\s*", text or "")
    if not m or not (m.group(1) or m.group(2)):
        raise UsageError(f"Can't read minutes from {text!r}; use e.g. 180, 150m, 2h30m.")
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def load():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def elapsed(state):
    end = state.get("stopped_at") or time.time()
    paused = state.get("paused_total", 0)
    if state.get("paused_at"):
        paused += end - state["paused_at"]
    return max(0, end - state["started_at"] - paused)


def fmt(seconds):
    minutes = int(seconds // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


def summary(state):
    budget = state["budget_min"] * 60
    spent = elapsed(state)
    pct = int(100 * spent / budget) if budget else 0
    remaining = round(max(0, budget - spent) / 60)
    mode = "stopped" if state.get("stopped_at") else "paused" if state.get("paused_at") else "running"
    return f"{fmt(spent)} of {fmt(budget)} ({pct}%, remaining {remaining}m, {mode})", pct, mode


def cmd_start(args):
    force = "--force" in args
    rest = [a for a in args if a != "--force"]
    minutes = parse_minutes(rest[0]) if rest else 180
    state = load()
    if state and not state.get("stopped_at") and not force:
        print(f"Timer already running ({summary(state)[0]}). Use `budget <minutes>` to change the budget, or `start {minutes} --force` to reset.")
        return
    save({"started_at": time.time(), "budget_min": minutes, "paused_total": 0, "paused_at": None, "stopped_at": None})
    print(f"Timebox started: budget {fmt(minutes * 60)}.")


def cmd_budget(args):
    if not args:
        raise UsageError("budget needs minutes, e.g. `budget 150`.")
    state = load()
    if not state:
        print("No timer yet; use `start <minutes>`.")
        return
    state["budget_min"] = parse_minutes(args[0])
    save(state)
    print("Budget updated: " + summary(state)[0])


def cmd_pause(_):
    state = load()
    if not state or state.get("stopped_at") or state.get("paused_at"):
        print("Nothing to pause.")
        return
    state["paused_at"] = time.time()
    save(state)
    print("Paused at " + summary(state)[0])


def cmd_resume(_):
    state = load()
    if not state or not state.get("paused_at"):
        print("Not paused.")
        return
    state["paused_total"] = state.get("paused_total", 0) + time.time() - state["paused_at"]
    state["paused_at"] = None
    save(state)
    print("Resumed: " + summary(state)[0])


def cmd_stop(_):
    state = load()
    if not state:
        print("No timer.")
        return
    if not state.get("stopped_at"):
        now = time.time()
        if state.get("paused_at"):
            state["paused_total"] = state.get("paused_total", 0) + now - state["paused_at"]
            state["paused_at"] = None
        state["stopped_at"] = now
        save(state)
    print("Timebox stopped: " + summary(state)[0])


def cmd_status(_):
    state = load()
    print("Timebox: " + summary(state)[0] if state else "Timebox: not started (suggest the user run /checkpoint start <minutes>).")


def cmd_prompt_hook(_):
    state = load()
    if not state or state.get("stopped_at"):
        return
    line, pct, mode = summary(state)
    advice = ""
    if mode == "running" and pct >= 100:
        advice = " Budget exceeded: stop adding scope and suggest the user run /finalize; list what you'd do with more time."
    elif mode == "running" and pct >= 75:
        advice = " Over 75% used: finish the current slice, prefer stub+describe, suggest /review-submission then /finalize."
    print(f"[timebox] {line}.{advice}")


def _read(path):
    try:
        return path.read_text()
    except OSError:
        return ""


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def cmd_session_hook(_):
    slices = len(_git("log", "--oneline", "--extended-regexp", "--grep", r"^feat\(").splitlines())
    state = load()
    finalized = bool(_git("tag", "--list", "submission-v1").strip()) or bool(state and state.get("stopped_at"))
    phases = [
        ("kickoff", "Not set yet" not in _read(ROOT / "CLAUDE.md")),
        ("frame", (ROOT / "docs" / "framing.md").exists()),
        ("design-doc", (ROOT / "DESIGN.md").exists()),
        ("slice", slices > 0),
        ("finalize", finalized),
    ]
    marks = " · ".join(f"{name} {'✓' if done else '✗'}" for name, done in phases)
    nxt = next((name for name, done in phases if not done), None)
    if nxt in ("slice", "finalize"):
        hint = f"/slice <name> ({slices} slice commit(s) so far), then /review-submission and /finalize"
    else:
        hint = "/" + nxt if nxt else "nothing; the submission is finalized"
    timer = summary(state)[0] if state else "not started"
    print(f"[rebooking-copilot] phases: {marks}. Suggested next for the user to run: {hint}. Timebox: {timer}.")
    print("State lives in files (docs/decisions.md, docs/framing.md, DESIGN.md, docs/TIMELOG.md); read them instead of relying on memory.")


COMMANDS = {
    "start": cmd_start,
    "budget": cmd_budget,
    "pause": cmd_pause,
    "resume": cmd_resume,
    "stop": cmd_stop,
    "status": cmd_status,
    "prompt-hook": cmd_prompt_hook,
    "session-hook": cmd_session_hook,
}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "status"
    if name not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    try:
        COMMANDS[name](sys.argv[2:])
    except UsageError as err:
        print(f"{err}\n{__doc__}")
        sys.exit(1)
