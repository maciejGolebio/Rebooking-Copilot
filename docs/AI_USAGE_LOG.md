# AI usage log

Raw material for the required AI-usage note (DESIGN.md §9 or README): which tools were used, how
they were driven, and at least one suggestion that was **rejected or corrected, and why**. Append as
you go with `/ai-log`; Claude also logs automatically when you correct it. Don't reconstruct it at the end.

**Tools:** Claude Code (desktop app, Code tab) with Claude Opus 5.5 (`claude-opus-5-5`); subagents pin sonnet or opus per `.claude/agents/`. The project setup is in `.claude/`: agents, skills,
workflows and hooks; see `docs/AI_SETUP.md`.

**Setup prep (before the implementation work):** the `.claude/` setup was generated with Claude Code on 2026-10-18. Two
independent review agents then checked it, and their findings were applied. Add your own corrections of the
setup below; they count as "rejected or corrected" examples too.

| When | Phase | AI proposed | Outcome | Why |
|------|-------|-------------|---------|-----|
| setup | setup | A timebox: timer hook, `/checkpoint`, minute budgets per phase | rejected ★ | User: "it looks stupid". Removed entirely; scope discipline stays as "build the risky core, stub and describe the rest" |
| 17:36 | kickoff | Pre-set rule D-00a: the LLM may only explain or escalate, never approve | modified ★ | User chose "the LLM decides within guardrails": a real decision role inside a code-built eligible set, re-validated by code (D-07, ADR-0004) |
| 17:36 | kickoff | A standard-library-only runtime (recommended for a zero-install run) | rejected | User allowed mainstream libraries: pydantic, the LLM SDK, LangChain (D-04, ADR-0003) |
| 17:36 | kickoff | Record decisions only in the ADR-lite log `docs/decisions.md` | modified | User asked for formal ADRs with a note on team experience and context, easy for an AI reviewer to find (`docs/adr/`) |
| 17:36 | kickoff | "Python 3.11+" | modified | User pinned Python 3.14 (D-01) |
