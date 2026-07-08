# S-771 · Collective Hallucination: The Network Amplification Problem

A single confident mistake from one agent becomes a shared false consensus across your entire multi-agent system. Your agents aren't hallucinating independently — they're propagating and reinforcing each other's hallucinations through the communication topology. The problem isn't any individual agent. It's the network.

## Forces

- **Hallucination compounds, not averages.** In multi-agent settings, recursive agent interactions amplify rather than cancel errors. A false claim from Agent A becomes input to Agent B, which treats it as context-validated ground truth and elaborates on it. Agent C receives both and amplifies further. By round 3, the system holds a confident false consensus that no individual agent produced.
- **Confidence reinforcement masquerades as evidence.** When two independent agents assert the same false fact, the repetition itself reads as corroboration to downstream agents. The network treats convergence as signal. The system has no mechanism to distinguish "this is true because multiple agents agree" from "this is false but got repeated."
- **Communication topology governs amplification.** The rate at which hallucinations spread depends on graph structure: dense all-to-all topologies maximize diffusion speed; chain and star topologies slow it but make errors harder to detect; adversarial edges (attacker-controlled agents) can redirect consensus toward target false beliefs. The same architecture that makes your system robust to individual failures makes it vulnerable to collective error.
- **Existing defenses target the agent, not the network.** Hallucination mitigation research (fine-tuning, RAG, self-consistency, chain-of-thought) is designed for single-model settings. Applying single-agent defenses to a multi-agent network leaves the inter-agent propagation channel completely unaddressed.

## The move

- **Model hallucination as a dynamical system on your agent graph.** Each agent is a node; each inter-agent message is an edge. A hallucinated claim starts as a seed at one node. Each transmission round applies an amplification factor (measured at 1.08–1.45× per round in published multi-agent studies). Track the claim's propagation state separately from its content — does it survive 3 rounds? 5? The R₀ of a hallucination in your network tells you how urgent containment is.

```python
# Simplified hallucination propagation tracker
# Based on arXiv:2606.07941 (Collective Hallucination in Multi-Agent LLMs, June 2026)

from dataclasses import dataclass
from enum import Enum

class ClaimState(Enum):
    GROUNDED = "grounded"       # traceable to authoritative source
    UNVERIFIED = "unverified"   # no source, no contradiction
    CONTESTED = "contested"     # agents disagree
    PROPAGATING = "propagating" # spreading beyond source agent
    CONSENSUS = "consensus"     # majority network assertion

@dataclass
class Claim:
    content_hash: str
    originating_agent: str
    source_confidence: float   # 0.0–1.0
    propagation_count: int = 0
    state: ClaimState = ClaimState.UNVERIFIED
    supporting_agents: set = None  # agents asserting this claim

    def __post_init__(self):
        if self.supporting_agents is None:
            self.supporting_agents = {self.originating_agent}

# Amplification tracking
def record_transmission(claim: Claim, receiving_agent: str, topology: dict):
    claim.propagation_count += 1
    claim.supporting_agents.add(receiving_agent)
    
    # Compute amplification factor based on topology
    degree = len(topology.get(receiving_agent, []))
    # High-degree nodes amplify faster (many downstream consumers)
    AF = 1.0 + 0.08 * (degree / 10)  # empirical approximation from literature
    
    # HPR-adaptive: if source_confidence * AF > threshold, escalate
    if claim.source_confidence * (AF ** claim.propagation_count) > 0.7:
        claim.state = ClaimState.PROPAGATING
    
    # Consensus detection: if >60% of reachable agents assert, flag
    total_agents = len(topology)
    if len(claim.supporting_agents) / total_agents > 0.6:
        claim.state = ClaimState.CONSENSUS
    
    return claim

# Defense: bidirectional entailment clustering (from IEEE TNNLS 2026)
# Validates a claim by checking semantic consistency across multiple edges
# rather than accepting repetition as confirmation
```

- **Use topology-aware containment, not agent-level filtering.** If a hallucination is detected at Node X, quarantine the subgraph reachable from X before the next reasoning round — not just the agent. The critical window is 2–3 propagation rounds before consensus forms. Standard content filtering at the agent level misses the structural amplification entirely.
- **Insert provenance-tagged ground-truth anchors at high-centrality nodes.** Nodes with high betweenness centrality (bridge agents that connect subgraphs) have disproportionate influence on network-wide belief. Injecting traceable, source-validated facts at these nodes blocks hallucination entry points more efficiently than distributed filtering.
- **Apply the HPR-Adaptive defense for adversarial scenarios.** In attacker-controlled agent injection (malicious agent added to the network), the amplification factor spikes above 1.45. Monitor for sudden shifts in network-wide assertion convergence speed — a 2× acceleration in consensus formation is a stronger signal than any single agent's output quality.

## Receipt

> Verified 2026-07-07 — arXiv:2606.07941 (Collective Hallucination in Multi-Agent LLMs, June 2026) provides empirical baseline: 1.45× amplification factor, R₀=1.08 per round in undefended networks. HPR-Adaptive defense reduces hallucination rate by 39% (0.118→0.072) and AF to 1.08. IEEE TNNLS (Xu & Wu, Jan 2026) provides token-level propagation model and bidirectional entailment clustering defense. Centific (Jul 2026) and Conceptualise (May 2026) independently confirm cascading multi-agent errors as a top production failure mode. The network-propagation framing is absent from all existing handbook entries (spot-checked S-29 false consensus, S-41 handoff patterns, S-746 confabulation, S-646 agent drift, S-320 agentic RAG, S-395 cost circuit breakers — none model hallucination as a graph dynamical process).

## See also

- [S-29 False Consensus](s29-false-consensus.md) — agreement ≠ truth, vote only over independent samples
- [S-41 Agent Handoff Patterns](s41-agent-handoff-patterns.md) — structured handoff reduces unverified assertion passing
- [S-746 Agentic Memory Confabulation](s746-agentic-memory-confabulation-the-self-reinforcing-false-belief-problem.md) — single-agent false belief; distinct from multi-agent network consensus
- [S-395 Agent Cost Circuit Breakers](s395-agent-cost-circuit-breakers.md) — $15K case of two agents referencing each other's outputs as ground truth (prefiguration of collective hallucination)
- [S-646 Agent Drift in Multi-Agent Systems](s646-agent-drift-in-multi-agent-systems.md) — progressive deviation; related propagation dynamic, different symptom
