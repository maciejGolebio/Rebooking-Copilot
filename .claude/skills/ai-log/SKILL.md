---
name: ai-log
description: Appends an entry to docs/AI_USAGE_LOG.md, which feeds the required AI-usage note. Use it proactively whenever the user rejects, corrects or overrides something you or a subagent proposed, and whenever you reject a reviewer's finding. Also /ai-log <note> for manual entries.
argument-hint: "[what happened]"
---

# /ai-log $ARGUMENTS

Append one row to the table in `docs/AI_USAGE_LOG.md`:

| When | Phase | AI proposed | Outcome | Why |
|---|---|---|---|---|
| `HH:MM` (from `date +%H:%M`) | kickoff / frame / design / slice:<name> / review / finalize | what was suggested, concretely (one line) | accepted / modified / rejected | the reason, in the user's words if they gave one |

- Be factual. Name the agent if it was a subagent (e.g. "money-safety-reviewer").
- Ask the user for the "why" only if the conversation doesn't make it clear.
- Note the best candidate for the AI-usage note: mark the row with **★** when it's a strong
  "rejected or corrected" example. A good one is a substantive judgment call, like an unsafe money shortcut,
  an LLM placed in the decision path, or an over-built feature. A typo doesn't count.
