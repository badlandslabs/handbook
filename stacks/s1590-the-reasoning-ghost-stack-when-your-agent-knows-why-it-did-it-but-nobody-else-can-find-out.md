# S-1590 · The Reasoning Ghost Stack — When Your Agent Knows Why It Did It, But Nobody Else Can Find Out

Your agent made a consequential decision: it routed a payment to the wrong account, escalated a support ticket to legal, and declined a loan application — all within policy. When the auditor asks why, you have the tool calls, the final output, and the system prompt. You don't have the reasoning. The agent's chain-of-thought was computed, consumed, and discarded. This is the reasoning ghost: the decision-making process that existed and determined everything, but left no artifact. The Cognitive Audit Trail fixes it by capturing, structuring, and governing reasoning traces as first-class compliance objects.

## Forces

- **LLM inference is stateless and ephemeral.** The internal reasoning that connects input to output — the draft plans, the considered alternatives, the rejected options — is computed and dropped. It never touches disk. You cannot audit what was never recorded.
- **The EU AI Act and ISO 42001 require explainability at the action boundary.** Regulators don't just want the decision; they want the rationale. Post-hoc rationalization by a second model is not the same as the actual reasoning path. It is a reconstruction, and it degrades under pressure.
- **Reasoning traces are large, expensive, and unstructured.** Storing raw CoT tokens multiplies storage and token costs. Reasoning output varies wildly in structure. Without a schema, traces are unreadable by automated policy enforcement.
- **Reasoning capture must not block inference.** Adding synchronous trace processing to the inference path introduces latency and failure modes that compound at scale.

## The move

### 1. Capture at the trace boundary

Store the reasoning output as a structured artifact at each step boundary — not as free text, but as a schema with fixed fields:

```python
@dataclass
class ReasoningTrace:
    step_id: str
    timestamp: datetime
    input_summary: str        # semantic compressed summary
    reasoning_steps: list[str]  # numbered steps
    considered_alternatives: list[str]  # rejected options
    confidence: float        # 0-1 self-reported
    tool_calls_planned: list[str]
    tool_calls_executed: list[str]
    outcome: str             # success / partial / failure
    parent_trace_id: str | None  # for step chains
```

Capture asynchronously via a non-blocking side-channel. Write to an append-only trace store (object storage, write-ahead log, or dedicated audit store). Never block the inference loop.

### 2. Govern at reasoning decision points

Apply policy checks at reasoning boundaries — not just at action boundaries. Three critical gates:

- **Complexity gate**: if reasoning depth exceeds a threshold (N steps, or confidence drops below a floor), route to human review before execution proceeds.
- **Reversal gate**: if the agent's reasoning rejects its own prior step, log the self-correction and check whether the reversal pattern indicates instability.
- **Contradiction gate**: if the reasoning trace conflicts with a prior session's trace on the same entity, surface the conflict before proceeding.

```python
def evaluate_trace(trace: ReasoningTrace, policy: Policy) -> PolicyResult:
    flags = []
    if trace.reasoning_steps.__len__() > policy.max_depth:
        flags.append(PolicyFlag.HIGH_COMPLEXITY)
    if trace.confidence < policy.min_confidence:
        flags.append(PolicyFlag.LOW_CONFIDENCE)
    if trace.outcome == "partial":
        flags.append(PolicyFlag.PARTIAL_SUCCESS)
    return PolicyResult(flags=flags, audit_record=trace.to_audit_entry())
```

### 3. Make traces queryable for post-hoc compliance

Reasoning traces are only useful if you can query them. Index by:

- **Entity** (what the agent was acting on: user_id, account_id, document_id)
- **Temporal window** (reasoning around a specific decision moment)
- **Pattern** (chains of self-corrections, confidence collapses, or repeated tool call attempts)
- **Policy reference** (which governance rule was evaluated at each trace)

This transforms reasoning from ephemeral inference noise into a queryable compliance artifact — the equivalent of a database transaction log for agent decisions.

### 4. Align trace granularity to consequence

Not every step needs full reasoning capture. A tiered approach:

| Tier | When | What's captured |
|------|------|----------------|
| **Full** | Action with downstream consequences | All fields including alternatives |
| **Summary** | Routine tool use | Step summary + outcome |
| **Minimal** | Context-setting steps | Just step_id + parent + outcome |
| **Drop** | Low-stakes token shaping | No trace |

Calibrate tiers by pre-computing consequence likelihood using a lightweight risk classifier on the input. High-risk inputs trigger full capture automatically.

## Receipt

> Verified 2026-07-24 — Architecture validated against: arXiv:2603.16586 (Runtime Governance for AI Agents: Policies on Paths — formalizes execution paths as governance objects); Zylos Research EU AI Act compliance framework (82% of enterprises lack agent audit trails); AgentGuard (arXiv:2509.23864 — dynamic probabilistic assurance via MDP over observed reasoning traces). Pattern confirmed in: Oracle Agent Reasoning (open-source reasoning layer for Ollama models with CoT/ReAct/self-reflection); Galileo AI self-evaluation research (CoT-based hallucination detection and reasoning trace analysis).

## See also

[S-1000](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) · [S-1029](stacks/s1029-the-evaluator-stack-when-your-agent-quality-measurement-is-the-real-failure-mode.md) · [S-1031](stacks/s1031-the-flip-rate-problem-when-your-llm-judge-sometimes-votes-a-and-sometimes-votes-b-on-identical-inputs.md) · [S-1588](stacks/s1588-the-agent-eval-calibration-stack-when-your-test-suite-says-pass-and-your-users-say-fail.md) · [S-1589](stacks/s1589-the-dead-end-recovery-stack-when-your-agent-spirals-into-nothing.md)

## Go deeper

`reasoning-trace` · `cognitive-audit` · `chain-of-thought-capture` · `EU-AI-Act-compliance` · `runtime-governance` · `ISO-42001` · `introspective-reasoning` · `self-reflection` · `reflexion` · `trace-provenance`
