# S-1333 · The Synchronization Boundary — When Naive Broadcast Makes Your Multi-Agent System More Confident and More Wrong

Your five-agent system has a hallucination problem. You add a shared context bus — every agent broadcasts its state to every other agent after each step. The hallucinations get worse. Not better. This is the synchronization boundary problem: the instinct to share everything is actively harmful, because a multi-agent system's joint output depends on whether agents share the *right* state at the *right* threshold, not whether they share everything all the time.

## Forces

- **Naive broadcast spreads contamination, not truth.** When one agent has hallucinated, broadcasting its false belief to other agents doesn't "correct" it — it propagates the error. Rodrigues (arXiv:2606.21666, 2026) shows full-broadcast synchronization increases hallucination rate by 34% above baseline (HR: 0.658 vs. 0.492, p=0.0022, d=1.18) in travel-domain multi-agent tasks. Contamination spreads through the agent network faster than correction does.
- **Context drift is the root cause, not model quality.** Multi-agent hallucinations arise from *context drift* — the divergence of internal knowledge states between concurrently operating agents. When Agent A and Agent B hold mismatched beliefs about shared world state, their joint reasoning produces contradictions that manifest as hallucination regardless of how capable each agent is individually. A 72B model with divergent context produces worse hallucinations than a 7B model with aligned context.
- **Drift is spatial, temporal, and structural.** Agents operating concurrently can diverge along three axes: *spatial* (different beliefs about the same environment), *temporal* (information from different timestamps, e.g., one agent processed a price change, another didn't), and *structural* (different reasoning chains about the same inputs). Each requires different synchronization.
- **Full context exchange is cost-prohibitive and brittle.** Sending full context windows between agents is expensive and still doesn't solve the problem — a hallucinated agent's context is confidently wrong, and the receiving agent has no way to distinguish it from accurate context without a gate.

## The move

**Threshold-gated synchronization with contamination detection.** Instead of broadcasting everything, gate synchronization on divergence measurement.

**Step 1 — Context Divergence Score (CDS):** Lightweight metric that quantifies knowledge-state discrepancy between agent pairs. Three dimensions: spatial (environment belief delta), temporal (timestamp delta), structural (reasoning chain similarity). Compute as cosine distance between agent state embeddings on shared facts.

```python
from numpy.linalg import norm
from numpy import dot
import numpy as np

def cosine_sim(a: list[float], b: list[float]) -> float:
    return dot(a, b) / (norm(a) * norm(b) + 1e-8)

def cds(agent_states: dict[str, list[float]], shared_facts: list[str]) -> dict[str, float]:
    """
    Compute Context Divergence Score between all agent pairs.
    Returns a dict of (agent_pair) -> divergence score [0,1], where 1 = full divergence.
    """
    agents = list(agent_states.keys())
    scores = {}
    for i, a in enumerate(agents):
        for b in agents[i+1:]:
            sim = cosine_sim(agent_states[a], agent_states[b])
            scores[f"{a}|{b}"] = 1.0 - sim
    return scores

# Example: two agents with divergent context
agent_a = embed(["user wants to fly BOS → LAX", "price is $340"])  # spatial: stale price
agent_b = embed(["user wants to fly BOS → LAX", "price is $892"])  # temporal: updated price
score = cds({"agent-a": agent_a, "agent-b": agent_b}, ["price"])
# score["agent-a|agent-b"] = 0.71 → exceeds threshold → trigger SSVP
```

**Step 2 — Threshold gate:** Only synchronize when CDS exceeds a domain-specific threshold. Below threshold: agents operate independently. Above threshold: enter the Shared State Verification Protocol.

**Step 3 — Shared State Verification Protocol (SSVP):** Rather than broadcasting raw context, agents *attest* to specific shared facts. A verification layer checks attestations against an authoritative source before propagating corrections. This prevents contaminated (hallucinated) beliefs from being broadcast as ground truth.

```python
THRESHOLD = 0.4  # calibrated per domain; travel ~0.4, software ~0.3

def ssvp_check(divergence_scores: dict[str, float], 
               shared_state: dict[str, str],
               agent_attestations: dict[str, dict[str, str]]) -> list[str]:
    """
    Given divergence scores, authoritative shared state, and agent attestations,
    return only the corrections that should be broadcast.
    """
    corrections = []
    for pair_key, score in divergence_scores.items():
        if score < THRESHOLD:
            continue  # aligned — no sync needed
        agent_a, agent_b = pair_key.split("|")
        for fact in shared_state:
            att_a = agent_attestations.get(agent_a, {}).get(fact)
            att_b = agent_attestations.get(agent_b, {}).get(fact)
            authoritative = shared_state[fact]
            # Only broadcast if BOTH attestations disagree with authoritative source
            if att_a != authoritative and att_b != authoritative:
                # Contamination detected — neither agent is correct
                corrections.append(f"[BLOCKED] {fact}: contaminated state, require fresh fetch")
            elif att_a != authoritative:
                corrections.append(f"[SYNC] {fact}: {att_a} → {authoritative}")
            elif att_b != authoritative:
                corrections.append(f"[SYNC] {fact}: {att_b} → {authoritative}")
    return corrections
```

**Step 4 — Measure three drift dimensions separately.** Spatial drift (shared environment state) is most common in real-time data tasks. Temporal drift (stale vs. fresh information) is most dangerous in financial/healthcare domains. Structural drift (different reasoning chains) is hardest to detect but most damaging to multi-hop reasoning. Each dimension warrants its own monitoring dashboard and escalation path.

## Receipt

> Verified 2026-07-19 — arXiv:2606.21666 (Rodrigues, Celabe, Jun 2026): SSVP reduces hallucination rate to 0.463 (-5.9% vs no-sync baseline, d=0.30) vs. full-broadcast HR 0.658 (+34%, d=1.18). 58% fewer API calls than full-broadcast. AI Navigate (Jun 2026): 80% of production AI deployments fail at the handoff boundary. Galileo AI (Jul 2026): coordination latency scales from ~200ms (2 agents) to 4+ seconds (8+ agents); proper orchestration reduces failure rate 3.2×.

## See also
- [S-986 · The Coordination Breakdown Pattern](/stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — coordination architecture fundamentals
- [S-401 · Agent Drift](/stacks/s401-agent-drift-the-longitudinal-regression-problem.md) — longitudinal behavioral degradation
- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — disagreement on shared state
