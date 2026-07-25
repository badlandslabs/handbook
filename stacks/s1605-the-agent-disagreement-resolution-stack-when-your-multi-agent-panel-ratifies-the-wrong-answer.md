# S-1605 · The Agent Disagreement Resolution Stack — When Your Multi-Agent Panel Ratifies the Wrong Answer

Multi-agent systems are sold on a promise: parallel specialized agents produce better answers than any single agent. The promise assumes that disagreement is handled. Most teams discover in production that it isn't — their panel of supposedly independent agents converges on the wrong answer with high, false confidence.

## Forces

- **Naive voting amplifies shared blind spots.** When all agents run the same base model, they fail on the same inputs the same way. Majority vote doesn't correct this — it confirms the shared error.
- **Context visibility destroys independence.** The moment one agent's answer appears in the shared context, other agents tilt toward it. LLMs exhibit conformity/sycophancy that looks like reasoning but isn't.
- **Disagreement is information, not noise.** A disagreement between a finance agent and a legal agent on a contract recommendation is the system surfacing genuine uncertainty. The resolution mechanism must preserve that signal.
- **Not all disagreements are the same kind.** Resolving a factual dispute between two retrieval agents requires different machinery than resolving a planning conflict between two specialized workers.
- **Resolution has a cost.** Every debate round, every arbitration call, every escalation burns latency and tokens. The stack must know when to invest in resolution versus when to accept the cost of being wrong.

## The move

### Classify the disagreement type first

The resolution strategy depends entirely on the disagreement taxonomy:

| Type | Example | Resolution approach |
|------|---------|---------------------|
| **Factual** | Two agents cite different sources for the same claim | Retrieval oracle, provenance trace, ground-truth lookup |
| **Reasoning** | Same facts, different conclusions | Debate with explicit justification, LLM-as-judge on reasoning chains |
| **Planning** | Different task decomposition strategies | Hierarchical arbitration, human escalation threshold |
| **Confidence** | Agents report different confidence levels for same output | Calibration-weighted voting, confidence-gated escalation |
| **Constraint** | One agent's output violates another's hard constraint | Constraint precedence matrix, precedence-gated handoff |

### The five-layer resolution stack

**Layer 1 — Disagreement Detection**

Before resolution, you need a detector. Not all disagreements are explicit — some agents silently override or defer. Monitor for:
- Convergent output drift (agents producing near-identical text within N turns)
- Confidence collapse (panel confidence exceeds any individual agent's confidence)
- Handoff modification rate (how often receiving agents alter sender output)

**Layer 2 — Independence Preservation**

The cheapest disagreement is one that doesn't happen. Structure agent interactions to preserve independence:
- **Sealed responses**: agents produce answers before seeing peers' outputs
- **Structural diversity**: run disagreement-prone agents on different base models or temperature settings
- **Retriever isolation**: each specialist agent queries its own retrieval layer, not a shared one

```python
class DisagreementAwarePanel:
    def __init__(self, agents, resolution_strategy="debate"):
        self.agents = agents
        self.resolution_strategy = resolution_strategy

    def run_sealed(self, task):
        # Phase 1: collect independently, before any context sharing
        raw_outputs = {}
        for agent in self.agents:
            agent.reset_context()
            raw_outputs[agent.id] = agent.run(task)

        # Detect disagreement before sharing
        disagreement = self._compute_disagreement(raw_outputs)
        if disagreement < self.threshold:
            return self._merge(raw_outputs)

        # Phase 2: resolution (only if needed)
        if self.resolution_strategy == "debate":
            return self._debate_resolve(raw_outputs)
        elif self.resolution_strategy == "arbitration":
            return self._arbitrate(raw_outputs)
        elif self.resolution_strategy == "escalate":
            return self._escalate(raw_outputs, task)

    def _compute_disagreement(self, outputs):
        # N-gram overlap, semantic embedding distance, or LLM-judged divergence
        pass
```

**Layer 3 — Structured Debate**

When disagreement is detected and agents must interact:
- Each agent defends its position with explicit justification (not just output)
- Responses are shown to all agents simultaneously (no sequential reveal)
- Round limit prevents infinite debate (3 rounds is typical)

Key constraint: the debate judge must not be one of the debating agents. Use a separate evaluator or ground-truth oracle.

**Layer 4 — Arbitration**

For high-stakes or unresolved disagreements, escalate to arbitration:
- **Model-based**: A more capable model reviews the reasoning chains, not the outputs
- **Human-based**: For decisions above a cost/confidence threshold, flag for human review
- **Rule-based**: For constraint violations, apply a precedence matrix (hard constraints override soft, policy overrides intent)

**Layer 5 — Confidence-Weighted Execution**

After resolution, attach a confidence score to the final output:
- Record which agents dissented and why
- Include the resolution rationale in the output metadata
- Set a monitoring window: if the executed plan fails within N steps, reopen the disagreement

### The precedence matrix for constraint conflicts

When agents disagree because their constraints conflict (e.g., legal agent says "cannot disclose" and business agent says "must disclose"), use an explicit precedence hierarchy:

```
policy constraint > regulatory constraint > safety constraint
> user intent constraint > optimization objective
```

This makes the conflict deterministic rather than negotiated.

## Receipt

> Verified 2026-07-24 — Structured around patterns from Tian Pan's taxonomy (April 2026) on multi-agent disagreement types, CallSphere's three-pattern comparison (Voting/Debate/Jury), and RunGuard's fault-tolerance stacking approach. Pattern connects to S-29 (False Consensus), S-1052 (Cascade Stack — atomic falsehood propagation), S-1132 (Intent Divergence), and S-299 (Multi-Agent Coordination). The code example is a structural sketch; no live execution performed. Receipt pending — code pattern untested.

## See also

- [S-29 · False Consensus](s29-false-consensus.md) — the dark twin: voting helps only when votes are independent
- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-multi-agent-atomic-falsehood-propagation.md) — how falsehood propagates through a multi-agent system
- [S-1132 · The Semantic Intent Divergence Stack](s1132-the-semantic-intent-divergence-stack-when-agents-succeed-locally-but-fail-globally.md) — the 79% failure rate in multi-agent specification
- [S-299 · Multi-Agent Coordination: Four Patterns That Actually Ship](s299-multi-agent-coordination-four-patterns-that-actually-ship.md) — coordination topology patterns
