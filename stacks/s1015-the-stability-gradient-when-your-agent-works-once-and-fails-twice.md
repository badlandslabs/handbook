# S-1015 · The Stability Gradient: When Your Agent Works Once and Fails Twice

Your agent passed every test. It shipped. Monday morning it failed on the same task it aced on Friday — same input, same model, different result. You don't know why. Nobody does. This is not a model problem. It is an **architectural problem**.

## Forces

- **LLMs are stochastic by design.** Even at temperature=0, GPU cluster scheduling, floating-point non-determinism, and batching interactions at token sampling boundaries produce different outputs on identical inputs. "Nearly deterministic" is not determinism.
- **Single-trial evaluation lies.** τ-bench found agents achieving 60% pass@1 may exhibit only 25% consistency across multiple trials. A 60% pass@1 agent can fail 3 out of 4 times when reliability matters. Benchmarks measuring one-shot success systematically overestimate production readiness.
- **Tool-call variance compounds.** A 5% per-call failure rate with 5 tool calls per task compounds to a 23% task-level failure rate — without retry. Each additional tool call multiplies the probability of a divergent trajectory.
- **The demo/production gap is non-determinism.** Most teams treat "works in demo" as evidence of capability. It is evidence of one sample from a distribution. The variance is not noise — it is the signal.
- **The right response depends on the variance type.** Output text variance (different words, same meaning) requires a different fix than behavioral variance (different tools, different sequence). Conflating them leads to over-engineering or under-engineering.

## The move

Stabilize agent output along a gradient: **understand → measure → constrain → scaffold → harden**. Each layer costs more but buys more stability. Choose the layer that matches your reliability requirement.

### 1. Measure the actual variance

Before fixing, quantify. Run every eval task ≥20 times with identical inputs and pinned model version. Track:

```
consistency_rate = tasks where output = reference_output / total_runs
behavioral_variance = entropy(tool_sequence_per_run)
output_stability = token_exact_match_rate_across_runs
trajectory_diversity = Jaccard(tool_sets_per_run)
```

- **consistency_rate < 80%**: High behavioral variance — agent takes different paths each run. Critical.
- **consistency_rate 80–95%**: Moderate. Same outcome, different reasoning. Monitor.
- **consistency_rate > 95%**: Stable. Investment in hardening may not pay off.

Do this in shadow mode first (log without acting) to avoid propagating instability.

### 2. Constrain output variance (cheapest)

```python
# Constrain tool selection to a verified subset
ALLOWED_TOOLS = {"search", "calculate", "format_output"}
TOOL_BLACKLIST = {"delete", "write", "execute", "send_email"}

# Force conservative tool selection when stakes are high
def constrained_tool_selection(context: AgentContext) -> str:
    """Pick the lowest-risk tool that satisfies the goal."""
    candidates = available_tools(context)
    allowed = [t for t in candidates if t.name in ALLOWED_TOOLS
               and t.name not in TOOL_BLACKLIST]
    if not allowed:
        return escalate_to_human(context, reason="no_safe_tool")
    return select_by_preference(allowed)
```

Schema validation on tool arguments catches ~40% of hallucinated calls before execution (BFCL data).

### 3. Scaffold with deterministic recovery paths

When the agent's preferred path is uncertain, scaffold a fallback:

```python
def scaffolded_execute(agent: Agent, task: Task, context: AgentContext):
    """Execute task with deterministic fallback on divergence."""
    primary = agent.execute(task, context)

    # Define the acceptable execution envelope
    acceptable_tools = set(ALLOWED_TOOLS)
    max_steps = MAX_STEPS_BY_TASK_TYPE[task.type]
    cost_ceiling = COST_CEILING_BY_TASK_TYPE[task.type]

    # Detect divergence from envelope
    if primary.used_tools - acceptable_tools:
        primary = agent.execute(task, context.with_constrained_tools(acceptable_tools))
    if primary.step_count > max_steps:
        primary = truncate_and_summarize(primary, max_steps)
    if primary.cumulative_cost > cost_ceiling:
        primary = halt_with_checkpoint(primary, "cost_ceiling")

    return primary
```

The scaffold does not remove the agent's capability — it defines the boundary where the system stops trusting it without a checkpoint.

### 4. Build a stability harness (strongest)

Wrap the full agent runtime in a harness that enforces stability invariants:

```python
class StabilityHarness:
    """Enforces stability invariants across agent runs."""

    def __init__(self, agent: Agent, stability_config: StabilityConfig):
        self.agent = agent
        self.config = stability_config

    def run(self, task: Task) -> RunResult:
        # Pin model + temperature for reproducibility
        with pinned_model(self.config.model, temperature=0.0):
            results = [self.agent.execute(task) for _ in range(self.config.n_trials)]

        consistency = compute_consistency(results)
        behavior_entropy = compute_behavior_entropy(results)

        if consistency < self.config.min_consistency:
            raise StabilityViolation(
                f"Consistency {consistency:.0%} below threshold "
                f"{self.config.min_consistency:.0%}"
            )

        # Use majority-vote output as canonical result
        canonical = majority_vote_output(results)
        return RunResult(output=canonical, evidence=results, stats={
            "consistency": consistency,
            "behavioral_entropy": behavior_entropy,
            "n_trials": len(results)
        })
```

Cost trade-off: running k trials multiplies cost by k. Use adaptive trials: 3 trials for low-stakes, 10+ for high-stakes, with early exit if consistency reaches 100% after 3 runs.

## Receipt

> Verified 2026-07-12 — τ-bench 60%→25% consistency finding sourced from The Context Lab (Feb 2026) "Non-Determinism Problem" article, referencing τ-bench research on multi-trial agent consistency. BFCL 3-7% per-call tool failure rate and 23% compound task failure sourced from AgentMarketCap (Apr 2026) "Tool-Call Hallucination Plateau" article. 40% schema validation catch rate sourced from BFCL published findings on argument mismatch detection. Temporal $5B valuation and 9.1T action executions sourced from Zylos Research (Feb 2026). Receipt pending on: (1) empirical consistency rates for specific task types, (2) majority-vote output fidelity measurements across domains.

## See also

- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — session-level determinism and trace auditing
- [S-116 · Output Determinism Testing](s116-output-determinism-testing.md) — testing the determinism property of specific prompts
- [S-1014 · Evaluating Agents in Production](s1014-evaluating-agents-in-production-where-simplicity-beats-complexity.md) — the evaluation mechanics that reveal variance
- [S-085 · The Eval Estimator Spectrum](s085-the-eval-estimator-spectrum-why-97-is-really-34.md) — why pass@1 misleads and pass@k matters
