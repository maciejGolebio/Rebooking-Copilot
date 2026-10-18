---
name: decide
description: Turns an open business, product, methodology or technology choice into an explicit user decision and records it as an ADR entry in docs/decisions.md. Use it whenever work depends on something undecided (equivalence rules, acceptable inconvenience, autonomy level, thresholds, FX handling, confidence semantics, volume assumptions, stack, library, test approach) instead of silently picking.
argument-hint: "<topic>"
---

# /decide $ARGUMENTS

1. **Already decided?** Search `docs/decisions.md`. If it's there, apply the decision, mention its D-id, and stop.
2. **Frame it:** give the context in 2 lines and cite the fixture facts or PNR ids. Offer 2–4 options, each with a
   one-line trade-off. Where sensible, include "make it configurable, default X" and "ask the client; proceed with
   default X". Put your recommendation first, labelled "(Recommended)".
3. **Ask** with AskUserQuestion: one question per decision. Batch related decisions, at most 4 per call.
   Headers are 12 characters or fewer.
4. **Record** the next `D-xx` in `docs/decisions.md`, using the entry format in that file, and update its index table.
   `Decided by: user`, or `default` if the user delegated the choice.
5. **Architecture-significant?** For stack, dependencies, LLM integration or authority, agent shape, the data or money
   model, storage or deployment, also write `docs/adr/NNNN-<slug>.md` from the template in `docs/adr/README.md`. Fill
   in **"Depends on (team & context)"**: where a real team could decide differently (team experience, existing platform,
   policy, risk appetite). Add a row to the ADR index, and link the ADR from the D-xx entry. A changed decision gets a
   new ADR marked "supersedes"; old ADRs are never rewritten.
6. **Provisional?** If the answer is "ask the client", add the question to `docs/open-questions.md` with the default.
   Add it to `docs/questions-email.md` too if the email hasn't gone out yet.
7. **Reflect it:** update the affected DESIGN.md section and the assumptions table, if DESIGN.md exists.

Don't use this for implementation details that have an obvious convention (naming, private helper layout,
formatting). Pick one and move on. Ask only when the answer changes behaviour, money, risk or scope.
