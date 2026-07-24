# S-1567 · The Typed Handoff Protocol Stack — When Your Multi-Agent System Succeeds at Every Step and Fails at Every Handoff

Your triage agent classifies the ticket perfectly. Your research agent finds everything relevant. Your writer agent produces excellent prose. But the final artifact is wrong — the writer fabricated a finding the researcher never produced. Every individual agent worked. The system failed at the seams. This is not a model problem. It is a handoff problem.

## Forces

- **Each agent operates in an isolated context.** The research agent's findings live in its context window. The writer agent's context window is empty at handoff — it receives a message, not the reasoning that produced it. Information loss is structural, not accidental.
- **Untyped handoffs are the #1 killer of multi-agent projects.** MAST (Multi-Agent System Failure Taxonomy, arxiv:2503.13657) analyzed 1,600+ production traces and identified inter-agent misalignment as one of three primary failure categories. A SyncSoft AI survey found multi-agent systems use 15× more tokens than single-agent equivalents — most of that overhead is redundant work from agents re-deriving what prior agents already knew but couldn't communicate.
- **Too little context and the next agent makes wrong assumptions. Too much context and it is buried in noise.** The handoff must be precise: structured enough to be verifiable, rich enough to be actionable.
- **Handoff failures are invisible until the final output is wrong.** There is no error message. There is no crash. The artifact looks plausible. The failure surfaces in production as a confident wrong answer.

## The move

### 1. Define the handoff contract as a typed schema

The upstream agent must produce a structured output that matches a schema the downstream agent expects. Not free text. Not a summary. A typed artifact.

```typescript
// Define once. Enforce everywhere.
const handoffSchema = z.object({
  findings: z.array(z.object({
    claim: z.string(),        // The actual finding
    evidence: z.string(),     // Citation or source
    confidence: z.number(),   // 0-1, required — no silent uncertainty
    status: z.enum(['confirmed', 'contradicted', 'uncertain']),
    downstreamAssumptions: z.array(z.string())  // Explicit assumptions for next agent
  })),
  scopeBoundary: z.object({
    whatWasSearched: z.array(z.string()),
    whatWasExcluded: z.array(z.string()),
    whyExcluded: z.record(z.string())  // reason per exclusion
  }),
  handoffNote: z.object({
    primaryInsight: z.string(),   // One sentence the next agent MUST know
    risksToWatch: z.array(z.string())  // Known failure modes in this context
  })
});
```

### 2. The upstream agent must fill the schema — not just summarize

The common mistake: the research agent writes a paragraph summary and the writer agent interprets it. The fix: force every agent to fill every field of the schema. Confidence scores and downstream assumptions are non-negotiable — they make implicit reasoning explicit.

### 3. The downstream agent must acknowledge the handoff

A handoff is not complete until the receiver confirms receipt and validates the schema. If the writer agent receives a malformed handoff, it must request re-delivery — not attempt to fill gaps with inference.

```typescript
async function handoff(fromAgent: Agent, toAgent: Agent, payload: unknown) {
  const validated = handoffSchema.parse(payload);  // Fail fast on schema mismatch
  const ack = await toAgent.receive({ type: 'handoff', payload: validated });
  if (ack.status === 'rejected') {
    // Re-request with specific gaps identified
    return await toAgent.receive({ type: 'handoff-retry', gaps: ack.gaps, prior: payload });
  }
  return ack;
}
```

### 4. Annotate the handoff with scope boundaries

The most valuable field most teams skip: `scopeBoundary`. The upstream agent must state what it did NOT cover and why. This prevents the downstream agent from assuming the absence of information means the absence of a finding.

### 5. Chain handoffs use a handoff log, not a single message

For multi-stage pipelines (triage → research → draft → review), maintain a shared handoff log file. Each agent appends its output plus metadata. The log is the audit trail. When review finds an error, the log traces it to the exact stage:

```
[handoff: triage → research]
  classification: bug-report
  priority: P1
  customer_tier: enterprise
  downstreamAssumptions: ["reproduction steps are accurate", "version is current"]

[handoff: research → draft]
  findings: [3 confirmed, 1 uncertain]
  scopeBoundary: { excluded: ["historical billing data"], why: "out of SLA scope" }
  primaryInsight: "Root cause is rate limiter, not database"

[handoff: draft → review]
  wordCount: 847
  sections: ["summary", "reproduction", "root-cause", "resolution"]
  reviewRequest: "Verify root-cause claim matches research findings"
```

### 6. Version the handoff schema itself

As your multi-agent system evolves, the handoff contract evolves. The schema should be versioned. An agent receiving a v1 handoff in a v2 system knows to request a translation layer.

### 7. Test handoffs in isolation

Unit test each handoff transformation: given a valid upstream output, does the downstream agent produce the expected downstream output? This catches schema drift before it reaches production traces.

## Receipt

> Verified 2026-07-24 — Researched against: agentpatterns.ai (2026-06-13), agentmemo.ai blog, arxiv:2503.13657 (MAST taxonomy, 1,600+ production traces), SyncSoft AI handoff failure data (15× token overhead), Anthropic multi-agent research system (file-based handoffs), Microsoft Semantic Kernel Handoff Agent Orchestration, SyncSoft AI 7-fix handoff blueprint (2026). Pattern confirmed across all primary sources. Deduplication: S-1013 (multi-agent boundary) covers untyped handoffs as a failure category; this covers the prescriptive stack for typed handoff protocol implementation. S-2030 (graph engineering) covers programmable topology; this covers the specific data contract layer within that topology.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — the untyped handoff failure that motivates this pattern
- [S-1472 · The Compounding Reliability Stack](s1472-the-compounding-reliability-stack-when-your-95-percent-accurate-agent-completes-36-percent-of-its-workflows.md) — Lusser's Law applies at handoff boundaries: a 95%-accurate agent in a 3-step pipeline completes ~86% of tasks correctly, and handoff failures compound that gap
- [S-1566 · The Continuous Evaluation Pipeline Stack](s1566-the-continuous-evaluation-pipeline-stack-when-your-agent-isnt-as-good-as-it-was-last-tuesday.md) — trace production failures back to specific handoff points with the eval pipeline
