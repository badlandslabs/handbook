# S-2441 · The Cascade Amplification Stack — When One Agent's Wrong Output Becomes Everyone's Ground Truth

[Your multi-agent pipeline has been running for three hours. Nobody noticed when the research agent cited a hallucinated statistic from a web search. The writer agent turned it into a confident paragraph. The reviewer agent checked the writing quality — not the facts. The publisher agent posted it. By the time the correction email arrives, the number has been quoted in three downstream systems, two Slack channels, and a stakeholder report. This is cascade amplification: not one agent failing, but one agent's error becoming the epistemic foundation for every agent downstream, compounding in both wrongness and confidence at each step until the final output is confidently catastrophic.]

## Forces

- **Multiplication, not addition.** Each agent in a chain multiplies the error surface, not adds to it. A 95%-accurate agent in a chain of five completes 77% of workflows correctly — in isolation. Downstream, that 23% failure rate becomes 100% confidence input for the next agent.
- **Trust without verification.** Agents treat peer-agent outputs as authoritative by default. The researcher says "fact X"; the writer treats it as fact; the reviewer checks style, not fact; the publisher treats it as cleared. No agent in the chain independently re-verifies what an upstream agent produced.
- **Amplification outpaces detection.** Errors propagate 17.2x faster in uncoordinated multi-agent systems than in single-agent baselines. By the time a human notices the final output is wrong, the contamination is already in three downstream systems.
- **Traditional circuit breakers fail here.** Circuit breakers are designed for homogeneous failures (a service goes down, stop calling it). Cascade amplification is a heterogeneous failure: the tool returned valid data, the agent processed it validly, the output is syntactically correct but semantically wrong. Standard CBs never trip.

## The Move

### 1. Know the three vulnerability classes

Every cascade has a root class. Treat them differently:

| Class | Mechanism | Primary Signal | Primary Fix |
|-------|-----------|----------------|-------------|
| **Cascade Amplification** | Wrong output propagates as authoritative input downstream | Confidence in wrong answer increases across agents | Output contracts + upstream credibility scoring |
| **Topological Sensitivity** | Network structure determines blast radius; hub agents concentrate risk | Single agents have disproportionate downstream reach | Hub decoupling — break the hub's ability to poison the full graph |
| **Consensus Inertia** | False claims embed into shared artifacts (code, specs, test cases), making correction require unwinding the entire dependency chain | Dependencies on wrong outputs prevent rollback | Artifact provenance + rollback-capable dependency graphs |

### 2. Centralize critical-path coordination

The single most effective architectural intervention: move from uncoordinated (17.2x amplification) to centralized (4.4x amplification) — a **75% reduction in blast radius** without changing any individual agent.

```python
# Anti-pattern: uncoordinated chain — each agent owns its output, no shared contract
class UncoordinatedChain:
    """Each agent assumes peer output is authoritative. Amplification: 17.2x."""
    def run(self, input_data):
        research = self.research_agent.execute(input_data)
        write = self.writer_agent.execute(research)  # trusts research blindly
        review = self.reviewer_agent.execute(write)  # checks style, not fact
        publish = self.publisher_agent.execute(review)
        return publish

# Pattern: centralized coordination with trust boundaries at every handoff
class CentralizedCoordination:
    """Central coordinator gates every inter-agent handoff.
    Amplification: 4.4x — 75% blast radius reduction.
    """
    def __init__(self):
        self.coordinator = CentralCoordinator()

    def run(self, input_data):
        research = self.research_agent.execute(input_data)
        # Gate: coordinator validates research output before writer sees it
        coordinator.validate_gate("research", research)
        write = self.writer_agent.execute(research)
        coordinator.validate_gate("writer", write)
        review = self.reviewer_agent.execute(write)
        coordinator.validate_gate("reviewer", review)
        publish = self.publisher_agent.execute(review)
        coordinator.validate_gate("publisher", publish)
        return publish

class CentralCoordinator:
    """Per-handoff validation layer. Blocks poisoned outputs from propagating."""
    def __init__(self):
        self.fact_checker = LLMJudge(model="claude-sonnet-4")
        self.confidence_threshold = 0.85

    def validate_gate(self, agent_name: str, output: AgentOutput):
        # Run fact checks on all claims in the output
        claims = extract_claims(output.content)
        verdicts = self.fact_checker.batch_verify(claims)
        low_confidence = [c for c, v in zip(claims, verdicts)
                          if v["confidence"] < self.confidence_threshold]
        if low_confidence:
            raise CascadeRisk(
                f"[CASCADE GUARD] {agent_name} output contains "
                f"{len(low_confidence)} low-confidence claims. "
                f"Blocking handoff until verified."
            )
```

### 3. Trust boundaries at every A2A handoff — don't decouple arbitrarily

The goal is not to eliminate inter-agent communication. It's to make each handoff a **verified contract**, not a blind pass-through:

- **Delegation timeout**: if the sub-agent doesn't return within `expected_duration × 2`, treat it as a potential cascade source, not a slow worker. Query its state directly, don't re-delegate.
- **Output schema contract**: define the contract before delegation. The calling agent should validate the returned structure against the contract — not the content, but the schema. If `confidence_score` is missing when it was promised, that's a cascade signal.
- **Confidence watermark**: every inter-agent message carries a `min_verification_level`. If a research agent marks output as `high_confidence`, the writer agent must respect that claim by re-checking non-obvious claims before treating them as facts.

### 4. Separate resource pools — don't let cascade burns consume shared budgets

When a cascade is detected, it consumes shared resources (rate limits, API budgets, context windows) at a rate proportional to its length. Isolate them:

```python
class ResourcePool:
    """Separate pools prevent cascade from burning shared quotas.
    Cascade detection → pool isolation → graceful degradation."""
    def __init__(self):
        self.shared = ResourcePool("shared", budget_tokens=500_000)
        self.cascade_isolation = ResourcePool(
            "cascade-isolation",
            budget_tokens=50_000,  # tiny — just enough to detect and stop
        )
        self.downstream_protection = ResourcePool(
            "protected-downstream",
            budget_tokens=200_000,  # preserves resources for downstream cleanup
        )

    def record_cascade_detected(self, agent_chain: list[str]):
        # Deduct from cascade pool only — protect shared and downstream
        for agent in agent_chain:
            self.cascade_isolation.allocate(agent, budget=10_000)
        # Alert: cascade isolation pool is 20% consumed
```

### 5. Consensus checks for multi-agent decisions

When multiple agents must agree on a decision, consensus isn't just reliability — it's cascade containment. A false consensus (all agents agreeing on a wrong fact) is a cascade signal, not a confidence signal.

```python
def multi_agent_consensus_check(
    agents: list[Agent],
    task: str,
    claim: str,
    required_agreement: float = 0.75,
) -> ConsensusResult:
    """Consensus that fails suspiciously (too-fast agreement) is a cascade signal.
    Run each agent independently on the same claim extraction task."""
    verdicts = [agent.verify_claim(claim) for agent in agents]

    agreement_rate = sum(1 for v in verdicts if v["agrees"]) / len(verdicts)
    response_variance = statistics.variance([v["confidence"] for v in verdicts])

    # Fast consensus + low variance = possible cascade poisoning
    # (all agents read the same corrupted source)
    if agreement_rate >= required_agreement and response_variance < 0.05:
        return ConsensusResult(
            outcome="SUSPECT_CASCADE",
            agreement=agreement_rate,
            signal="Near-unanimous agreement at low variance — possible shared poisoned source",
            action="ISOLATE_AND_REVERIFY",
        )

    return ConsensusResult(
        outcome="AGREED" if agreement_rate >= required_agreement else "DISAGREED",
        agreement=agreement_rate,
        action="PROCEED" if agreement_rate >= required_agreement else "ESCALATE",
    )
```

### 6. The kill-switch paradox: design layered kills that track children

A kill switch that kills the parent but leaves 14 children running is worse than no kill switch. Every agent in your system must implement:

```python
class AgentKillSwitch:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.children: list[str] = []  # track spawned child agents
        self.parent: str | None = None

    def register_child(self, child_id: str):
        self.children.append(child_id)

    def cascade_kill(self, reason: str):
        """Kill this agent AND all children, in dependency order."""
        log(f"[KILL] {self.agent_id}: {reason}")

        # Kill children first (leaf-to-root order)
        for child_id in self.children:
            child_agent = get_agent(child_id)
            child_agent.cascade_kill(f"Parent {self.agent_id} killed: {reason}")

        # Then kill self
        self.shutdown()

        # Notify parent so it knows a child died
        if self.parent:
            parent_agent = get_agent(self.parent)
            parent_agent.on_child_death(self.agent_id, reason)
```

The critical mistake: most agent kill switches are a single boolean. Make them a **directed acyclic graph of lifecycle ownership** — every agent knows its children, and shutdown propagates leaf-to-root.

## Verification

> Receipt pending — run verification and record actual output

## See also
- [S-1157 · The Cascading Failure Containment Stack](stacks/s1157-the-cascading-failure-containment-stack-when-one-agent-goes-wrong-and-thirty-follow.md) — agent-level belief propagation and per-tool circuit breakers
- [S-1443 · The Agent Network Collapse Stack](stacks/s1443-the-agent-network-collapse-stack-when-your-multi-agent-coordination-becomes-a-cascade.md) — A2A state machine failures and MCP concurrency governance
- [S-1026 · The Evaluation Coverage Gap Stack](stacks/s1026-the-evaluation-coverage-gap-stack-when-4-out-of-7-failure-modes-sneak-past-your-test-suite.md) — eval blind spots that let cascade sources survive to production
