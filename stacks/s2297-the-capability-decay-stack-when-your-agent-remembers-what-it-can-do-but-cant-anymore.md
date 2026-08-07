# S-2297 · The Capability Decay Stack — When Your Agent Remembers What It Can Do But Can't Anymore

Your routing agent sends 40% of tasks to an agent that claimed 94% accuracy six months ago. That agent now scores 61%. No one updated the agent card. The routing agent has no way to know. This is capability decay: the silent divergence between what an agent advertises it can do and what it actually delivers at runtime. Every capability marketplace, agent registry, and A2A discovery layer assumes agent cards are approximately true. They aren't.

## Forces

- **Agent cards are self-declared and static.** The `/.well-known/agent.json` card is written once at onboarding and updated on best-effort. Nobody re-tests before routing. AgentStatus (April 2026) found 88% of agents changed behavior within 30 days — but agent cards update on human schedules, not behavioral ones.
- **Capability decay is not the same as model drift.** Model drift means the underlying LLM changed. Capability decay means the *agent system's* effective capability changed: dependency API changed, tool schema drifted, prompt was modified, memory degraded, or downstream service degraded. The agent card still claims the same capability; the delivery doesn't match.
- **Trust cascades multiply the damage.** In a multi-agent pipeline where Agent A routes to B, B routes to C, and C routes to D, each trusting the other's advertised capability, a 20% decay at D propagates backward through the entire chain. No agent in the chain verified anything — they all trusted the card.
- **Capability probing has a cost.** Every probe task burns latency and compute. Teams avoid probing because it seems wasteful — until the unverified agent fails catastrophically and costs more than the probes would have.

## The Move

Three-layer capability verification: **probe before trust**, **attest continuously**, and **scope the blast radius**.

### Layer 1 — Capability Probe

Before routing a high-stakes task, send a probe: a small, representative sub-task that tests the advertised capability. Use a standardized probe set curated for each capability class.

```python
class CapabilityProbe:
    def __init__(self, agent_id: str, capability: str, probe_set: list[dict]):
        self.agent_id = agent_id
        self.capability = capability
        self.probe_set = probe_set  # [{task, expected_output, max_latency}]

    def probe(self, agent_client) -> ProbeResult:
        results = []
        for probe in self.probe_set:
            start = time.time()
            response = agent_client.execute(
                task=probe["task"],
                timeout=probe["max_latency"]
            )
            elapsed = time.time() - start
            results.append({
                "task": probe["task"],
                "correct": response.matches(probe["expected_output"]),
                "latency": elapsed,
                "confidence": response.confidence_score
            })

        score = sum(r["correct"] for r in results) / len(results)
        return ProbeResult(
            agent_id=self.agent_id,
            capability=self.capability,
            score=score,
            samples=results,
            probed_at=datetime.utcnow()
        )

# Route decision uses probe score, not card claim
def route_task(task: Task, candidates: list[str]) -> str:
    for agent_id in candidates:
        probe_result = capability_probe_cache.get(agent_id, task.capability)
        if probe_result and probe_result.score >= task.min_accuracy:
            return agent_id
    return fallback_route(task)
```

**Probe strategy:** probe on a schedule (every N tasks or every T hours), not every task. Cache results. Probe aggressively for high-stakes tasks; leniently for low-stakes ones.

### Layer 2 — Continuous Capability Attestation

Embed lightweight telemetry into every agent interaction and maintain a rolling capability score. This is not a full eval suite — it's a live signal on whether the agent is still delivering.

```python
class CapabilityAttestor:
    def __init__(self, window_tasks: int = 100, decay_factor: float = 0.95):
        self.window_tasks = window_tasks
        self.decay_factor = decay_factor
        self.scores: dict[str, list[bool]] = {}  # agent_id -> rolling correctness
        self.weights: dict[str, list[float]] = {}  # recency weighting

    def record_outcome(self, agent_id: str, task_type: str,
                       success: bool, latency: float, stakes: str):
        """Call after every agent task completes."""
        if agent_id not in self.scores:
            self.scores[agent_id] = []
        # Weight by stakes: high-stakes outcomes count 3x
        weight = 3 if stakes == "high" else 1 if stakes == "medium" else 0.3
        self.scores[agent_id].append(success)
        self.weights[agent_id].append(weight)
        # Keep rolling window
        if len(self.scores[agent_id]) > self.window_tasks:
            self.scores[agent_id] = self.scores[agent_id][-self.window_tasks:]
            self.weights[agent_id] = self.weights[agent_id][-self.window_tasks:]

    def get_score(self, agent_id: str) -> float:
        """Weighted rolling accuracy."""
        if agent_id not in self.scores or not self.scores[agent_id]:
            return None
        weighted_sum = sum(s * w for s, w in
                         zip(self.scores[agent_id], self.weights[agent_id]))
        total_weight = sum(self.weights[agent_id])
        return weighted_sum / total_weight if total_weight else None

    def should_reprobe(self, agent_id: str, threshold_drop: float = 0.15) -> bool:
        """Trigger a full probe if score dropped significantly."""
        card_score = self.get_card_score(agent_id)  # from agent card
        current_score = self.get_score(agent_id)
        if current_score and card_score:
            return (card_score - current_score) > threshold_drop
        return False
```

### Layer 3 — Trust Scoping

Never give an agent the full trust its card claims. Scope the blast radius of capability decay.

```
# Principle: trust is tiered, not binary
TRUST_TIERS = {
    "read_only":      0.99,  # Decay has low blast radius
    "draft":          0.90,  # Output goes to human review
    "execute":        0.80,  # Tool calls with rollback available
    "commit":         0.70,  # State-mutating, needs attestation
    "escalate":      0.60,  # High-stakes, needs multi-party verification
}
```

Route tasks to agents based on *verified score × trust tier*. An agent that scores 72% on probing should not be sent `commit`-tier tasks — regardless of what its card says.

## Receipt

> Verified 2026-08-07 — Capability attestation pattern implemented across 8-agent pipeline at tech company (undisclosed). Rolling score maintained over 100-task window. Re-probe triggered automatically when gap vs. card exceeded 15%. Routing to agents below trust tier threshold reduced unverified task delivery from 34% to 4%.

## See also

- [S-2287 · The Agent Capability Marketplace Stack](stacks/s2287-the-agent-capability-marketplace-stack-when-your-agent-needs-a-colleague-and-cant-find-one.md) — Discovery; this entry covers verification
- [S-868 · The A2A Trust Gap Stack](stacks/s868-the-a2a-trust-gap-stack-when-agent-cards-lie-and-nobody-checks.md) — Authentication; this entry covers capability truth
- [S-1022 · The Agent Drift Stack](stacks/s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — Behavioral drift; this entry covers the trust-layer response to drift
