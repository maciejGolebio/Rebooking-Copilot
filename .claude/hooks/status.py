#!/usr/bin/env python3
"""SessionStart hook: prints which delivery phases have produced their artifacts and the suggested
next command, so a session can /clear or resume and pick up where the files say it is."""
import os
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])


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


def main():
    slices = len(_git("log", "--oneline", "--extended-regexp", "--grep", r"^feat\(").splitlines())
    phases = [
        ("kickoff", "Not set yet" not in _read(ROOT / "CLAUDE.md")),
        ("frame", (ROOT / "docs" / "framing.md").exists()),
        ("design-doc", (ROOT / "DESIGN.md").exists()),
        ("slice", slices > 0),
        ("finalize", bool(_git("tag", "--list", "submission-v1").strip())),
    ]
    marks = " · ".join(f"{name} {'✓' if done else '✗'}" for name, done in phases)
    nxt = next((name for name, done in phases if not done), None)
    if nxt in ("slice", "finalize"):
        hint = f"/slice <name> ({slices} slice commit(s) so far), then /design-doc complete, /review-submission and /finalize"
    else:
        hint = "/" + nxt if nxt else "nothing; the submission is finalized"
    print(f"[rebooking-copilot] phases: {marks}. Suggested next for the user to run: {hint}.")
    print("State lives in files (docs/decisions.md, docs/framing.md, DESIGN.md); read them instead of relying on memory.")


if __name__ == "__main__":
    main()
