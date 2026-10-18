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
| 17:55 | frame | A fixed "cash only" saving definition | modified | User: "allow to select". Now a configurable `settlementPolicy`, default cash-only (D-10) |
| 17:55 | frame | Four hard blocks: downgrade, lost refundability, fewer bags, carrier change/extra stop | modified ★ | User kept only "fewer bags"; the rest became review-level differences judged by the LLM with confidence capped at MEDIUM (D-11, D-16). Why: _add_ |
| 17:55 | frame | Re-shop in the ticket's currency for a currency mismatch (point-of-sale reasoning) | rejected | User chose a stubbed, timestamped FX table; point of sale goes to the assessors (D-12). Why: _add_ |
| 17:55 | frame | Analyst subagent's default: count travel credit at face value | rejected | User kept cash-only as the default (D-10) |
| 18:16 | design | Architecture A (safety-first pipeline, one LLM call) + grafts | rejected ★ | User chose B, an LLM agent over deterministic tools (D-19, ADR-0007). Why: _add_ |
| 18:16 | design | Direct Anthropic SDK behind the Reasoner interface | rejected | User chose LangChain (D-20, ADR-0008). Why: _add_ |
| 18:16 | design | A replay cache to make Claude mode reproducible | rejected | User: claim determinism for stub mode only (D-23) |
| 18:29 | slice:core | Plain dataclasses for the loader's result types, next to pydantic input models | corrected ★ | User asked "what is the point to use dataclasses while we [use] pydantic?". The results reach the output and its JSON Schema (D-05), and the frozen dataclasses held mutable lists; switched to frozen pydantic models with tuples |
| 19:39 | slice:decision | money-safety-reviewer: 10 findings (duplicate ids oversell seats, FX seam trusted blindly, REBOOK onto departed flights, ledger leaves seats empty, …) | accepted | All reproduced; fixed with regression tests (D-33–D-35). One left as a documented limitation: no FX plausibility check against a reference |
| 19:39 | slice:decision | test-engineer: 4 needs-decision gaps in the seat-ledger and fingerprint spec | accepted | Turned into user decisions D-31/D-32 before implementing |
| 20:15 | slice:reasoner | Claude Opus 5.5 (the API reference's default) for the agent | rejected | User chose Claude Sonnet 5.5 at effort medium (D-36). Why: _add_ |
| 20:15 | slice:reasoner | One way to switch Claude mode (a flag) | modified | User asked for both a flag and an env var, flag wins (D-37) |
| 20:15 | slice:reasoner | Claude's own test draft: a faithfulness test that checked the rationale against a dump containing the rationale (vacuous), and a seat test that couldn't reach the fallback | corrected | Caught by Claude before implementing; both rewritten so they can fail |
| 20:56 | review | Round 2, three independent reviewers (money safety, LLM boundary, assessor's read): a number laundered through an echoed tool error, an offer id able to close the FACTS block, an agent decline hiding a credit saving, an unpriced sibling left at HIGH, a freed seat never re-offered, LangChain resending the fallback block as `from_`, `api_key=""` disabling `ant auth` | accepted | All serious findings reproduced before fixing; fixed with regression tests, including the real ChatAnthropic run offline against canned API responses (D-41) |
| 20:56 | review | D-34 as built: the agent may approve a PRICE_ANOMALY offer at MEDIUM | modified ★ | User: "No, review only". A possible feed error isn't a trade-off for the model to weigh, so the agent can't approve it (D-40) |
| 20:56 | review | DESIGN v1 claims written by Claude: "I've asked the assessors"; "every number must appear in what the model saw" | corrected | The questions email was never sent; user chose to say "would ask". The faithfulness check was weaker than claimed; it is now a typed (amount, currency) check, and its remaining limit (a misattributed real amount) is stated and tested |
| 20:56 | review | Claude's own rationale template ("0.9276 USD→EUR") | corrected | The new number check flagged it as an unbacked money amount; reworded to "at the USD→EUR rate 0.9276" so the template passes the check the agent must pass |
