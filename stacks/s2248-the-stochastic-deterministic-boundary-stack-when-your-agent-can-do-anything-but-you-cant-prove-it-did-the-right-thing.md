# S-2248 · The Stochastic-Deterministic Boundary Stack

Your agent just declared success. The API returned 200. Your monitoring dashboard shows green. But the customer received the wrong data, the database is in an inconsistent state, and the agent is already moving on to the next task. Nothing errored. Everything failed. The problem isn't the model — it's the seam.

## Forces

- LLM outputs are stochastic by design. The same prompt can produce different tool calls, different parameters, different conclusions. But production systems expect deterministic inputs.
- Standard APM captures what happened structurally — spans, latency, HTTP codes — but cannot tell you whether the agent's action was semantically correct.
- The longer an agent runs autonomously, the more stochastic decisions compound. Without a boundary contract, each step propagates uncertainty downstream.
- Teams often add guardrails that validate LLM outputs against schemas (type checking, enum validation) but not against the *meaning* of the action or the *state* it should produce.
- The silence of a successful-looking failure is the most dangerous failure mode: no alerts fire, no logs scream, the agent believes it succeeded, and humans trust the dashboard.

## The move

The **Stochastic-Deterministic Boundary (SDB)** is a four-part contract at the seam where an LLM proposal becomes a system action:

| Part | Role | Example |
|------|------|---------|
| **Proposer** | The LLM's output — sampled from a distribution, inherently probabilistic | `"ToolCall: delete_record(id=42)"` |
| **Verifier** | A deterministic check on the proposal | `id in allowed_ids AND id in current_session_scope` |
| **Commit** | The durable write or state mutation | `DELETE FROM records WHERE id = 42` |
| **Guard** | Fallback behavior when Verifier fails | Abort, surface to human, emit audit event |

The SDB enforces that **no Commit happens without a passing Verifier**. The LLM proposes; the verifier checks; only then does the deterministic system act.

### Layer 1 — Output Scope Verification

Before any tool call executes, verify the *parameters* against what the agent is permitted to touch in the current session context.

```python
def verify_tool_call(agent_context: SessionContext, tool_call: ToolCall) -> VerificationResult:
    # Check: does this tool+target exist in the agent's declared scope?
    scope = agent_context.current_scope()
    if tool_call.tool not in scope.allowed_tools:
        return VerificationResult(safe=False, reason=f"Tool {tool_call.tool} not in scope")

    # Check: does the target entity belong to this session?
    if tool_call.target_id not in scope.allowed_targets:
        return VerificationResult(safe=False, reason=f"Target {tool_call.target_id} not session-owned")

    # Check: does this action violate any declared invariants?
    for invariant in scope.invariants:
        if not invariant.holds_after(tool_call):
            return VerificationResult(safe=False, reason=f"Violates invariant: {invariant.name}")

    return VerificationResult(safe=True)


def execute_with_sdb(agent_context, tool_call):
    result = verify_tool_call(agent_context, tool_call)
    if not result.safe:
        agent_context.record_violation(tool_call, result.reason)
        agent_context.emit_guard_event(tool_call, result.reason)
        agent_context.request_human_review(tool_call)
        return None
    return tool_call.commit()
```

### Layer 2 — Outcome Verification

After a Commit succeeds at the API level, verify the *post-state* matches what the agent declared it was trying to achieve.

```python
async def verify_outcome(session: SessionContext, tool_call: ToolCall, expected_state: dict):
    """Poll or query the system-of-record to confirm the intended state was reached."""
    actual_state = await session.query_state(tool_call.target_id)
    diff = compute_diff(expected_state, actual_state)
    if diff.materially_different():
        session.record_outcome_mismatch(tool_call, diff)
        session.emit_alert(AlertLevel.HIGH, f"Agent declared success but state mismatch: {diff}")
        await session.trigger_compensation(tool_call)
    return diff.within_tolerance()


async def execute_verified(session: SessionContext, plan: AgentPlan):
    for step in plan.steps:
        result = await session.execute_with_sdb(step.tool_call)
        if result is None:  # SDB blocked
            session.abort_with_audit()
            return
        verified = await verify_outcome(session, step.tool_call, step.expected_state)
        if not verified:
            session.abort_with_audit()
            return
```

### Layer 3 — Semantic Drift Detection

Track what the agent *believes* is true versus what the system-of-record actually shows. Divergence triggers a re-grounding.

```python
class BeliefTracker:
    """Tracks the agent's declared beliefs vs. confirmed system state."""
    def __init__(self):
        self.beliefs: dict[str, Claim] = {}  # claim_id -> Claim(belief, source_step, verified)

    def record_claim(self, claim: Claim):
        self.beliefs[claim.id] = claim

    def verify_beliefs(self) -> list[Divergence]:
        divergences = []
        for claim_id, claim in self.beliefs.items():
            system_truth = self.fetch_system_truth(claim.target)
            if not claim.matches(system_truth):
                divergences.append(Divergence(claim, system_truth))
        return divergences

    def on_divergence(self, divergences: list[Divergence]):
        # Alert + re-ground the agent before continuing
        emit_divergence_alert(divergences)
        re_ground(divergences)
```

### The Invariant Catalog Pattern

Rather than verifying each action individually, declare **session-level invariants** the agent must not violate. The verifier checks all actions against the invariant catalog before any commit.

```python
class InvariantCatalog:
    """Declarative rules that constrain the agent's action space per session."""
    def __init__(self, session_type: str):
        self.invariants: list[Invariant] = self._defaults_for(session_type)

    def _defaults_for(self, session_type: str) -> list[Invariant]:
        match session_type:
            case "customer_write":
                return [
                    Invariant("no_cross_customer", lambda tc: tc.customer_id == tc.session_customer_id),
                    Invariant("deletion_requires_audit", lambda tc: tc.operation != "delete" or tc.audit_trail_exists),
                    Invariant("amounts_non_negative", lambda tc: tc.params.get("amount", 0) >= 0),
                ]
            case "code_deploy":
                return [
                    Invariant("no_production_write", lambda tc: tc.env != "production" or tc.has_production_tag),
                    Invariant("rollback_plan_exists", lambda tc: tc.rollback_plan is not None),
                ]
            case _:
                return []
```

## Receipt

> Verified 2026-08-06 — Research synthesis from ACM ICPE '26 (IBM Research: "Detecting Silent Failures in Multi-Agentic AI Trajectories," DOI 10.1145/3777911.3801104), the devstarsj.ai production architecture post (April 2026), and AgentMarketCap tool reliability analysis. The SDB framework maps directly onto the four-layer reliability stack (API Layer → Tool Call Layer → Application Layer → Outcome Layer) described across sources. Real production implementations observed in enterprise agent deployments as of Q2 2026. Core mechanism confirmed against Zylos Research June 2026 work on behavioral verification loops.

> The SDB is not theoretical — it is the missing contract that closes the gap between "the agent tried" and "the agent succeeded."

## See also

- [S-1907 · The Three-Pillar Observability Stack](stacks/s1907-the-three-pillar-observability-stack-when-your-agent-telemetry-is-deep-but-not-wide.md) — instrumentation layer for SDB signals
- [S-2235 · The Agent Evaluation Stack](stacks/s2235-the-agent-evaluation-stack-when-your-agent-passes-all-tests-and-still-fails-in-production.md) — harness design for SDB verification
- [S-2230 · The Benchmark Ceiling Stack](stacks/s2230-the-benchmark-ceiling-stack-when-your-agent-passes-all-tests-but-fails-in-production.md) — why proxy metrics miss SDB violations
- [S-2231 · The Agent Failure Handling Stack](stacks/s2231-the-agent-failure-handling-stack-when-your-agent-runs-overnight-or-wipes-production.md) — what to do when the Guard fires
