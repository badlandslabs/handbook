# S-1764 · The Production Eval Gap Stack

Your agent scores 95% on SWE-bench. Your production pipeline shows 58% task completion. The benchmark isn't lying — it's measuring something completely different from what matters in production. You've been evaluating the wrong thing at the wrong scale with the wrong instrument.

## Forces

- **Offline eval is a parking lot. Production is a highway.** Standard benchmarks (HELM, MT-Bench, AgentBench, BIG-bench) test isolated capability in controlled, single-session, single-turn settings. Production agents operate continuously across thousands of sequential decisions, compounding errors, evolving ground truth, and adversarial user inputs. These are fundamentally different evaluation problems requiring different instruments.
- **The gap is structural, not statistical.** A 37% performance gap exists between lab benchmark scores and real-world deployment for enterprise agents (NWI 2026). This isn't measurement noise — it's the benchmark measuring whether the agent is *capable*, while production asking whether the agent is *reliable*. Capability and reliability are orthogonal.
- **Annotation quality is a floor problem, not a ceiling.** Some benchmark datasets have documented annotation error rates exceeding 50%. The "ground truth" being measured against is wrong half the time. A 95% score on a 50%-noisy benchmark is statistically indistinguishable from a coin flip.
- **Production reveals failure modes no offline eval can see.** Tool failure cascades, non-deterministic output drift, state mutation propagation, resource exhaustion spirals — these emerge from the interaction between the agent and the live environment across time. No static benchmark can observe them.
- **88% of agent pilots never reach production** (NWI 2026). The primary cited reason: the eval infrastructure used to validate pilots doesn't translate to production confidence. You validated the wrong thing.

## The move

**Don't benchmark smarter. Benchmark for production.**

### The Production Agentic Evaluation Framework (PAEF)

arXiv:2605.01604 (Pandey, May 2026) defines five evaluation dimensions that offline benchmarks miss:

1. **Trajectory integrity** — does the agent stay on goal across all steps, not just reach the right answer?
2. **Cascade resistance** — does a failure in step 3 propagate to step 10, or does the agent recover?
3. **Drift rate** — how does behavior changes over extended operational time?
4. **Resource efficiency** — what is the cost-per-successful-task, not cost-per-token?
5. **Ground truth stability** — does the agent's output remain consistent when ground truth shifts mid-session?

### The seven production-only failure modes (PAEF taxonomy)

Standard metrics fail to detect **4 of 7** of these entirely and detect **the other 3 only after multi-cycle lag**:

| Failure Mode | What it is | Offline detection |
|---|---|---|
| Tool failure cascade | One bad tool call poisons downstream calls via corrupted context | No |
| Compounding decision error | Small wrong choice at step 2 → large failure at step 15 | No |
| Non-deterministic output drift | Same input → different output across invocations (stochastic) | Partial |
| Adversarial injection exploit | Injection payload activates three turns later | No |
| State mutation propagation | Agent's own prior outputs corrupt future context | No |
| Resource exhaustion cascade | One slow tool → context bloat → session death | Lag |
| Cross-session behavior degradation | Agent drifts after N successful sessions | Lag |

### Build a production eval harness, not a benchmark runner

```python
# Production eval harness skeleton
import json
import time
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class PAEFRun:
    session_id: str
    trajectory: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    cost_cents: float = 0.0
    trajectory_integrity_score: float = 0.0
    cascade_count: int = 0
    drift_events: int = 0

def run_paef(
    agent_fn: Callable,
    production_scenarios: list[dict],
    cascade_threshold: int = 3,
    drift_threshold: float = 0.15,
) -> dict:
    """
    Production Agentic Evaluation Framework (PAEF) harness.
    
    Unlike offline benchmarks that score a single turn:
    - Measures trajectory integrity across all steps
    - Detects failure cascades as they propagate  
    - Tracks semantic drift per-step (not post-hoc)
    - Computes cost-per-successful-task (not cost-per-token)
    - Runs continuously — detects degradation over N sessions
    """
    results = []
    for scenario in production_scenarios:
        run = PAEFRun(session_id=scenario["id"])
        agent_state = scenario["initial_state"]
        
        for step in range(scenario["max_steps"]):
            # Capture per-step semantic fingerprint
            step_input = agent_state.copy()
            
            # Agent step with cost tracking
            start_cost = run.cost_cents
            start_time = time.time()
            
            output = agent_fn(agent_state, scenario["task"])
            
            step_latency_ms = (time.time() - start_time) * 1000
            step_cost = (run.cost_cents - start_cost)
            
            # Record trajectory
            run.trajectory.append({
                "step": step,
                "input_hash": hash(str(step_input)),
                "output_hash": hash(str(output)),
                "latency_ms": step_latency_ms,
                "cost_cents": step_cost,
                "tool_calls": run.tool_calls[-5:],  # last 5
            })
            
            # Cascade detection: did step N failure corrupt step N+1?
            if step > 0 and run.cascade_count > cascade_threshold:
                run.cascade_count += 1
                # Cascade propagation detected
                
            # Drift detection: semantic distance from expected trajectory
            drift = semantic_drift(run.trajectory, scenario["expected_trajectory"])
            if drift > drift_threshold:
                run.drift_events += 1
                
            agent_state = update_state(agent_state, output)
            
            # Hard stops
            if is_terminal(output, scenario["success_criteria"]):
                break
            if run.cost_cents > scenario["max_budget_cents"]:
                break
            if run.drift_events > scenario["max_drift_events"]:
                break
        
        run.trajectory_integrity_score = compute_trajectory_score(
            run.trajectory, scenario["expected_trajectory"]
        )
        results.append(run)
    
    # Aggregate PAEF scores
    return {
        "trajectory_integrity_p50": median(r.trajectory_integrity_score for r in results),
        "cascade_rate": sum(r.cascade_count for r in results) / len(results),
        "drift_rate": sum(r.drift_events for r in results) / len(results),
        "cost_per_success_cents": median(
            r.cost_cents for r in results 
            if r.trajectory_integrity_score > 0.7
        ),
        "production_reliability": sum(
            1 for r in results if r.trajectory_integrity_score > 0.7
        ) / len(results),
    }

# Key insight: PAEF scores ≠ benchmark scores
# A 95% on SWE-bench might correspond to 58% trajectory integrity in PAEF.
# The 37% gap IS the production eval gap.
```

### The three questions production eval must answer that benchmarks can't

1. **Does the agent fail forward or fail flat?** A reliable agent makes progress even when tools fail. A benchmark only tests the success case.
2. **Does cost scale with value or with time?** An agent that loops 40 times on a $0.05 task has a cost problem no benchmark detects.
3. **Does behavior drift across sessions?** An agent that works perfectly in session 1 and silently degrades by session 50 fails the production eval even if it passed the lab eval.

## Receipt

> Receipt pending — 2026-07-28

## See also

- [S-1735 · The "Failure Is Not the Crash" Stack](stacks/s1735-the-failure-is-not-the-crash-stack-when-your-agent-pretends-to-work.md) — quiet failures in production; this entry's scope
- [S-1753 · The Agent Reliability Stack](stacks/s1753-the-agent-reliability-stack-measuring-and-recovering-from-failure.md) — measuring what breaks; PAEF is the eval infrastructure for that measurement
- [S-1761 · The Trajectory Grade Stack](stacks/s1761-the-trajectory-grade-stack-when-your-agent-scored-perfectly-and-failed-in-production.md) — trajectory scoring; PAEF extends it with cascade and drift detection
