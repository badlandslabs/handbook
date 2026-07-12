# S-984 · The First-Attempt Architecture — When <25% Is Not a Model Problem

Your agent completes fewer than 25% of real-world tasks on the first attempt (APEX-Agents benchmark, 2026). You upgrade to the latest frontier model. The number barely moves. This is the wrong diagnosis.

The <25% first-attempt rate is overwhelmingly an architectural failure, not a model failure. Frontier models score 80-94% on SWE-bench and GAIA benchmarks — and still manage fewer than one in four single-pass completions in production. The gap lives in the gap between what the agent assumes and what's actually true: environment state the agent didn't read, outcomes the agent didn't verify, and decisions the agent made while uncertain rather than deferring.

The First-Attempt Architecture treats single-pass task completion as an explicit design target — not "ship and hope," not "retry until it works," but a layered system of grounding, verification, and calibrated deferral that moves the success rate up before the model even runs.

## Forces

- **First-attempt failures are grounding failures, not reasoning failures.** An agent that calls the wrong tool or uses stale data is not failing because it can't reason — it's failing because it acted on an assumption instead of a read. Most first-attempt failures would be caught by reading the state before writing to it.

- **Retry loops are expensive and invisible.** Each failed attempt costs token budget, latency, and often compounding errors — a wrong assumption in attempt one propagates into a wrong correction in attempt two. A 10-step chain at 90% per-step accuracy produces 35% overall accuracy; four retries don't fix a bad first assumption.

- **Confidence scores don't drive behavior.** Agents report uncertainty verbally ("I'm not confident about...") but act with the same certainty regardless. The verbalized confidence decouples from the decision — S-807 covers this gap. Without a behavioral response to uncertainty, escalation only happens after the failure has already occurred.

- **Verification is structurally different from retry.** Re-executing the same action with the same assumptions produces the same result. Effective verification re-reads state after action and gates continuation on confirmed outcomes — not on confident narratives.

- **The benchmark-to-production gap is a test-time distribution gap.** Agents trained on clean, pre-verified trajectories fail on noisy, state-dependent tasks where the ground truth is dynamic. No model upgrade closes this without architectural support.

## The move

### 1. Pre-action grounding: read before write

The single highest-leverage intervention. Before any state-modifying action, the agent reads the current state of the target system explicitly.

```
# Ground the action in confirmed state, not assumed state
async def ground_before_act(agent, action, target):
    # Pre-read: confirm current state before modifying
    snapshot = await target.snapshot()          # DB record, API response, file state
    grounded_action = {
        **action,
        "assumptions": snapshot,               # Embed confirmed state into reasoning
        "precondition_check": snapshot.is_valid
    }
    return agent.execute(grounded_action)
```

This is not re-reading the prompt. It's re-reading the world. An agent that confirms "the user record ID 42 exists and has status=active" before sending an email is architecturally different from one that assumes it.

### 2. Post-action verification gates

After any consequential action (write, send, merge, delete), verify the outcome before reporting completion.

```
# Verify, then claim
async def verify_then_complete(agent, tool_call_id, invariant):
    result = await agent.await_tool_result(tool_call_id)
    confirmed = await invariant.check(result)  # Read-back from the actual system
    if not confirmed:
        agent.escalate(f"Post-action verification failed: {invariant.description}")
        return {"status": "verified_failed", "action": tool_call_id}
    return {"status": "verified_ok", "action": tool_call_id}
```

The invariant is domain-specific: "the record now has the updated email," "the file exists at the path," "the Slack message appears in the channel." This is S-928 (Phantom Completion) made structural — the verification gate exists at the architectural level, not as an agent awareness heuristic.

### 3. Uncertainty-directed deferral

When the agent's confidence drops below a threshold, route to human review instead of proceeding with best-effort action.

```
# Confidence-gated deferral
async def confidence_gated_act(agent, action):
    confidence = await agent.calibrated_confidence(action)  # Per-action, not global
    if confidence < agent.deferral_threshold:
        return agent.defer_to_human(action, reason=f"Confidence {confidence:.0%} below threshold")
    return agent.execute(action)
```

The threshold is per-action-type: file writes defer at 80% confidence; email sends defer at 90%; read-only queries proceed at 60%. These are configurable policy gates, not model behavior.

### 4. Assumed-state inventory

Track every assumption the agent makes during a session. At session end, surface any unverified assumptions as an audit record.

```
class AssumptionTracker:
    def __init__(self):
        self.assumptions = []      # {claim, source_turn, verified: bool, invalidated: bool}
    
    def record(self, claim: str, turn: int):
        self.assumptions.append({"claim": claim, "turn": turn, "verified": False})
    
    def verify(self, claim: str, outcome):
        for a in self.assumptions:
            if a["claim"] == claim:
                a["verified"] = True
                a["outcome"] = outcome
    
    def audit(self):
        unverified = [a for a in self.assumptions if not a["verified"]]
        return {"verified": len(self.assumptions) - len(unverified), 
                "unverified": unverified}
```

This produces a per-session assumption audit: how many claims did the agent make, how many were verified, which remain unverified. It feeds the Production Case Harvest Stack (S-908): unverified assumptions that caused failures become regression test seeds.

### 5. Design for first-pass, not retry coverage

Architecture that assumes retries will happen and optimizes for "good enough to retry" produces agents that fail repeatedly. Design for the first pass:

| Anti-pattern | First-Attempt Architecture |
|---|---|
| "Call the tool, if it fails retry" | Read state → verify precondition → call tool → verify outcome |
| Global confidence threshold | Per-action-type confidence thresholds with domain-specific policy |
| Best-effort escalation | Uncertainty-directed deferral before action, not after failure |
| Retry until narrative sounds right | Verified state confirmation at each consequential step |
| Assumptions invisible in trace | Assumed-state inventory as first-class trace attribute |

## Receipt

> Receipt pending — 2026-07-12

The architectural interventions above are composable patterns from published research and practitioner reports. A minimal implementation was not run in this session. The APEX-Agents benchmark figure (<25% first-attempt) comes from CyberQuickly (April 2026, citing APEX-Agents). The SWE-bench/GAIA benchmark figures come from Presenc AI (May 2026). The compounding accuracy math (90% × 10 steps = 35%) is derived from S-928's observation and is directionally validated by trajectory studies.

## See also

- [S-928 · Phantom Completion](s928-the-phantom-completion-stack-when-your-agent-says-done-but-nothing-happened.md) — Why "done" doesn't mean verified, the sibling problem
- [S-807 · The Confidence Gap](s807-the-confidence-gap-when-agents-say-i-dont-know-then-act-anyway.md) — Why verbalized confidence decouples from behavior
- [S-908 · Production Case Harvest](s908-the-production-case-harvest-stack-when-your-failing-users-are-your-best-eval-writers.md) — Converting unverified assumptions into regression tests
- [S-976 · The Verification Layer](s976-the-verification-layer-when-your-agent-cant-distinguish-right-from-almost-right.md) — The "almost right" problem and how verification gates address it
