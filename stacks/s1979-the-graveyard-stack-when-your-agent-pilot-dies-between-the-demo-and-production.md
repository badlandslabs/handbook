# S-1979 · The Graveyard Stack — When Your Agent Pilot Dies Between the Demo and Production

*When your agent nails the boardroom demo, gets buried in the first week of production, and nobody can explain why. The pilot-to-production graveyard is real — 60–88% of enterprise agent pilots never ship. The ones that do share a pattern: they stopped optimizing for demos and started engineering for the gap.*

## Forces

- **The demo uses clean data; production uses reality.** Agents that pass evaluation on curated test sets collapse on scanned documents at odd angles, handwritten annotations, non-standard certificate formats, and 50 overlapping policy rules instead of one. The evaluation data and production data occupy different distributions — and the agent never knew it was being tested on the wrong one.
- **The pilot assumes trust; production requires proof.** Demos skip audit trails, compliance checks, and rollback procedures because they don't need them. Production environments demand all three before the first transaction clears — and the gap between "it works" and "it's allowed to work" is where pilots go to die.
- **The demo tests capability; production tests resilience.** An agent that completes a task correctly 95% of the time is impressive. An agent that completes it correctly while handling API timeouts, partial tool failures, noisy inputs, and cost overruns — that's the bar production actually sets.
- **Pilot success is measured in outputs; production success is measured in outcomes.** The pilot team celebrates when the agent produces the right answer. The production team fails when nobody can explain *why* the agent produced it, *what would make it fail next*, or *who is accountable when it does*.
- **Multi-agent coordination failures are invisible in single-agent pilots.** The moment you compose two agents, coordination becomes the dominant failure mode — not capability. Custom agent-to-agent integrations break silently, and by the time you notice, both agents are producing results that can't be composed into a coherent output.

## The move

**Engineer the gap before the pilot, not after.**

### 1. Define failure modes explicitly, not just success criteria

Before writing a single prompt, write the "what the agent must never do" list. Production-grade agents need both:

```markdown
# What the agent MUST do
- Route tickets with >85% accuracy
- Complete end-to-end in <90 seconds
- Surface low-confidence responses for human review

# What the agent must NEVER do
- Modify records without a human-in-the-loop gate
- Send outputs to external systems without audit logging
- Exceed $0.50 per transaction in tool costs
- Proceed when confidence < 0.7 on classification tasks
```

The denial list is the product spec. Everything else is out of scope.

### 2. Run on production-representative data from day one

The fastest way to find your pilot-to-production gap is to introduce production noise immediately:

```
# Production noise injection pipeline
- Inject 10% malformed inputs (missing fields, wrong types, encoding issues)
- Inject 5% adversarial inputs (edge cases, ambiguous cases)
- Inject realistic latency distributions on tool calls
- Inject partial failure modes (tool returns empty, times out, returns partial)
- Run cost estimation per trace and alert on outliers
```

If the agent can't handle noise in week two of the pilot, it won't handle it in week twelve of production.

### 3. Build the production checklist before the demo checklist

The Cordum 20-control model (2026) maps the minimum viable production surface:

| Control | Pass gate |
|---------|-----------|
| Explicit failure mode registry | Hard stop — no pilot without it |
| Audit trace on every decision | Hard stop |
| Human-in-the-loop threshold defined | Hard stop |
| Cost bounding per session | Hard stop |
| Rollback procedure documented and tested | Soft gate — must ship within 2 weeks |
| Observability dashboard live | Soft gate |
| Escalation owner assigned per failure type | Soft gate |

The demo checklist validates capability. The production checklist validates resilience.

### 4. Instrument for the gap, not just for success

Standard observability catches failures. Production observability catches *why* failures cluster:

```python
# The four signals that predict pilot death
class AgentHealthMetrics:
    # Signal 1: capability ceiling — accuracy flatlines as input difficulty increases
    accuracy_by_input_difficulty: dict[int, float]
    
    # Signal 2: confidence calibration drift — agent confidence mispredicts actual accuracy
    confidence_vs_outcome: list[tuple[float, bool]]
    
    # Signal 3: cost per successful outcome trends up (diminishing returns)
    cost_per_success_over_time: list[float]
    
    # Signal 4: tool call chains get longer without proportional quality gain
    tool_depth_vs_quality_gain: list[tuple[int, float]]
```

When any of these signals crosses its threshold, the pilot is entering the graveyard. Act before production, not after.

### 5. Structure handoffs with explicit contracts

In multi-agent systems, the most common pilot failure is silent composition failure:

```python
# Explicit handoff contract (not just a message)
@dataclass
class AgentHandoff:
    sender_id: str
    receiver_id: str
    task_description: str
    required_capability: list[str]       # what receiver must support
    acceptance_criteria: list[str]        # how sender defines success
    failure_response: Literal["escalate", "retry", "decompose", "halt"]
    max_attempts: int = 3
    timeout_seconds: int = 120

# Anti-pattern: unstructured message passing
# agent_a.send_message("here's the data, please process it")

# Correct: typed contract with failure modes pre-negotiated
handoff = AgentHandoff(
    sender_id="classifier",
    receiver_id="router",
    task_description="Route this ticket to the correct queue",
    required_capability=["priority_scoring", "queue_routing"],
    acceptance_criteria=["priority_score between 1-5", "queue_id is valid"],
    failure_response="escalate"  # Don't silently default to retry loops
)
```

The handoff contract is the integration test. If you don't write it, the agents will improvise one — and it will be wrong.

### 6. Measure pilot-to-production readiness with the deployment readiness ratio

```
Deployment Readiness Ratio (DRR) = P(PASS | production_noise) / P(PASS | clean_eval)

- DRR > 0.95: Ready to ship
- DRR 0.80-0.95: Ship with monitoring and rollback plan
- DRR 0.60-0.80: Significant gap — engineer the noise cases first
- DRR < 0.60: Pilot is in the graveyard — rearchitect before redeploying
```

The demo gives you P(PASS | clean_eval). The production noise injection pipeline gives you P(PASS | production_noise). The ratio tells you whether your pilot is a product or a prototype.

## Receipt

> Verified 2026-08-01 — Cross-referenced against: Presenc AI (pilot mortality data, May 2026), Gartner (40% enterprise apps embed agents by 2026, >40% at risk of cancellation by 2027), Paul Okhrem / S&P Global (31% running agents in production vs 80% piloting), Cordum 20-control deployment checklist (2026), Future AGI (6 eval drift modes, 2026), Open Empower (common production failure patterns, Jun 2026), BCG / Forrester (5.1-month median time-to-value).

## See also

- [S-1978 · The Benchmark Faith Stack](s1978-the-benchmark-faith-stack-when-your-agent-scores-80-on-swe-bench-and-fails-in-production.md) — When the eval score and the deployment capability are different numbers
- [S-1976 · The Tool Catalog Stack](s1976-the-tool-catalog-stack-when-your-agent-has-30-tools-and-cant-decide-which-one-to-use.md) — When too many tools make failure surfaces unpredictable
- [S-1974 · The Confident Failure Stack](s1974-the-confident-failure-stack-when-your-agent-knows-something-went-wrong-but-keeps-going-anyway.md) — When the pilot succeeds and production fails silently
