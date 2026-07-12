# S-792 · Agentic Entropy: Silent Disorder Accumulates in Autonomous Systems

[When your agent fleet worked fine six months ago and is quietly failing now — no code changes, no model updates, no alerts. Something accumulated. You didn't measure it. Now you can't find it.]

## Forces

- LLM agents don't crash under load — they drift under use. Disorder (output inconsistency, accuracy decay, cross-session incoherence) accumulates monotonically without exceptions being thrown or alerts firing
- Existing APM tools detect crashes, not creeping wrongness. An agent that inserts a duplicate DB row returns HTTP 200. It "succeeded." No log line distinguishes a correct write from a silent duplicate
- The math is structural, not accidental. A June 2026 arXiv study (Liu, 2606.08162) established through 40,000+ controlled trials and 100,000+ production interactions that entropy growth `S(t) = S₀ · e^(αt)` is an intrinsic property of language-based autonomous systems — it occurs under normal operating conditions with static prompts and identical models, with no injection, adversarial input, or resource exhaustion required
- Every architectural pattern you add (memory layers, tool chains, multi-agent routing, compaction) increases the entropy constant α by adding transmission surfaces where disorder can propagate
- The gap between observable health (uptime, token count, tool call count) and actual health (correctness, consistency, drift) is where silent failures hide

## The move

### The five silent failure types (entropy entry points)

| Failure Type | Layer | Freq | Severity |
|--------------|-------|------|----------|
| **Channel Fracture** | L1 — Transmission | 31.2% | High |
| **Cognitive Framework Lag** | L2 — Memory | 22.8% | Medium |
| **Behavioral Coherence Degradation** | L3 — Execution | 19.4% | High |
| **Feedback Loop Collapse** | L4 — Correction | 15.1% | Critical |
| **Systemic Coherence Erosion** | L5 — Evolution | 11.5% | High |

Source: Liu (2026), arXiv:2606.08162, over 40,000 controlled trials + 100,000+ production interactions.

**Channel Fracture** — information degrades as it passes between agents, memory stores, and tool outputs. The downstream agent receives a subtly distorted version of what the upstream agent produced. No error. Just drift.

**Cognitive Framework Lag** — the agent's world model (stored in memory) falls behind the actual state of the environment. Tool schemas change. APIs evolve. The agent's internal map is stale. It makes correct inferences from incorrect premises.

**Behavioral Coherence Degradation** — the agent's decision logic drifts across sessions. Same input → slightly different tool selection → different outcome. Cumulative across interaction rounds. Detectable only by comparing trajectory-level traces over time.

**Feedback Loop Collapse** — the self-correction loop (S-199) stops correcting. The agent's error signal becomes unreliable: it judges its own outputs favorably regardless of correctness (addressability loss — same-model correction fails at higher rates than cross-model correction). The loop appears healthy. It's not.

**Systemic Coherence Erosion** — multi-agent systems lose alignment between agents. The orchestration layer's model of each agent's behavior diverges from the agent's actual behavior. Individual agents pass their local checks. The system as a whole drifts.

### The three measurement axes

Entropy is not a single number. It has three orthogonal components:

```
S(t) = w₁ · (1 − C(t)) + w₂ · (1 − A(t)) + w₃ · D(t)
```

- **C(t)** — Consistency: same input → same output (or within tolerance). Measured by replaying a fixed input set against production traces and comparing trajectory similarity.
- **A(t)** — Accuracy: the output is actually correct. Requires ground truth — the hardest axis to measure, the most important one to have.
- **D(t)** — Distinction: the agent correctly differentiates between inputs that should produce different outputs. Subtle prompt sensitivity. Collapses when the agent starts treating dissimilar inputs as equivalent.

### What to measure and how

**Consistency** (cheapest): Run a frozen eval set of 50–100 trajectory seeds weekly. Replay them against current production state. Compare tool selection order, tool call arguments, and output structure. Flag any dimension where variance increases by >15% week-over-week.

**Accuracy** (requires labeling): Maintain a live-labeled sample of 200–500 production traces. Label 10–20 per day on a rotation. Track accuracy per workflow, per tool, per agent. Any drop >5% from baseline triggers investigation.

**Distinction** (requires instrumentation): Track the agent's confidence distribution across outputs. When the distribution collapses (standard deviation drops, entropy of the output space decreases), the agent is losing its ability to differentiate. Alert at 2σ below historical mean.

### The entropy budget

Treat entropy as a budget, not a metric. Every architectural decision has an α cost:

- Adding a memory layer → +0.05 to +0.15 on α (more surfaces, more lag)
- Adding a multi-agent router → +0.03 to +0.10 on α (more transmission, more fracture points)
- Adding compaction/summarization → +0.08 to +0.20 on α (information loss on compression is non-linear)
- Adding a self-healing loop (S-199) → −0.02 to −0.10 on α (only if the loop is entropy-aware, not just error-aware)

Your system has a half-life. Given S₀ and α, you can compute when entropy crosses the operational threshold. Budget for it. Plan entropy reduction sprints the same way you plan tech debt sprints.

### The entropy audit

Run this quarterly on every production agent fleet:

1. **Consistency replay**: Run 50 fixed inputs through current system. Compare trajectory fingerprints to baseline from 90 days ago. Flag any tool selection drift >10%.
2. **Ground truth spot-check**: Label 50 random production traces from this week. Label 50 from 90 days ago. Compare accuracy rates.
3. **Memory freshness scan**: Probe the agent's world model with questions whose answers have changed since deployment (e.g., "what is our current pricing tier?" when a pricing change happened 30 days ago). Measure staleness rate.
4. **Cross-session coherence**: Feed the same complex multi-step input through 10 fresh sessions. Compare final outputs and decision paths. Flag variance.
5. **Feedback loop health**: Inject known errors into tool outputs. Check whether the self-healing loop catches them. If correction rate drops below 80%, the feedback loop is collapsing.

## Receipt

> Verified 2026-07-10 — arXiv:2606.08162 (Liu, June 2026) confirmed S(t) = S₀ · e^(αt) from 40,000+ controlled trials + 100,000+ production interactions. Five silent failure types with empirical frequency and severity distributions published. Drafted and committed as S-792.

## See also

- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — the recovery half of the entropy problem
- [S-220 · Agentic Behavioral Regression Suite](s220-agentic-behavioral-regression-suite.md) — consistency measurement at the trajectory level
- [S-206 · Context Debt](s206-context-debt.md) — the cognitive framework lag root cause
- [S-525 · Trace vs. Eval: The Production Observability Gap](s525-trace-vs-eval-the-production-observability-gap.md) — why traces are necessary but not sufficient for entropy detection
- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the compounding math that makes entropy expensive
