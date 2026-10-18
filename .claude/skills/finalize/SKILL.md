---
name: finalize
description: Phase 5b. Makes the submission complete and verifiable. Covers the README with run steps and a real example output, the AI-usage note (including disclosure of the prepared setup), an offline no-key run, secret and fixture checks, and packaging.
disable-model-invocation: true
---

# /finalize

Work through the checklist in order. Each item is **run or checked**, never assumed. Report ✓/✗ per item at the end.

1. **Tests are green**, using the test command from the CLAUDE.md quick reference.
2. **Clean offline run:** run `env -u ANTHROPIC_API_KEY <run command>` from a fresh shell. Paste the real output
   (trimmed, not hand-edited) into the README's "Example output" section. If an LLM mode exists, document how to
   enable it and show what happens without a key.
3. **README:** prerequisites, install (ideally none), run, test, where the output goes and its schema, what's stubbed,
   and a link to DESIGN.md. Keep it short.
4. **DESIGN.md:**
   - Every section the brief requires is there: approach & architecture, LLM boundary, money safety,
     scale/cost/observability, assumptions & open questions, what wasn't done / next.
   - The §8 Built/Stubbed table matches the code.
   - The assumptions agree with `docs/decisions.md`. Anything still provisional is clearly marked.
   - The §1 fixture walk-through matches the real output.
   - The §10 ADR table matches `docs/adr/README.md`. Every ADR has a concrete "Depends on (team & context)" section and matches the code.
5. **AI-usage note (§9):** write it from `docs/AI_USAGE_LOG.md`.
   - The tools and models, and how they were driven (phases, agents, where you decided).
   - At least one ★ suggestion that was rejected or corrected, with the reason.
   - **Disclosure:** the `.claude/` setup (skills, checklists, agents) was prepared with AI before the
     implementation work, and the knowledge checklists were AI-drafted and then reviewed.
6. **Fixtures unchanged:** `shasum -a 256 -c .claude/fixtures.sha256`.
7. **No secrets:**
   - `python3 .claude/hooks/guard.py --scan --history` scans the working tree and the git history with the guard's patterns.
   - `git ls-files` shows no `.env`.
8. **What ships:** ask (AskUserQuestion, header "Ship setup") whether to include `.claude/` and the `docs/` logs
   (decisions, framing, AI usage).
   - Recommended: yes, with the disclosure from item 5. It shows how the AI was driven, and the decision log backs up DESIGN.md.
   - Alternative: ship only `docs/decisions.md` and drop `.claude/`.
9. **Package (ask first):**
   - Commit and tag `submission-v1`.
   - Optionally run `git archive --format=zip -o ../rebooking-copilot.zip HEAD`.
   - Push only if the user says so.
   - Offer a short submission email draft. Never send it.
