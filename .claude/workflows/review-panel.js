export const meta = {
  name: 'review-panel',
  description: 'Pre-submission review against the brief and rubric; quick = assessor + money-safety, deep = + boundary + fresh-run; serious findings are adversarially verified',
  whenToUse: 'Phase 5, called by /review-submission. Read-only. quick: 2-6 agents; deep: up to 10 agents.',
  phases: [
    { title: 'Review', detail: 'independent reviewers' },
    { title: 'Verify', detail: 'skeptics try to refute serious findings (capped per reviewer)' },
  ],
}

const A = args || {}
const DEPTH = A.depth === 'deep' ? 'deep' : 'quick'
const VERIFY_SEVERITIES = DEPTH === 'deep' ? ['critical', 'high'] : ['critical']
const MAX_VERIFY_PER_REVIEWER = DEPTH === 'deep' ? 3 : 2

const STR = { type: 'string' }
const FINDING = {
  type: 'object',
  properties: {
    id: STR,
    severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
    area: STR,
    file: STR,
    line: { type: 'integer' },
    summary: STR,
    failureScenario: STR,
    suggestedFix: STR,
    effortMinutes: { type: 'number' },
  },
  required: ['id', 'severity', 'area', 'file', 'summary', 'failureScenario', 'suggestedFix', 'effortMinutes'],
}
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: { findings: { type: 'array', items: FINDING }, checked: { type: 'array', items: STR } },
  required: ['findings', 'checked'],
}
const DIM = {
  type: 'object',
  properties: { score: { type: 'integer', minimum: 1, maximum: 5 }, evidence: STR },
  required: ['score', 'evidence'],
}
const ASSESSOR_SCHEMA = {
  type: 'object',
  properties: {
    findings: FINDINGS_SCHEMA.properties.findings,
    checked: FINDINGS_SCHEMA.properties.checked,
    scorecard: {
      type: 'object',
      properties: {
        framing: DIM,
        boundary: DIM,
        moneySafety: DIM,
        scaleCostObs: DIM,
        prototype: DIM,
        communication: DIM,
      },
      required: ['framing', 'boundary', 'moneySafety', 'scaleCostObs', 'prototype', 'communication'],
    },
    briefCompliance: { type: 'array', items: { type: 'object', properties: { item: STR, ok: { type: 'boolean' }, note: STR }, required: ['item', 'ok'] } },
  },
  required: ['findings', 'checked', 'scorecard', 'briefCompliance'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reproduced: { type: 'boolean' }, evidence: STR },
  required: ['refuted', 'reproduced', 'evidence'],
}

const NO_RERUN = DEPTH === 'deep' ? ' A separate fresh-run reviewer executes the README end to end; do not repeat that run.' : ''

const ALL_REVIEWERS = [
  {
    key: 'money',
    depth: 'quick',
    agentType: 'money-safety-reviewer',
    schema: FINDINGS_SCHEMA,
    verify: true,
    prompt: 'Review all money, matching, eligibility, decision, confidence and output-contract code in this repository. Find every way it could produce a wrong REBOOK or a wrong saving. Reproduce in the scratchpad where possible.',
  },
  {
    key: 'assessor',
    depth: 'quick',
    agentType: 'assessor',
    schema: ASSESSOR_SCHEMA,
    verify: false,
    prompt: `Assess the whole submission against docs/ASSIGNMENT.md and its rubric. Rank improvements by score gain relative to effort.${NO_RERUN}`,
  },
  {
    key: 'boundary',
    depth: 'deep',
    agentType: 'llm-boundary-reviewer',
    schema: FINDINGS_SCHEMA,
    verify: true,
    prompt: `Review the AI/deterministic boundary end to end: prompts, schemas, validation, faithfulness, fallback, injection exposure, cost levers, and whether DESIGN.md §3 matches the code. Judge prompt quality as an evaluator would.${NO_RERUN}`,
  },
  {
    key: 'fresh-run',
    depth: 'deep',
    agentType: 'general-purpose',
    schema: FINDINGS_SCHEMA,
    verify: false,
    prompt:
      'Act as an evaluator with a clean machine. Clone the committed state into a temp dir in your scratchpad (git clone <repo> <tmp>); if there are uncommitted changes, ALSO run in the working tree and report the difference. ' +
      'With ANTHROPIC_API_KEY unset and no network assumptions, follow README.md literally: install, test, run. Report every step that fails, is ambiguous, or deviates; whether the README example output matches the real output; and whether fixtures/ and DESIGN.md are present. Do not modify the repository.',
  },
]
const REVIEWERS = ALL_REVIEWERS.filter((r) => DEPTH === 'deep' || r.depth === 'quick')
log(`Depth: ${DEPTH} (${REVIEWERS.map((r) => r.key).join(', ')}); verifying ${VERIFY_SEVERITIES.join('/')} findings, max ${MAX_VERIFY_PER_REVIEWER} per reviewer`)

const reviewed = await pipeline(
  REVIEWERS,
  (r) => agent(r.prompt, { label: `review:${r.key}`, phase: 'Review', schema: r.schema, agentType: r.agentType }),
  async (result, r) => {
    if (!result) return { reviewer: r.key, result: null, confirmed: [], refuted: [], unverified: [] }
    const findings = result.findings || []
    if (!r.verify) return { reviewer: r.key, result, confirmed: findings, refuted: [], unverified: [] }
    const serious = findings.filter((f) => VERIFY_SEVERITIES.includes(f.severity))
    const rest = findings.filter((f) => !VERIFY_SEVERITIES.includes(f.severity))
    const toVerify = serious.slice(0, MAX_VERIFY_PER_REVIEWER)
    const overflow = serious.slice(MAX_VERIFY_PER_REVIEWER)
    if (overflow.length) log(`${r.key}: ${overflow.length} serious finding(s) not verified (cap ${MAX_VERIFY_PER_REVIEWER}) - reported as unverified`)
    const verdicts = await parallel(
      toVerify.map((f) => () =>
        agent(
          `Try to REFUTE this review finding. Read the cited code, then reproduce with a throwaway script or test in your scratchpad (never modify the repo). ` +
            `Set refuted=true if the code does not actually behave this way, a recorded decision in docs/decisions.md explicitly accepts it, or you cannot demonstrate it.\n\nFinding:\n${JSON.stringify(f, null, 1)}`,
          { label: `verify:${r.key}:${f.id}`, phase: 'Verify', schema: VERDICT_SCHEMA, agentType: r.agentType },
        ),
      ),
    )
    const judged = toVerify.map((f, i) => ({ ...f, verdict: verdicts[i] }))
    const failedVerify = judged.filter((f) => !f.verdict)
    if (failedVerify.length) log(`${r.key}: ${failedVerify.length} verifier(s) returned nothing - finding(s) reported as unverified`)
    return {
      reviewer: r.key,
      result,
      confirmed: judged.filter((f) => f.verdict && !f.verdict.refuted),
      refuted: judged.filter((f) => f.verdict && f.verdict.refuted),
      unverified: [...failedVerify, ...overflow, ...rest],
    }
  },
)

const done = reviewed.filter(Boolean)
const assessor = done.find((d) => d.reviewer === 'assessor')
return {
  depth: DEPTH,
  scorecard: assessor && assessor.result ? assessor.result.scorecard : null,
  briefCompliance: assessor && assessor.result ? assessor.result.briefCompliance : null,
  confirmed: done.flatMap((d) => d.confirmed.map((f) => ({ reviewer: d.reviewer, ...f }))),
  refuted: done.flatMap((d) => d.refuted.map((f) => ({ reviewer: d.reviewer, ...f }))),
  unverified: done.flatMap((d) => d.unverified.map((f) => ({ reviewer: d.reviewer, ...f }))),
  checked: Object.fromEntries(done.map((d) => [d.reviewer, d.result ? d.result.checked : []])),
  missingReviewers: REVIEWERS.filter((r) => !done.some((d) => d.reviewer === r.key && d.result)).map((r) => r.key),
}
