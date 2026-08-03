# S-2092 · The Verifier Tax Stack: When Your Safety Enforcement Costs More Than the Unsafe Actions It Prevents

Runtime safety enforcement is supposed to make agents safer. The evidence says otherwise — at least at production scale. Across τ-bench evaluations on Airline and Retail domains, adding a verifier to a tool-using agent imposes a consistent 2.0–2.8× token overhead and a persistent drop in end-to-end task success rate. The overhead compounds with conversation depth. The safety improvement rarely compensates. You are paying the verifier tax without collecting the safety benefit — and most teams don't know the bill exists.

## Forces

- **Verification overhead is horizon-dependent.** Safety enforcement adds latency and compute on every step. At short horizons (under ~15 turns), this overhead is manageable and the safety benefit exceeds the cost. Beyond 15–30 turns, the overhead accumulates faster than the safety benefit. The verifier becomes the bottleneck.
- **Blocking an unsafe action is not the same as completing the task safely.** A verifier that intercepts a dangerous API call prevents harm but also terminates the task. If the task was on a critical path, you've traded an unsafe outcome for a failed outcome. Neither is success.
- **The verifier fails in ways the agent cannot recover from.** False negatives (unsafe actions that pass the verifier) are the obvious failure mode. False positives (safe actions blocked by the verifier) are the silent one — they look like agent errors, trigger retry loops, and compound token costs without improving safety.
- **Safety enforcement tooling was built for single-turn models, not multi-step agents.** Early guardrail products inspect a model's input and output. Agentic systems add a loop: model → tool → observation → model. Each loop iteration is a potential safety enforcement point, and each enforcement point adds overhead. The product wasn't designed for this topology.

## The move

### The three-tier verification stack

Rather than applying uniform verification, route tasks by horizon and consequence severity:

**Tier 1 — Baseline Tool-Calling (short-horizon, low-severity)**
No internal mediation. The model calls tools directly. Appropriate for: sub-15-turn tasks, low-stakes tools (search, read-only APIs), environments where tool errors are self-correcting.

**Tier 2 — Planning-Integrated TRIAD (medium-horizon, medium-severity)**
Add a Planner + Actor + Verifier with a block-and-revise loop. When the verifier flags an action, the planner generates an alternative. Appropriate for: 15–30 turn tasks, medium-stakes tools (database writes, user-facing notifications). Budget: 1–2 revision cycles before escalating.

**Tier 3 — Policy-Mediated with Abort Fallback (long-horizon, high-severity)**
TRIAD-SAFETY architecture: policy enforcement on every tool call, but with a hard abort on verifier failure rather than retry. If the verifier cannot confirm safety, the action is blocked and the task terminates. Appropriate for: 30+ turn tasks, high-stakes tools (financial transactions, PII access, production deployments).

### The horizon router

```python
def route_to_tier(task_estimate: int, tool_severity: str) -> int:
    """
    Route a task to its verification tier.
    task_estimate: expected number of turns
    tool_severity: 'low' | 'medium' | 'high'
    """
    if tool_severity == 'high':
        return 3  # Always policy-mediate, always abort on verifier failure
    if task_estimate <= 15:
        return 1  # Baseline: let the model drive
    if task_estimate <= 30:
        return 2  # TRIAD: plan + act + verify, 1-2 revisions max
    return 3  # Long horizon: conservatively mediate, abort on uncertainty
```

### Treat verifier failure as fatal, not retryable

The most expensive pattern in verified agentic systems is the retry-on-verifier-failure loop. When a verifier blocks an action and the agent re-attempts with modified parameters, the verifier re-evaluates and re-blocks with high probability — generating overhead without safety improvement. Counter-intuitively, **aborting immediately on a verifier rejection is more cost-efficient than retrying**.

### Measure the tax, not just safety outcomes

Add instrumentation for:
- `verifier_token_ratio`: tokens spent on verification / total tokens
- `verifier_block_rate`: percentage of tool calls blocked
- `verifier_retry_loops`: how often blocked actions trigger retry
- `horizon_success_curve`: task success rate binned by conversation depth

The token ratio reveals whether your verification is cheap or expensive. The block rate tells you if the verifier is calibrated. The retry loop count tells you if your retry policy is compounding the overhead.

### The Safety-Capability Gap threshold

Research (Sah et al., ACM CAIS 2026) identifies the Safety-Capability Gap as the interaction horizon beyond which safety enforcement dominates and degrades task success. For GPT-OSS-20B and GLM-4-9B on τ-bench, this threshold is 15–30 turns depending on domain complexity. **Below the threshold: verification pays for itself in prevented harm. Above it: verification is a net cost in both tokens and success rate.**

## Receipt

> Verified 2026-08-03 — Sah et al., "The Verifier Tax: Horizon Dependent Safety–Success Tradeoffs in Tool Using LLM Agents," ACM Conference on AI and Agentic Systems (CAIS '26), San Jose CA. τ-bench (Airline + Retail), GPT-OSS-20B and GLM-4-9B. TRIAD-SAFETY vs baseline: 2.0–2.8× token inflation across all model×domain settings. Horizon-dependent Safety-Capability Gap confirmed at 15–30 turns.

## See also

- [S-1000 · The Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — the governance layer that safety enforcement lives inside
- [S-2091 · The Evaluation Stack](s2091-the-evaluation-stack-when-your-pass1-is-green-but-production-is-on-fire.md) — lab vs. production divergence; the verifier tax is a specific case of harness overhead inflating real-world performance
- [S-2087 · The MCP Fleet Resilience Stack](s2087-the-mcp-fleet-resilience-stack-when-your-mcp-server-works-for-one-agent-and-breaks-for-one-hundred.md) — the infrastructure layer; a verifier is itself a component that can fail and cascade
