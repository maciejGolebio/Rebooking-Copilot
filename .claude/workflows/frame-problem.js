export const meta = {
  name: 'frame-problem',
  description: 'Multi-lens framing of the Rebooking Copilot brief and fixtures: per-PNR facts, traps, assumptions, questions, business choices',
  whenToUse: 'Phase 1, called by /frame deep. Read-only, 5 agents (4 lenses + synthesis), ~8 min. Returns only the synthesis.',
  phases: [
    { title: 'Analyze', detail: '4 independent fixture-analyst lenses' },
    { title: 'Synthesize', detail: 'merge, dedupe, rank, surface conflicts' },
  ],
}

const A = args || {}
const BRIEF = A.brief || 'docs/ASSIGNMENT.md'
const FIXTURES = A.fixtures || 'fixtures'
const DECISIONS = A.decisions || 'docs/decisions.md'

const STR = { type: 'string' }
const STRS = { type: 'array', items: STR }

const LENS_SCHEMA = {
  type: 'object',
  properties: {
    lens: STR,
    perPnr: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          pnr: STR,
          candidateOffers: STRS,
          facts: STRS,
          naiveMoney: { type: 'string', description: 'gross / fees / net with inputs, computed by script; "n/a" if not computable and why' },
          risks: STRS,
        },
        required: ['pnr', 'candidateOffers', 'facts', 'risks'],
      },
    },
    traps: {
      type: 'array',
      items: {
        type: 'object',
        properties: { title: STR, evidence: STR, whyItMatters: STR, inFixtures: { type: 'boolean' } },
        required: ['title', 'evidence', 'whyItMatters', 'inFixtures'],
      },
    },
    assumptions: {
      type: 'array',
      items: {
        type: 'object',
        properties: { assumption: STR, why: STR, alternative: STR, impactIfWrong: STR },
        required: ['assumption', 'why', 'impactIfWrong'],
      },
    },
    questions: {
      type: 'array',
      items: {
        type: 'object',
        properties: { question: STR, whyItMatters: STR, defaultIfUnanswered: STR, askWhom: { type: 'string', enum: ['client', 'user'] } },
        required: ['question', 'whyItMatters', 'defaultIfUnanswered', 'askWhom'],
      },
    },
    businessChoices: {
      type: 'array',
      items: {
        type: 'object',
        properties: { choice: STR, options: STRS, suggestedDefault: STR, illustratedBy: STRS },
        required: ['choice', 'options', 'suggestedDefault'],
      },
    },
  },
  required: ['lens', 'traps', 'assumptions', 'questions', 'businessChoices'],
}

const SYNTH_SCHEMA = {
  type: 'object',
  properties: {
    pnrTable: {
      type: 'array',
      items: {
        type: 'object',
        properties: { pnr: STR, summary: STR, candidateOffers: STRS, keyDifferences: STRS, naiveMoney: STR, tricky: STR },
        required: ['pnr', 'summary', 'candidateOffers', 'keyDifferences', 'naiveMoney', 'tricky'],
      },
    },
    traps: LENS_SCHEMA.properties.traps,
    assumptions: LENS_SCHEMA.properties.assumptions,
    questionsForClient: {
      type: 'array',
      description: 'ranked, at most 8, each answerable in one line',
      items: LENS_SCHEMA.properties.questions.items,
    },
    decisionsForUser: {
      type: 'array',
      description: 'at most 6 product/policy stances for AskUserQuestion, recommendation first',
      items: {
        type: 'object',
        properties: { choice: STR, options: STRS, recommended: STR, why: STR, illustratedBy: STRS },
        required: ['choice', 'options', 'recommended', 'why'],
      },
    },
    conflicts: STRS,
  },
  required: ['pnrTable', 'traps', 'assumptions', 'questionsForClient', 'decisionsForUser', 'conflicts'],
}

const LENSES = [
  {
    key: 'money',
    perPnr: true,
    focus: 'Money & arithmetic: per-passenger vs total, which change fee applies and how often, currency of ticket vs offer, seats vs passengers, naive gross/fees/net per candidate (compute with a script), and every reason a cheaper number is not a real saving.',
  },
  {
    key: 'equivalence',
    perPnr: true,
    focus: 'Equivalence & traveler impact: every difference between what was booked and what is offered (flight number, departure/arrival times, arrival day, stops, carrier, cabin/fare product, refundability, baggage, future change fee). Which are hard constraints vs soft trade-offs, and what a traveler or a corporate travel manager would reject.',
  },
  {
    key: 'business',
    focus: 'Business ambiguity & requirement-sensing: everything the brief deliberately leaves undefined, which choices belong to the business (present as options with a default), which questions to ask the assessors (high-leverage, answerable in one line), and what each fixture booking is probably designed to probe.',
  },
  {
    key: 'production',
    focus: 'Production reality & scale: what the fixtures do not model but production will (snapshot staleness and re-pricing before action, inventory contention, exchange mechanics and residual credit, cross-carrier changes, taxes, multi-segment itineraries, free-text fare rules, supplier rate limits, volume and cost, observability, failure modes, autonomy risk).',
  },
]

phase('Analyze')
const lensResults = await parallel(
  LENSES.map((l) => () =>
    agent(
      `Lens: ${l.key.toUpperCase()}.\n${l.focus}\n\n` +
        `Inputs: the brief at ${BRIEF}, fixtures in ${FIXTURES}/, recorded decisions in ${DECISIONS} (binding where present).\n` +
        (l.perPnr ? `Cover every PNR in the fixtures in perPnr. ` : `Skip perPnr; cite PNR ids inside traps/choices instead. `) +
        `Compute any number with a script (jq, or python3 -c with Decimal) and include inputs. ` +
        `Label inferences and assumptions as such. Anything that needs a human decision goes into businessChoices. Do not modify files.`,
      { label: `lens:${l.key}`, phase: 'Analyze', schema: LENS_SCHEMA, agentType: 'fixture-analyst' },
    ),
  ),
)

const ok = lensResults.filter(Boolean)
const missing = LENSES.filter((_, i) => !lensResults[i]).map((l) => l.key)
if (missing.length) log(`Lenses with no result: ${missing.join(', ')}`)

phase('Synthesize')
const synthesis = await agent(
  `You are merging independent framing analyses of the Rebooking Copilot take-home (brief: ${BRIEF}, fixtures: ${FIXTURES}/, decisions: ${DECISIONS}).\n` +
    `Produce one per-PNR table, a deduplicated trap list, deduplicated assumptions, at most 8 ranked questions for the assessors ` +
    `(highest leverage first; each answerable in one line; include our default), at most 6 product/policy decisions for the user ` +
    `(options + recommendation + the PNRs that illustrate it), and every point where the lenses disagree (do not resolve silently). ` +
    `Where lenses report different numbers, recompute with a script from the fixtures.\n\nLens results (JSON):\n${JSON.stringify(ok, null, 1)}`,
  { label: 'synthesis', phase: 'Synthesize', schema: SYNTH_SCHEMA, agentType: 'fixture-analyst' },
)

return { synthesis, missingLenses: missing }
