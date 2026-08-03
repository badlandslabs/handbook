# S-2040 · The Conway's Law Stack — When Your Org Chart Is Already Your Agent Architecture

Your customer-onboarding agent and your billing agent don't coordinate well. Not because of a technical bug — because the teams that built them don't talk to each other. Conway's Law — systems mirror the communication structures of the organizations that build them — turned 58 this year and has never been more dangerous. When the "system" is a network of autonomous agents making decisions at machine speed, every organizational seam becomes a failure point where context is lost, handoffs break, and agents optimize for local metrics that contradict each other. The fix is designing agent architectures that anticipate and correct for the organizational structure that produced them.

## Forces

- **Agents compound organizational dysfunction at machine speed.** In traditional software, Conway's Law produces awkward API boundaries. In agentic systems, it produces confidently wrong decisions with no error code — and agents keep compounding those mistakes without pausing to reconsider.
- **Your org chart is your agent boundary map.** Teams that don't communicate produce agents that don't share state. If the payments team and the fraud team never sync, their agents will disagree on what's a valid transaction — and the customer will discover it.
- **Conway alignment is harder than API versioning.** Retrofitting communication protocols onto agents that were designed by siloed teams is expensive and fragile. The right time to apply Conway's Law is before the agents exist.
- **Design-by-committee produces coordination-heavy agents; design-by-silo produces agents that can't coordinate.** Both are wrong in different ways. The goal is intentional alignment: design the org structure that would produce the agent architecture you actually need.

## The move

### 1. Map agents to organizational seams, not job titles

The starting point is a team-to-agent audit: for every agent, ask *which team owns it* and *which teams it needs to cooperate with*. Agents that bridge teams (onboarding → finance, support → engineering) are high-risk coordination points. These are the agents that need explicit handoff contracts and shared state schemas — not because of a technical gap, but because of the organizational gap that produced them.

```
# Conway alignment audit
# For each agent, document:
AGENT_CATALOG = {
    "onboarding": {
        "owner": "growth-engineering",      # team that built it
        "requires_input_from": ["crm"],     # organizational dependencies
        "delivers_to": ["billing", "support"],
        "coordination_risk": "HIGH"         # crosses 2+ team boundaries
    },
    "fraud-scoring": {
        "owner": "risk-engineering",
        "requires_input_from": ["payments", "auth"],
        "delivers_to": ["payments"],
        "coordination_risk": "LOW"          # stays within risk-engineering orbit
    }
}
```

### 2. Design the team structure before the agent structure

Conway's Law works in both directions. You can use it reactively (accept your org chart and build agents that fit) or proactively (design the agent architecture you need, then restructure the teams that build it). The proactive approach produces more coherent systems but requires organizational will.

```
# Top-down Conway alignment: define agent topology first
# Then ask: "Does our org structure support this topology?"

DESIRED_TOPOLOGY = [
    ("orchestrator", "gates"),
    ("orchestrator", "worker-A"),
    ("orchestrator", "worker-B"),
    ("worker-A", "worker-C"),
    ("worker-B", "worker-D"),
]

# Conway check: for each edge, does a team boundary exist?
# Edge (orchestrator → worker-A): same team? YES → clean handoff
# Edge (worker-A → worker-C): different teams? NO → org restructure needed
```

### 3. Build explicit handoff contracts at every organizational seam

Every pair of agents that cross a team boundary needs a structured handoff: a defined schema for what state is transferred, a version number, and an acknowledgment protocol. This is the agentic equivalent of an API contract — and like API contracts, it's only valuable if both teams own it.

```python
from typing import TypedDict
from datetime import datetime

class HandoffContract(TypedDict):
    source_agent: str
    target_agent: str
    team_boundary: bool          # True = crosses org seam
    schema_version: str
    required_fields: list[str]
    optional_fields: list[str]
    acknowledgment_required: bool
    escalation_on_timeout_minutes: int

# Organizational seam = high ceremony handoff
handoff = HandoffContract(
    source_agent="onboarding",
    target_agent="billing",
    team_boundary=True,           # growth ↔ finance
    schema_version="2.1.0",
    required_fields=["customer_id", "plan_tier", "effective_date"],
    optional_fields=["coupon_code", "referral_source"],
    acknowledgment_required=True,
    escalation_on_timeout_minutes=5  # org seams need faster escalation
)
```

### 4. Add a cross-team coordination agent (the "org-chart corrector")

For agent networks that cross multiple team boundaries, introduce a thin coordination layer whose job is specifically to reconcile the outputs of siloed agents. This agent doesn't do domain work — it watches for contradictions between agent outputs and flags them before they propagate downstream. Think of it as the agentic equivalent of a program manager who sits in every team's standup.

```python
class ConwayCorrector:
    """
    Cross-team coordination agent.
    Reads outputs from boundary-crossing agents,
    detects contradictions, and escalates to human org review.
    """
    def __init__(self, agent_outputs: list[AgentOutput]):
        self.seam_agents = [a for a in agent_outputs if a.team_boundary]
        
    def detect_contradiction(self) -> list[Contradiction]:
        contradictions = []
        for i, a in enumerate(self.seam_agents):
            for b in self.seam_agents[i+1:]:
                if self._shares_context_domain(a, b):
                    if self._contradicts(a.output, b.output):
                        contradictions.append(Contradiction(
                            agent_a=a.name, agent_b=b.name,
                            org_boundary_a=a.owner_team,
                            org_boundary_b=b.owner_team,  # shows which teams must sync
                            contradiction=a.output ^ b.output,
                            escalate=True   # org-seam contradictions always escalate
                        ))
        return contradictions
```

### 5. Instrument coordination failures with org-context

When a multi-agent coordination failure occurs, the incident report should include the organizational topology at the time: which teams owned which agents, whether the failing edge crossed an org boundary, and when the relevant teams last communicated. This turns Conway's Law from a vague systemic observation into a first-class incident dimension.

## Receipt

> Verified 2026-08-02 — Research sourced from: tianpan.co (April 2026), Swoft.ai multi-agent coordination article (April 2026), sweft.ai agent patterns article (July 2026), Cemri 2025 arXiv paper on multi-agent failure modes. Composite Score: 8.65. Conway's Law for agentic systems is a fresh angle with strong production urgency and zero existing handbook coverage. Pattern: organizational seams become agent failure points — same root cause as Conway's Law in traditional software, but compounded by agent autonomy.

## See also

- [S-2038 · Agent Orchestration Pattern](stacks/s2038-the-agent-orchestration-pattern-stack-when-one-agent-isnt-the-problem-but-your-architecture-is.md) — orchestration patterns that Conway's Law shapes from within
- [S-1013 · Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement as a symptom of org-seam agents
- [S-2037 · Agent Drift Stack](stacks/s2037-the-agent-drift-stack-when-your-agent-systemically-deviates-from-its-goals-over-extended-interactions.md) — drift accelerated when siloed agents optimize locally
- [S-1965 · Contextual Drift Stack](stacks/s1965-the-contextual-drift-stack-when-your-parallel-agents-produce-results-that-cant-be-together.md) — parallel agents diverging from unaligned team incentives
