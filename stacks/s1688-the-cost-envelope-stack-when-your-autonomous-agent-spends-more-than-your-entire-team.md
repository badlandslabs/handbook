# S-1688 · The Cost Envelope Stack — When Your Autonomous Agent Spends More Than Your Entire Team

Your agent is running overnight. It found a problem, it is retrying, it is looping, it is burning tokens at $2.40 per thousand output tokens — and nobody is watching. The $47,000 bill arrives Monday morning. This is not a pricing problem. This is an architecture problem: autonomous agents optimize for task completion, not cost, and no built-in mechanism exists to make them stop.

## Forces

- **Autonomous agents have no cost stop condition.** A human reviewing a bill notices spend. An autonomous agent that hits an error retries. An agent in a loop burns tokens until a hard limit fires. None of these limits exist by default in agent frameworks.
- **Token costs compound invisibly.** Each tool call adds input tokens (the tool definition, parameters, the response). Each retry doubles the step. Each parallel agent multiplies the base rate. By the time cost becomes visible on the monthly bill, the runaway event is days old.
- **Budgets are set for chat, not agents.** A team budgeting $500/month for AI tools is assuming single-turn interactions. One autonomous agent handling a multi-step workflow generates 10–100× more tokens than the equivalent chat session.
- **Context reuse hides the meter.** Agents pass the full conversation history to every model call. Even if individual calls seem cheap, the cumulative cost of a 200-step workflow with repeated context far exceeds any single-call heuristic.
- **Retry and loop logic amplifies runaway.** Exponential backoff on tool failures, retry loops on transient errors, and recursive agent-to-agent communication all increase token consumption — often exponentially — during exactly the moments when things are going wrong.

## The move

Three layers of defense, applied before autonomy begins:

### 1. Hard cost envelope with per-step prediction

Estimate cost before each step, not after. Use the provider's pricing API or a local token-counter that runs synchronously:

```
cost_estimate = (input_tokens × input_rate) + (output_tokens × output_rate)
if cost_estimate + cumulative_cost > envelope:
    interrupt_and_escalate()
```

Set three thresholds:
- **50% envelope:** log + alert. Informational — still room to maneuver.
- **80% envelope:** warn + pause. Require operator acknowledgment to continue.
- **95% envelope:** hard stop. Do not pass Go. Return control.

### 2. Context-level budget partitioning

Split the envelope by workflow phase, not just overall. A five-step task gets roughly 20% of the envelope per phase, with the final phase getting a smaller allocation (no time for retries at step 5). This forces course-correction before the final step runs out of budget.

```python
PHASE_BUDGETS = {
    "plan":    0.30,  # 30% for decomposition and routing
    "execute": 0.50,  # 50% for tool calls and responses
    "verify":  0.15,  # 15% for output validation
    "report":  0.05,  # 5% for final summary — no room for retries
}
```

If execution exceeds its phase budget, either escalate or truncate — do not borrow from verify/report.

### 3. Continuous cost meter and real-time routing

Emit per-step token counts and cost estimates as structured log fields to your observability pipeline (Datadog, OpenTelemetry, Honeycomb). Route to:
- A live cost dashboard (per-agent, per-task)
- A PagerDuty/Slack alert when 80% threshold is breached
- An automatic escalation that hands control to a human operator

The feedback loop must close within minutes, not days.

## Variations

**Soft envelope:** warn without stopping. Good for exploratory agents where killing the run prematurely destroys value. The operator sees the cost and decides.

**Hard envelope:** stop + rollback. For agents with financial or operational consequences. Stopping is the right behavior even if the task is 90% complete — an unfinished task is cheaper than a runaway one.

**Tiered envelope by autonomy level.** Agents running at L1 (advisory) get tighter envelopes. L3 (fully autonomous, no human in loop) get the full envelope but require pre-flight budget approval. Match spend authority to autonomy level.

**Predictive envelope:** use a lightweight model to estimate the probability that the current trajectory will exceed the budget before the next step runs. Fire the 80% alert early if probability > 0.7, even if current spend is lower.

## Tradeoffs

- Hard envelopes create false negatives: an agent that is correctly solving a hard problem gets killed at 95% and produces nothing. Tune the thresholds against your actual task distribution.
- Pre-call cost estimation adds ~5–15ms latency per step from token counting. For ultra-low-latency agents, batch-estimate over the next N steps instead.
- Phase budgets prevent cross-phase borrowing, which means a slow plan phase kills execution even when execution would have been cheap. Calibrate phase allocations empirically.
- Setting envelope limits too low causes chronic early termination. Start with generous limits and narrow based on observed cost distributions.

## Receipt

> Verified 2026-07-26 — TechCrunch (June 5, 2026): Uber blew through entire 2026 AI coding budget by April. Microsoft revoked Claude Code licenses months after enabling them. AgentMarketCap (April 12, 2026): Two LangChain agents in an 11-day infinite conversation cycle ran up a $47,000 bill against a budgeted <$200/month pipeline. Zylos Research (April 12, 2026): 96% cost overrun rate for enterprise agentic deployments; achievable savings with full optimization stack: 60–80%.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — route to cheaper models before cost thresholds fire
- [S-107 · The Loop Guard Stack](s1070-the-loop-guard-stack-when-agents-run-forever.md) — loops are the primary cost amplifier; loop guards and cost envelopes are complementary
- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — the economic case for compaction before the hard envelope fires
