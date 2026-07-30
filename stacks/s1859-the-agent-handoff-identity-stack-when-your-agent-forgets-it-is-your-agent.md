# S-1859 · The Agent Handoff Identity Stack — When Your Agent Forgets It Is Your Agent

When you hand off a task from one agent to another and the receiving agent loses the strategic context, goal framing, and working decisions of its predecessor — producing technically correct output that solves the wrong problem, in the wrong style, for the wrong user.

## Forces

- **Handoffs are lossy compression, and no one budgeted for the loss.** A handoff passes a task description forward. Everything the sending agent inferred, decided, disambiguated, and prioritized during its work either makes it into the prompt string or it doesn't. There is no automatic preservation.
- **Each agent starts with a fresh context window.** Multi-agent systems fail not because individual agents are bad, but because the seams between them are lossy. Corbits documents this as "the leading cause of production failures in agentic workflows": each agent produces reasonable output in isolation; together, the thread gets lost at the handoff.
- **Naive fixes make it worse.** Passing everything forward — full conversation history, all intermediate outputs, all reasoning — re-sends growing context at every step, so token cost climbs with roughly the square of chain length (the coordination tax). The fix is not more text; it is a smarter contract.
- **Multi-agent systems fail 41–86.7% of the time in studied environments** (MAST benchmark, Cemri et al., NeurIPS 2025). Handoff failure is a primary driver of this rate.

## The move

**Design handoff contracts as structured state transfer, not free-text messaging.**

### 1. Choose the handoff strategy by consequence, not preference

Three strategies exist. Match them to risk:

- **Full conversation history** — every turn preserved. Highest fidelity, highest token cost. Use when the downstream agent must replicate the sender's reasoning exactly (auditing, legal review).
- **Compressed summary** — LLM-generated synopsis of key decisions, constraints, and state. Anthropic's Research Agent uses this. Token-efficient; fidelity depends on summarization quality. Use for routine handoffs where reconstruction cost is acceptable.
- **Structured state transfer** — typed schema: `{goal, current_state, constraints, decisions_made, pending_questions, style_requirements}`. Most robust against drift. Use for handoffs where the downstream agent must preserve identity, not just receive a task.

### 2. Pass epistemic tier in the handoff, not just the task

At minimum, include three tiers in every handoff message:

1. **Verified facts** — authoritative data retrieved with citation (pass without flag)
2. **Working inferences** — the sending agent's reasoned conclusions (flag explicitly as `confidence: inferred`)
3. **Pending questions** — unresolved gaps the sender did not have time to answer (flag as `needs_resolution`)

### 3. Make a bad handoff fail loudly, not quietly

Passing state through free-text messages is the most expensive default in multi-agent design. Implement handoff validation:

- **Schema enforcement** — handoff messages must conform to a typed contract; reject untyped payloads
- **Replay integrity check** — after handoff, the receiving agent summarizes back what it understood; compare against the sender's intent
- **Trace stitching** — connect every handoff in a single observability span (as emphasized by Atlan's debugging framework: "debugging N agents without a stitched trace means debugging blind")

### 4. Name the receiving agent's role explicitly in the handoff

Free-text task descriptions invite the receiving agent to re-interpret scope. Instead:

```
AGENT ROLE: billing_specialist
TASK: resolve_invoice_dispute(invoice_id=INV-4421)
PRESERVED CONTEXT:
  - Customer tier: enterprise (not standard)
  - Previous dispute outcome: partial credit issued 2025-03
  - Escalation flag: TRUE (customer threatened chargeback)
  - Style requirement: formal, include statute citations
PENDING: confirm whether partial credit from prior dispute covers the contested line item
```

## Evidence

- **Research paper:** MAST benchmark (Multi-Agent Systems Testing) found multi-agent systems fail 41–86.7% of the time, with handoff-related failures as a primary driver — [Cemri et al., NeurIPS 2025](https://atlan.com/know/ai-agent/debugging-multi-agent-systems)
- **Engineering blog:** Corbits documented that "each agent in isolation produced reasonable output, but together the thread got lost" as the core failure mode, calling context loss "the leading cause of production failures in agentic workflows" — [Context Loss in Multi-Agent Systems, corbits.dev, 2026-05](https://www.corbits.dev/blog/context-loss-in-multi-agent-systems)
- **Framework docs:** Anthropic's Research Agent uses compressed summaries for inter-agent handoffs to balance fidelity against token cost; the full history pattern is used in audit-sensitive applications requiring complete reasoning trails — [Anthropic Claude Blog: Multi-Agent Coordination Patterns, 2026-04](https://claude.com/blog/multi-agent-coordination-patterns)
- **Observability research:** Atlan's multi-agent debugging framework recommends a single stitched trace across all agents as the first debugging step — [Multi-Agent Debugging: 7 Failure Modes, Atlan, 2026-07](https://atlan.com/know/ai-agent/debugging-multi-agent-systems)
- **Enterprise blog:** The coordination tax of naive full-history passing grows O(n²) with chain length, making structured state transfer the only viable approach at scale — [Blck Alpaca: Agent Handoff Strategies, 2026-06](https://blckalpaca.at/en/knowledge-base/ai-agents/multi-agent-systems-fundamentals/agent-handoff-strategien)

## Gotchas

- **Passing everything breaks at scale.** Full history works for 2-agent chains. By agent 5 with 50 turns each, you have consumed most of the context window on history. Structured state is not a performance optimization — it is a correctness requirement for chains beyond depth 3.
- **Summarization introduces subtle distortion.** The LLM summarizing the handoff may drop exactly the detail the receiving agent needs. Treat summary fidelity as a failure mode to test, not a solved problem.
- **Handoff contracts drift from reality.** When the schema is designed upfront, it captures the state you thought mattered. As the system evolves, the schema may no longer reflect what agents actually need to pass. Treat handoff contracts as versioned interfaces, not static schemas.
- **Observability without trace stitching is useless.** Per-agent logs are necessary but insufficient. Without a unified trace linking each handoff to its successor, you cannot determine whether a failure originated in the sender, the handoff, or the receiver.
