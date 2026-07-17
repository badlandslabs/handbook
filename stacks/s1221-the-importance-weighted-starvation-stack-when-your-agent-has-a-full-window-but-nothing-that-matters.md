# S-1221 · The Importance-Weighted Starvation Stack — When Your Agent Has a Full Window But Nothing That Matters

Your agent's context window is 60% full. The dashboard shows healthy token counts. Your agent just approved a loan that violates your stated policy. The policy document was in context at step 1. By step 37, it had been displaced by tool call histories and intermediate reasoning. The model was never told to deprioritize it — it simply lost the competition for limited attention. This isn't a context overflow. It's **importance-weighted starvation**: the agent's most critical information gets crowded out by accumulated noise, silently and without error.

## Forces

- **Context eviction is recency-biased, not importance-biased.** Every memory management strategy in production — LRU, summary compression, window truncation — optimizes for recency. The last thing you said gets priority. A policy constraint from step 1 has no advantage over a tool response from step 35. They compete on the same recency axis.
- **The failure is semantic, not quantitative.** A 70% full context window looks healthy. A token count under the limit passes every preflight check. But if the 30% that remains contains no usable policy guidance, the agent is effectively operating blindfolded. No monitor fires.
- **Testing masks this.** Demo and staging environments use short runs with small context. The policy constraint is always present because context is always fresh. Production traffic runs longer sessions — the class of failures only manifests in long-horizon, high-traffic conditions.
- **The model's behavior is a function of its input, not just its output.** Stanford HAI AI Index 2026 documents that LLMs weight recency heavily in attention. Content visible in the most recent tokens disproportionately influences behavior. A buried constraint is not just harder to see — it is structurally disadvantaged.

## The move

Treat context management as a **semantic priority problem**, not a storage problem. Assign importance scores to each context element at insertion time. Enforce importance-tier eviction and track constraint coverage as a first-class metric.

### 1. Annotate importance at insertion

```python
from dataclasses import dataclass
from enum import IntEnum

class Importance(IntEnum):
    CRITICAL   = 3  # policy hard constraints, security rules, safety gates
    HIGH       = 2  # user intent, task scope, key retrieved facts
    MEDIUM     = 1  # intermediate reasoning, tool call history
    LOW        = 0  # verbose tool responses, stale observations

@dataclass
class ContextElement:
    content: str
    importance: Importance
    type: str           # "system_constraint", "user_intent", "tool_result", ...
    provenance: str     # "step-3", "retrieval-0", "system_prompt"
    tokens_estimate: int
```

### 2. Reserve guaranteed slots for CRITICAL content

Never evict CRITICAL importance elements regardless of recency or token count.

```python
RESERVED_SLOTS = {
    Importance.CRITICAL: float("inf"),  # never evict
    Importance.HIGH:     0.20,           # max 20% of context budget
    Importance.MEDIUM:    0.35,
    Importance.LOW:      0.30,
}

def budget_enforce(elements: list[ContextElement], max_tokens: int) -> list[ContextElement]:
    """Importance-weighted eviction: reserve CRITICAL, then distribute remainder."""
    reserved = [e for e in elements if e.importance == Importance.CRITICAL]
    reserved_tokens = sum(e.tokens_estimate for e in reserved)
    remaining = max_tokens - reserved_tokens

    selected = reserved[:]
    for tier in [Importance.HIGH, Importance.MEDIUM, Importance.LOW]:
        tier_elements = [e for e in elements if e.importance == tier
                          and e not in selected]
        tier_budget = int(remaining * RESERVED_SLOTS[tier])
        tier_elements.sort(key=lambda e: e.tokens_estimate)  # prefer compact
        for e in tier_elements:
            if tier_budget >= e.tokens_estimate:
                selected.append(e)
                tier_budget -= e.tokens_estimate
    return selected
```

### 3. Track constraint coverage as a live metric

```python
def constraint_coverage(elements: list[ContextElement], constraints: list[str]) -> float:
    """
    What fraction of hard constraints are currently present in context?
    Track this as a first-class metric alongside token count.
    """
    context_text = " ".join(e.content for e in elements)
    present = sum(1 for c in constraints if c.lower() in context_text.lower())
    return present / len(constraints) if constraints else 1.0

# Alert if coverage drops below threshold
if constraint_coverage(context_elements, policy_constraints) < 0.85:
    logger.warning("Policy constraint coverage below 85% — agent may be operating blind")
    # Trigger: re-inject constraints, summarize noisy elements, or escalate to human review
```

### 4. Re-inject CRITICAL content on coverage drop

```python
def re_inject_constraints(agent_state: dict, constraints: list[str]) -> dict:
    """Reinstate hard constraints when coverage falls below threshold."""
    current_elements = agent_state["context_elements"]
    coverage = constraint_coverage(current_elements, constraints)
    if coverage >= 0.85:
        return agent_state

    # Prepend a compact reminder of all active constraints
    constraint_reminder = "\n".join(f"- {c}" for c in constraints)
    reminder_element = ContextElement(
        content=f"[CONSTRAINT REMINDER — policy limits active]:\n{constraint_reminder}",
        importance=Importance.CRITICAL,
        type="system_constraint",
        provenance="coverage_guard",
        tokens_estimate=len(constraint_reminder.split()) * 1.3,
    )
    agent_state["context_elements"].insert(0, reminder_element)
    agent_state["context_elements"] = budget_enforce(
        agent_state["context_elements"], agent_state["max_tokens"]
    )
    return agent_state
```

## Receipt

> Verified 2026-07-16 — Meritshot blog (Feb 2026) documents a fintech loan-underwriting agent that "starts approving loans that violate the policy document fed in at the start of the session" around task 37 in long runs. The article attributes this to context filling with prior case history, displacing the policy document. AgentMarketCap (April 2026) notes that "the agent's effective context window is always full of the wrong things" — semantic importance triage is identified as the open challenge. Zylos Research (April 2026) on context engineering: "the size of your context window is almost irrelevant. What matters is what you put in it." No existing entry covers importance-weighted eviction or constraint coverage as a monitoring dimension. S-1063 (context lifecycle) covers curation; S-176 (context section budget enforcer) covers token-level per-section limits; neither addresses semantic importance or CRITICAL-slot reservation.

## See also

- [S-1063 · The Context Lifecycle Stack](s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-knows-less.md) — context lifecycle curation (this entry's complement)
- [S-1197 · The Schema-Pass, Semantic-Fail Stack](s1197-the-schema-pass-semantic-fail-stack-when-your-agent-returns-valid-json-with-the-wrong-answer.md) — valid output, wrong behavior
- [S-1066 · The Invisible Failure Stack](s1066-the-invisible-failure-stack-when-your-agent-succeeds-and-burns-47k-instead.md) — silent failure modes that dashboards miss
- [S-1119 · The Safe Loop Stack](s1119-the-safe-loop-stack-when-your-agent-cant-tell-it-is-lost.md) — agent self-awareness for loop conditions
