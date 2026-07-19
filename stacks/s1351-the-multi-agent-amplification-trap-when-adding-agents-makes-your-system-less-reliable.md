# S-1351 · The Multi-Agent Amplification Trap — When Adding Agents Makes Your System Less Reliable

Adding a second agent to your pipeline feels like adding a safety net. Two agents can catch each other's mistakes. A critic can review the generator. A verifier can check the planner. But the research is now unambiguous: multi-agent pipelines fail in ways single agents don't, and the most dangerous failure mode is invisible. It's not that agents break — it's that they **amplify** each other's errors and build false consensus around wrong answers.

## Forces

- **Errors compound, not cancel.** Unlike in human teams where peer review catches mistakes, agents in a pipeline don't naturally challenge each other. A subtly wrong intermediate output passes through as "ground truth" to every downstream agent.
- **Conformity bias is a first-class failure mode.** When one agent produces a confident output, downstream agents tend to interpret and build on it rather than independently verify it — even when they have the tools to check.
- **Multi-agent feels more reliable than it is.** The visible infrastructure (multiple agents, structured handoffs, task delegation) creates an impression of rigor. The hidden state — context drift, implicit trust in upstream outputs, absence of independent verification — is what actually drives results.
- **Per-agent tests pass while coordination fails.** S-1008 shows single agents match or outperform multi-agent on 64% of benchmarked tasks. The 2% accuracy gain that justifies multi-agent comes with coordination failures that unit tests never catch.

## The move

The failure operates through two distinct mechanisms:

### 1. The Confidence Cascade

An upstream agent makes a confident but wrong assertion. The downstream agent receives this not as "an assertion to evaluate" but as "the established state to build on." The error compounds silently through the chain.

```
Agent-1: "The shipment was delayed to March 15."
Agent-2: [builds on this — schedules follow-up for March 15]
Agent-3: [builds on Agent-2's output — flags March 15 as the critical date]
Agent-4: [builds on Agent-3 — escalates March 15 to stakeholders]
→ The actual delivery date was March 12. No agent independently verified it.
```

Without explicit checkpoints, the pipeline has no mechanism to catch a confident wrong fact.

### 2. The Conformity Spiral

Redis Labs (Apr 2026) identifies this as a distinct failure mode: when one agent makes a confident assertion, other agents tend to **align rather than push back**. The mechanism is the same as in human groups — high confidence signals quality, and LLMs are trained to prefer coherent continuations over contradictory ones. A wrong answer that arrives with confident framing gets reinforced by downstream agents' tendency to produce consistent, aligned outputs.

```
Agent-1: "Based on our data, this is a Category A defect."
Agent-2: "Understood — escalating Category A defect for immediate review."
Agent-3: "Category A confirmed. Assigning P1 priority."
→ No agent questioned whether the original classification was correct.
```

### The Verification Stack

Counter the amplification trap with three layers:

**Layer 1 — Independent verification agents (not downstream consumers).** A verifier agent should check upstream output against source data or ground truth — not receive the output as given and validate its logic. The verifier needs independent access, not inherited context.

```python
# Downstream consumer (broken — receives pre-processed context)
downstream_agent = Agent(
    role="Reviewer",
    prompt="Based on the analyzer's findings: {analyzer_output}"
)

# Independent verifier (correct — accesses source directly)
verifier_agent = Agent(
    role="Audit",
    prompt="Query the source data directly. Does this match: {analyzer_output}?"
)
```

**Layer 2 — Dissent-preserving handoff schema.** Every handoff message should include an explicit confidence field and a "verified_by" field. If downstream disagrees, it should surface the disagreement, not resolve it silently toward the upstream answer.

```json
{
  "handoff": {
    "from": "agent-classifier",
    "to": "agent-reviewer",
    "claim": "This is a Category A defect",
    "confidence": "high",
    "verified_by": null,
    "dissent_channel": "escalate_if_confidence_low"
  }
}
```

**Layer 3 — Parallel path with cross-check.** Run critical decisions through two independent paths and compare outputs. Divergence is a signal, not noise — surface it for human review before the pipeline continues.

```python
async def parallel_path_check(task: str, path_a: Agent, path_b: Agent) -> str:
    result_a, result_b = await asyncio.gather(
        path_a.execute(task),
        path_b.execute(task)
    )
    if result_a.claim != result_b.claim:
        # Surface divergence — don't default to either
        return f"DIVERGENCE: A={result_a.claim} vs B={result_b.claim}"
    return result_a.claim
```

### Coordination Testing

QASkills (Jun 2026) establishes the key test shapes for multi-agent coordination:

| Test Shape | What It Catches |
|---|---|
| Handoff schema validation | Missing idempotency keys, untyped payloads |
| Dead-letter path | Dropped handoffs, retry collisions |
| Cross-validation round-trip | Conformity bias, silent error propagation |
| Partial failure injection | Cascade behavior when one agent fails mid-pipeline |

## Receipt

> Verified 2026-07-19 — Redis Labs multi-agent failure analysis (2026-04-22); QASkills multi-agent testing guide (2026-06-15); iSimplifyMe agent handoff patterns research. Pattern confirmed in: single-agent setups outperform multi-agent on 64% of tasks (Princeton NLP); coordination overhead outweighs parallelization benefit on sequential reasoning. Conformity bias mechanism documented by Redis Labs — agents tend to align with confident upstream assertions rather than verify independently.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement at handoff boundaries
- [S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — when multi-agent is the wrong choice
- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — recovery design for agentic failures
