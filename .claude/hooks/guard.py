#!/usr/bin/env python3
"""Guard for the Rebooking Copilot repo.

As a PreToolUse hook (Write/Edit/MultiEdit/NotebookEdit/Bash) it blocks (exit 2, reason on stderr):
  1. writes or mutating shell commands that touch fixtures/ - the dataset the submission ran
     against must stay byte-identical (backstop: .claude/fixtures.sha256)
  2. content or commands containing something that looks like a secret - keys live in env vars only

As a CLI:  guard.py --scan [--history]
  scans tracked + untracked-not-ignored files (and with --history the whole git log) for
  secret patterns; prints masked matches; exit 1 if any are found.
"""
import json
import os
import re
import subprocess
import sys

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),  # Anthropic
    re.compile(r"sk-[A-Za-z0-9]{32,}"),  # OpenAI-style
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]"),
]
SELF = os.path.realpath(__file__)


def project_dir(data=None):
    return os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or (data or {}).get("cwd") or os.getcwd())


def find_secret(text):
    for pattern in SECRET_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def mutates_fixtures(command, project):
    ref = rf"(?:(?<![\w./-])(?:\./)?fixtures/|{re.escape(project)}/fixtures/)"
    seg = r"[^;&|\n]*"
    patterns = [
        rf"\b(?:rm|mv|tee|truncate|touch|chmod|chown|ln)\b{seg}{ref}",
        rf"\bsed\b{seg}\s(?:-[a-zA-Z]*i\b|--in-place){seg}{ref}",
        rf">>?\s*[\"']?{ref}",
    ]
    return any(re.search(p, command) for p in patterns)


def block(reason):
    print(f"Blocked by .claude/hooks/guard.py: {reason}", file=sys.stderr)
    return 2


def hook():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    tool_input = data.get("tool_input") or {}
    project = project_dir(data)

    if data.get("tool_name") == "Bash" or "command" in tool_input:
        command = tool_input.get("command") or ""
        if mutates_fixtures(command, project):
            return block("this command would modify fixtures/, which is read-only. Put extra test data under tests/.")
        if find_secret(command):
            return block("the command contains something that looks like an API key. Use an env var set outside Claude.")
        return 0

    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if path and os.path.realpath(path).startswith(os.path.join(project, "fixtures") + os.sep):
        return block(
            "fixtures/ is read-only (it is the dataset the submission ran against; checksums in "
            ".claude/fixtures.sha256). Put extra test data under tests/."
        )
    texts = [tool_input.get(k) for k in ("content", "new_string", "new_source")]
    texts += [e.get("new_string") for e in tool_input.get("edits") or [] if isinstance(e, dict)]
    if find_secret("\n".join(t for t in texts if isinstance(t, str))):
        return block("the content looks like a secret/API key. Read keys from environment variables; never write them to files.")
    return 0


def mask(secret):
    return secret[:8] + "…" + f"({len(secret)} chars)"


def scan(history):
    project = project_dir()
    found = 0
    files = subprocess.run(
        ["git", "-C", project, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, text=True
    ).stdout.split("\0")
    for rel in filter(None, files):
        path = os.path.join(project, rel)
        if os.path.realpath(path) == SELF or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    secret = find_secret(line)
                    if secret:
                        found += 1
                        print(f"{rel}:{n}: {mask(secret)}")
        except (UnicodeDecodeError, OSError):
            continue
    if history:
        log = subprocess.run(["git", "-C", project, "log", "-p", "--all"], capture_output=True, text=True, errors="replace").stdout
        for line in log.splitlines():
            if line.startswith("+") and "guard.py" not in line:
                secret = find_secret(line)
                if secret:
                    found += 1
                    print(f"git history: {mask(secret)}")
    print(f"secret scan: {found} match(es){' incl. history' if history else ''}")
    return 1 if found else 0


if __name__ == "__main__":
    if "--scan" in sys.argv:
        sys.exit(scan("--history" in sys.argv))
    sys.exit(hook())
