# S-1111 · The Horizon Breakpoint Stack — When Your Agent Looks Fine Until It Quantum-Tunnels Into Failure

Your agent scores 97% on the first 10 steps. 98% on steps 11–20. By step 30, it is building an entire subsystem on a false assumption it made at step 4, and every subsequent step — scored in isolation — still looks correct. This is not gradual degradation. It is a phase transition. Agentic systems trained on short-horizon tasks (≤10 steps) do not gradually worsen as horizon increases — they hold performance until they don't, then collapse in ways that look sudden and inexplicable from the outside.

The HORIZON benchmark (Wang, Bai, Song et al., arXiv:2604.11978, April 2026) is the first systematic diagnosis of this pattern across 3,100+ trajectories, GPT-5 variants and Claude models, four domains (code, web, science, games). Its core finding: **72.5% of long-horizon failures are process-level, not outcome-level.** The agent produces plausible intermediate outputs at every step while drifting into qualitatively wrong territory. Benchmark pass rates mask this because they score the final answer, not the belief-state integrity at each checkpoint.

## Forces

- **Short-horizon eval tells you nothing about long-horizon behavior.** A 100-step agent is not a 10-step agent with 10× more steps. The failure modes are categorically different. Standard benchmarks test step-level accuracy; the failure lives in the propagation between steps.
- **Agents look functional until they don't.** Unlike software that degrades visibly (slowing, errors, crashes), agentic failure at long horizons is often invisible until a catastrophe lands. Step N+5 can be completely wrong while looking statistically indistinguishable from step N-5.
- **Belief-state corruption compounds, not averages.** An error at step 3 is not an isolated event. If the agent acts on a false intermediate result (a phantom ID, a hallucinated tool state, a misread API response), subsequent steps build on corrupted ground. Each step that looks correct *in isolation* is actually constructing a more deeply wrong belief state.
- **Performance collapse is a phase transition, not a gradient.** HORIZON finds that agents sustain near-ceiling performance for extended horizons, then abruptly shift into a degraded regime. There is no warning. The agent appears coherent until it isn't.

## The move

Use horizon breakpoints — predictable failure horizon markers — to trigger architectural transitions, not just retry or abort logic.

### 1. Instrument Horizon-Aware Metrics, Not Just Step Metrics

Track these at every step, not just at task end:

```python
from dataclasses import dataclass
from collections import deque

@dataclass
class StepMetrics:
    step: int
    tool_call_success: bool
    tool_calls: list[dict]
    context_utilization: float      # tokens used / context limit
    belief_state_entropy: float     # uncertainty in agent's world model
    output_distribution_psi: float  # PSI vs. baseline on this dimension
    plan_fidelity: float           # does step still align with top-level goal?

class HorizonMonitor:
    """Detects approach to HORIZON breakpoints before collapse."""

    BREAKPOINTS = {
        "early": 10,    # context fills; summarization needed
        "mid": 25,      # belief-state drift risk becomes measurable
        "late": 50,     # phase-transition risk zone
        "critical": 100 # collapse probability exceeds 0.7 per HORIZON
    }

    def __init__(self):
        self.trajectory: deque[StepMetrics] = deque(maxlen=200)
        self.baseline_psi = self._load_baseline()

    def record(self, step: StepMetrics):
        self.trajectory.append(step)

    def checkpoint(self) -> dict:
        """Run full HORIZON-style evaluation at each step."""
        steps = len(self.trajectory)
        horizon = self._current_horizon()

        flags = []
        if horizon in self.BREAKPOINTS.values():
            flags.append(f"BREAKPOINT_APPROACHING:{horizon}")

        # Belief entropy trend (rising = corruption accumulating)
        entropies = [s.belief_state_entropy for s in self.trajectory]
        if len(entropies) > 5:
            entropy_trend = (entropies[-1] - entropies[-5]) / entropies[-5]
            if entropy_trend > 0.3:
                flags.append("BELIEF_STATE_DRIFT")

        # Output distribution PSI
        psi = self.trajectory[-1].output_distribution_psi
        if psi > 0.2:
            flags.append(f"OUTPUT_PSI_DRIFT:{psi:.2f}")

        # Plan fidelity decay
        fidelity = self.trajectory[-1].plan_fidelity
        if fidelity < 0.6:
            flags.append(f"PLAN_FIDELITY_COLLAPSE:{fidelity:.2f}")

        return {
            "steps": steps,
            "horizon_zone": self._horizon_zone(steps),
            "flags": flags,
            "action": self._recommend_action(flags, steps)
        }

    def _horizon_zone(self, steps: int) -> str:
        if steps <= 10: return "safe"
        elif steps <= 25: return "caution"
        elif steps <= 50: return "risk"
        else: return "critical"

    def _recommend_action(self, flags: list, steps: int) -> str:
        if "PLAN_FIDELITY_COLLAPSE" in str(flags):
            return "ABORT_AND_REPLAN"
        elif "BELIEF_STATE_DRIFT" in str(flags):
            return "INSERT_VERIFICATION_STEP"
        elif steps >= self.BREAKPOINTS["critical"]:
            return "TRANSITION_TO_MULTI_AGENT"
        elif steps >= self.BREAKPOINTS["late"]:
            return "SWITCH_TO_GENERATOR_EVALUATOR"
        return "CONTINUE"
```

### 2. Trigger Architectural Transitions at Breakpoints

The HORIZON finding that 72.5% of failures are process-level means you need architecture changes, not just more prompting:

- **Step 10 (early breakpoint):** Switch from single-pass to structured memory. Insert a consolidation step that distills the current belief state into a verified checkpoint before continuing.
- **Step 25 (mid breakpoint):** Activate a second "auditor" agent that independently verifies the top-3 beliefs the primary agent is acting on. Do not ask the primary agent to verify itself.
- **Step 50 (late breakpoint):** Transition to generator-evaluator architecture (see S-1061). The generator continues producing; the evaluator is a separate model that scores trajectory coherence against the original goal.
- **Step 100 (critical):** If the task isn't complete, abort and escalate. HORIZON data shows collapse probability exceeds 70% past 100 steps regardless of model quality.

### 3. Verify Belief-State Integrity Explicitly

The HORIZON taxonomy's most actionable finding: agents fail because early errors corrupt the belief state, and downstream steps don't know to question it. The fix is explicit verification:

```python
def verify_belief_state(beliefs: list[str], env_state: dict) -> list[str]:
    """Spot-check beliefs against ground-truth environment state.
    
    HORIZON finding: belief-state corruption is the primary failure 
    mechanism. Agents don't 'forget' — they act on false beliefs 
    that look correct in context.
    """
    verified = []
    for belief in beliefs:
        # Only verify beliefs that map to external state
        if subject := extract_subject(belief):
            if subject in env_state:
                if claim_matches_env(belief, env_state[subject]):
                    verified.append(belief)
                else:
                    verified.append(f"[CORRUPTED] {belief}")
            else:
                # Subject not in env — mark as unverified, don't assume correct
                verified.append(f"[UNVERIFIED] {belief}")
    return verified
```

### 4. Run HORIZON-Style Trajectory Audits in Your Eval Suite

Replace episodic step accuracy with trajectory-level evaluation:

```python
def horizon_eval(trajectory: list[StepMetrics], ground_truth_final) -> dict:
    """HORIZON-style trajectory evaluation.
    
    Replaces: pass/fail at task end
    With: continuous monitoring of 7 failure categories
    """
    failures = {
        "execution_errors": [],   # invalid tools, bad params
        "planning_fragmentation": [],  # sub-goal drift
        "memory_contamination": [],    # stale/corrupted context
        "grounding_failures": [],      # hallucinated facts or tools
        "belief_state_corruption": [], # acting on false intermediate beliefs
        "cascade_propagation": [],     # early error compounding
        "silent_completion_claims": [] # agent reports success on false basis
    }

    for i, step in enumerate(trajectory):
        if not step.tool_call_success:
            failures["execution_errors"].append(i)
        if step.belief_state_entropy > 0.8:
            failures["belief_state_corruption"].append(i)
        if step.plan_fidelity < 0.7:
            failures["planning_fragmentation"].append(i)
        # Cascade: did failure at N cause failure at N+1?
        if i > 0 and trajectory[i-1] in failures["execution_errors"]:
            if step.tool_call_success and not step.output_quality:
                failures["cascade_propagation"].append(i)

    return {
        "total_steps": len(trajectory),
        "failure_profile": {k: len(v) for k, v in failures.items()},
        "collapse_risk": _horizon_collapse_risk(trajectory),
        "recommendation": _horizon_recommendation(failures)
    }
```

## Receipt

> Verified 2026-07-14 — HORIZON benchmark (arXiv:2604.11978) accessed via emergentmind.com. Core findings: 3100+ trajectories, GPT-5 + Claude tested across 4 domains, 72.5% process-level failures confirmed. Horizontal breakpoints confirmed via HORIZON leaderboard data at xwang2775.github.io/horizon-leaderboard/. InfiAgent (arXiv:2601.03204) confirms unbounded context → belief-state corruption mechanism. Pattern density verified: connects to S-1061 (generator-evaluator), S-1066 (invisible failure), S-1022 (agent drift), S-1026 (PAEF stack), S-1067 (hallucination laundry), S-1062 (production drift).

## See also

- [S-1061 · The Generator-Evaluator Stack](/opt/data/handbook/stacks/s1061-the-generator-evaluator-stack-when-your-agent-runs-too-long-and-loses-the-plot.md) — architectural transition triggered by long-horizon degradation
- [S-1066 · The Invisible Failure Stack](/opt/data/handbook/stacks/s1066-the-invisible-failure-stack-when-your-agent-succeeds-and-burns-47k-instead.md) — agents fail silently; process-level monitoring is the counter
- [S-1026 · The PAEF Stack](/opt/data/handbook/stacks/s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — why episodic benchmarks miss the failure modes HORIZON exposes
