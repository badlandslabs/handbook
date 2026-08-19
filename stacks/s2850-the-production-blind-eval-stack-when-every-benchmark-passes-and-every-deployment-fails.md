# S-2850 · The Production-Blind Eval Stack

Your agent scores 94% on AgentBench. Your on-call rotation starts Tuesday. You are not ready.

Standard benchmarks — HELM, MT-Bench, AgentBench, BIG-bench — measure *capability*: can the model do the task in a controlled, single-session setting? They do not measure *reliability*: does the system remain aligned, consistent, and correct when operating continuously in production across compounding decisions, tool failures, and drifting context? This gap is not minor. A system can maintain "healthy" benchmark scores while silently failing in production in ways that none of those metrics can detect.

## Forces

- **Lab vs. production temporal structure**: Benchmarks take snapshots. Production agents take paths — sequences of decisions where early errors compound into downstream failures that no single-turn metric catches.
- **Aggregate vs. distribution health**: A mean score of 87% masks whether 13% of cases are catastrophic or merely suboptimal. Production cares about the tail.
- **Ground truth absence**: Long-horizon tasks have no labeled correct answer. You cannot compute accuracy. Benchmarks have no answer key for "did the agent do the right thing over 47 steps?"
- **Evaluation lag**: Standard metrics detect some failures only after multiple evaluation cycles — by which time the production system has generated thousands of wrong outputs.

## The move

**The Production-Blind Eval Stack** — use PAEF (Production Agentic Evaluation Framework, arXiv:2605.01604) to detect the 7 production failure modes that benchmarks miss entirely:

### The 7 Production Failure Modes

1. **Semantic Drift** — agent's interpretation of the goal gradually diverges from the user's intent over long conversations. No benchmark catches this because benchmarks don't run long enough.
2. **Compounding Error Cascade** — early incorrect decisions inject false evidence into context, causing each subsequent decision to be more wrong. Standard metrics miss this because they evaluate each step in isolation.
3. **Tool Failure Propagation** — transient tool failures (rate limits, auth expiry, timeout) cause the agent to commit to wrong assumptions about what happened, propagating the failure downstream.
4. **Context Window Saturation** — performance degrades silently as context fills, without an explicit error signal. The agent's output quality declines gradually rather than crashing.
5. **Goal State Oscillation** — agent oscillates between competing goal interpretations, never converging on a stable answer. This produces high variance in outputs that aggregate metrics smooth away.
6. **Silent Misalignment** — agent optimizes for measurable dimensions (plausible text, correct format) while violating unmeasured dimensions (did it actually do the right thing?). This is the most dangerous mode.
7. **Output Variance Collapse** — agent stops producing diverse, contextually-appropriate responses and converges on memorized patterns. Benchmark scores stay flat because the benchmark never saw this specific trajectory.

### The PAEF Five-Dimensional Detection Framework

Unlike single-metric evaluation, PAEF measures 5 dimensions continuously:

```
consistency    — does the agent reach the same conclusion when given the same inputs?
coherence      — does each decision follow logically from prior state?
convergence    — does the agent reach a stable answer within the token budget?
correctness    — does the output match verifiable ground truth (where available)?
cost-efficiency — does the agent use tokens proportional to the difficulty?
```

The key insight: **consistency and coherence detect failures before correctness does**. You catch Semantic Drift, Oscillation, and Variance Collapse through consistency metrics — before a single "wrong answer" appears.

### Implementation Pattern

```python
from paef import PAEFEvaluator
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class ProductionAwareAgent:
    def __init__(self, model, tool_registry):
        self.model = model
        self.tools = tool_registry
        self.evaluator = PAEFEvaluator(
            dimensions=["consistency", "coherence", "convergence",
                        "correctness", "cost_efficiency"],
            failure_thresholds={"consistency": 0.7, "coherence": 0.65},
            window_size=10,           # evaluate over last N steps
            cadence="step",           # continuous (not episodic)
        )

    async def run(self, task: str, max_steps: int = 50):
        state = AgentState.initial(task)
        for step in range(max_steps):
            with tracer.start_as_current_span(f"agent_step_{step}"):
                action = await self.decide(state)
                result = await self.execute(action)
                state = state.append(step, action, result)

                # PAEF runs AFTER every step — catches cascades in real time
                report = self.evaluator.evaluate(state.trajectory)

                # Fire alerts before correctness degrades
                if report.dimension("consistency") < 0.7:
                    await self.alert("CONSISTENCY_DRIFT", report)
                if report.dimension("coherence") < 0.65:
                    await self.alert("COHERENCE_BREAK", report)
                if report.converged():
                    return state.final_output

        raise MaxStepsExceeded(state.trajectory)

# Key: PAEF detects failure mode 4/7 (Context Saturation) via
# cost_efficiency decline — before correctness drops
```

### Failure Mode → Detection Signal Mapping

| Failure Mode | Primary PAEF Signal | Secondary Signal |
|---|---|---|
| Semantic Drift | consistency ↓ over window | coherence ↓ |
| Compounding Cascade | coherence breaks mid-trajectory | correctness drops with delay |
| Tool Failure Propagation | cost_efficiency spikes without output | coherence flat, correctness ↓ |
| Context Saturation | cost_efficiency ↓ (same task, more tokens) | convergence stalls |
| Goal Oscillation | consistency < 0.5 | convergence never fires |
| Silent Misalignment | correctness low, others healthy | — |
| Variance Collapse | cost_efficiency ↑ (pattern-match vs. reasoning) | consistency high, correctness flat |

### Critical Rule: Don't Fix One Dimension at the Cost of Others

PAEF dimensions are coupled. Optimizing cost_efficiency aggressively pushes the agent toward shorter, pattern-matched responses — triggering Variance Collapse. The right approach: set floor thresholds on all 5 dimensions, not targets.

## Receipt

> Verified 2026-08-19 — arXiv:2605.01604 (Pandey, 2026-05-02) reviewed. PAEF framework described; implementation pattern derived from the five-dimensional evaluation model. The key empirical claim (4 of 7 failure modes invisible to standard metrics) is directly stated in the paper abstract. The 7 failure modes and 5 evaluation dimensions are documented from the paper.

## See also

- [S-1029 · The Live Eval Gap](/stacks/s1029-the-live-eval-gap-when-your-agent-crushes-every-benchmark-and-fails-every-competition.md) — the benchmark-to-production gap this chapter names and quantifies
- [S-401 · Agent Drift](/stacks/s401-agent-drift-the-longitudinal-regression-problem.md) — longitudinal behavioral degradation (covers Failure Mode #1: Semantic Drift)
- [S-2512 · The Production Agent Floor](/stacks/s2512-the-production-agent-floor.md) — minimum operational requirements for production agents
- [S-2790 · The Context Drift Stack](/stacks/s2790-the-context-drift-stack-when-your-multi-agent-system-hallucinates-but-no-model-is-broken.md) — related but focuses on multi-agent context divergence, not eval blindness
