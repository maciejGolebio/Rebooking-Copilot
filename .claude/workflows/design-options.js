export const meta = {
  name: 'design-options',
  description: 'Judge panel: 3 Rebooking Copilot architectures from different angles, scored against the rubric',
  whenToUse: 'Phase 2, called by /design-doc options deep. Read-only, 4 agents (3 architects + judge).',
  phases: [
    { title: 'Propose', detail: '3 solution-architect angles in parallel' },
    { title: 'Judge', detail: 'score vs rubric, pick, graft best ideas' },
  ],
}

const A = args || {}
const DECISIONS = A.decisions || 'docs/decisions.md'
const FRAMING = A.framing || 'docs/framing.md'

const STR = { type: 'string' }
const STRS = { type: 'array', items: STR }

const OPTION_SCHEMA = {
  type: 'object',
  properties: {
    name: STR,
    angle: STR,
    summary: STR,
    flow: STRS,
    llmDoes: STRS,
    deterministicDoes: STRS,
    moneySafety: STRS,
    scaleCost: STRS,
    observability: STRS,
    autonomy: STR,
    risks: STRS,
    buildInPrototype: STRS,
    stubOrDescribe: STRS,
    needsDecision: STRS,
  },
  required: ['name', 'angle', 'summary', 'flow', 'llmDoes', 'deterministicDoes', 'moneySafety', 'scaleCost', 'risks', 'buildInPrototype', 'stubOrDescribe'],
}

const SCORE = { type: 'integer', minimum: 1, maximum: 5 }
const JUDGE_SCHEMA = {
  type: 'object',
  properties: {
    scores: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: STR,
          framing: SCORE,
          boundary: SCORE,
          moneySafety: SCORE,
          scaleCostObs: SCORE,
          pragmatism: SCORE,
          communication: SCORE,
          oneLine: STR,
        },
        required: ['name', 'framing', 'boundary', 'moneySafety', 'scaleCostObs', 'pragmatism', 'communication', 'oneLine'],
      },
    },
    recommended: STR,
    why: STR,
    graftFromOthers: STRS,
    presentAsAlternative: STRS,
    questionsForUser: {
      type: 'array',
      items: {
        type: 'object',
        properties: { question: STR, options: STRS, recommended: STR },
        required: ['question', 'options', 'recommended'],
      },
    },
  },
  required: ['scores', 'recommended', 'why', 'graftFromOthers', 'presentAsAlternative', 'questionsForUser'],
}

const ANGLES = [
  {
    key: 'safety-first',
    brief: 'A deterministic pipeline owns everything that touches money and eligibility. The LLM only explains and may flag ambiguity (escalate to human, never approve). Optimise for money safety, auditability and a small, fully-tested core.',
  },
  {
    key: 'judgement-where-it-pays',
    brief: 'Deterministic hard gates first; the LLM adds value only on genuinely soft trade-offs (schedule inconvenience, lost perks vs saving) as a schema-bound advisory signal combined with deterministic confidence. Optimise for recommendation quality on ambiguous cases without letting the model approve anything.',
  },
  {
    key: 'scale-first',
    brief: 'Design for a very large, growing book of bookings: incremental/event-driven reshopping, prioritisation, caching, cost control, observability, shadow mode and gradual autonomy. The prototype is a thin, honest slice of that pipeline.',
  },
]

phase('Propose')
const options = await parallel(
  ANGLES.map((a) => () =>
    agent(
      `Angle: ${a.key}. ${a.brief}\n\nBinding decisions: ${DECISIONS}. Framing (if present): ${FRAMING}. ` +
        `Propose ONE coherent architecture for this angle, separating what the prototype builds ` +
        `now from what the design only describes. Be explicit about every LLM vs deterministic step and why.`,
      { label: `architect:${a.key}`, phase: 'Propose', schema: OPTION_SCHEMA, agentType: 'solution-architect' },
    ),
  ),
)
const proposed = options.filter(Boolean)
if (proposed.length < ANGLES.length) log(`${ANGLES.length - proposed.length} architect(s) returned nothing`)

phase('Judge')
const judgement = await agent(
  `You are the hiring panel for the Rebooking Copilot take-home (brief: docs/ASSIGNMENT.md, rubric at its end). ` +
    `This is the design phase: no code exists to run, so judge the proposals only. ` +
    `Score each option 1-5 on: framing, AI/deterministic boundary, correctness & money safety, scale/cost/observability, ` +
    `pragmatism (a small, honest prototype of the risky core), communication. Recommend one, list ideas worth grafting from the others, ` +
    `which rejected options deserve a "considered alternative" paragraph in DESIGN.md, and the questions the user must answer ` +
    `before committing (options + recommendation) - merge and dedupe the architects' needsDecision items into questionsForUser, ` +
    `and include the agent-shape question (deterministic pipeline + LLM explainer vs LLM orchestrating deterministic tools with the gate in code) ` +
    `unless ${DECISIONS} settles it. Respect ${DECISIONS}.\n\nOptions (JSON):\n${JSON.stringify(proposed, null, 1)}`,
  { label: 'judge', phase: 'Judge', schema: JUDGE_SCHEMA },
)

return { options: proposed, judgement }
