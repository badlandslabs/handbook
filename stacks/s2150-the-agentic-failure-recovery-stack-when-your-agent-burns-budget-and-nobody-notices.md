# S-2150 · The Agentic Failure Recovery Stack: When Your Agent Burns Budget and Nobody Notices

Your agent is live. It runs overnight, every night, processing invoices. At 2am it hits a malformed JSON response from a third-party API. It retries. Fails. Retries again with a "fix" it hallucinated. Fails. At 6am your rate limit is exhausted and every other production system sharing that API tier goes down. The bill is $12,000. Nobody noticed until morning. This is not a hypothetical — it is the most common production failure mode for autonomous agents, and most teams have no guardrail against it.

Agents fail differently from traditional software. Traditional software fails loudly: an exception, a 500, a log line. Agents fail silently and confidently. They keep producing plausible-sounding tool calls that accomplish nothing. The cost accumulates while the monitoring dashboard shows green because the agent never crashed — it just kept running in circles.

## Forces

- **Agents fail confidently, not loudly.** A retry loop that produces 10,000 API calls looks identical to the monitoring system as a fast, successful run — if you're only tracking request count and not semantic progress.
- **Pre-emptive caps don't exist by default.** Every major agent framework and LLM SDK lets you set a total token budget, but none of them surface it at the per-step level in a way that would trigger a circuit break before the next call. The bill is already spent by the time someone looks at the dashboard.
- **Semantic drift is invisible to token counters.** The agent calling the same tool with slightly different args on every iteration will show normal token counts. A token counter won't catch it — only a semantic fingerprint can.
- **The agent cannot self-correct loop detection.** The same reasoning capability that enables autonomous behavior also enables the agent to hallucinate plausible "fixes" to failed tool calls, perpetuating the loop indefinitely. Loop detection must live outside the agent's reasoning loop.
- **Rate limit exhaustion cascades.** One runaway agent can exhaust shared rate limits and take down every other system in the same API tier — not just its own task, but unrelated services too.

## The move

Wrap the agent execution loop with a deterministic orchestration-layer circuit breaker. The circuit breaker lives outside the agent's reasoning loop — it is not the agent deciding to stop, it is the infrastructure refusing to make the next call.

### Layer 1 — Token Budget Guard

Track cumulative token spend at the orchestration layer, not the framework layer. Set a hard cap in dollars per task or per session. The key insight: the meter reports a capped value — once the cap is reached, the next call is blocked, not allowed to overspend and then reported.

```python
class TokenBudgetGuard:
    def __init__(self, max_spend_usd: float):
        self.max_spend = max_spend_usd
        self.cumulative_spend = 0.0

    def check(self, next_call_estimate_usd: float):
        if self.cumulative_spend + next_call_estimate_usd > self.max_spend:
            raise BudgetExceeded(self.cumulative_spend)
        self.cumulative_spend += next_call_estimate_usd
```

### Layer 2 — Semantic Drift Detection

Token counts don't catch the agent calling the same tool with minor arg variations. Add a semantic fingerprint: hash the normalized tool name + a normalized hash of the args. If the same fingerprint appears N times within a window, trip the breaker. This catches "I tried the same thing with slightly different args" loops that token counters miss.

From AgentCap's prevention framework: track tool call fingerprints across a rolling window. A repetition rate above threshold triggers escalation before the next call executes.

### Layer 3 — Wall-Clock Timeout

Set a maximum wall-clock duration per task. Not a model timeout — an orchestration-level timeout that kills the entire agent loop after N minutes regardless of internal state. This catches slow drifts that neither token counters nor semantic fingerprinting catch (e.g., the agent making progress but at a glacial pace burning tokens on every step).

### Layer 4 — Rate Limit Circuit Breaker

Track API error codes at the orchestration layer, not the tool layer. A 429 from the LLM provider or a downstream API is a signal to back off and escalate, not retry blindly. Implement exponential backoff with a maximum retry count. After N consecutive failures, route to a human-in-the-loop queue — do not retry.

### Layer 5 — Silent Escalation Path

When any of the above breakers trip, do not just log and continue. Route to a dead-letter queue or human review. The event should surface in PagerDuty or Slack immediately, not sit in a log file nobody reads until Monday.

## Evidence

- **DEV Community — Case Study:** A team running autonomous customer support agents encountered a malformed JSON response from a third-party API. The agent entered a blind retry loop, hallucinated fixes that failed repeatedly, executed thousands of requests per minute, and exhausted global LLM rate limits — taking down every production system sharing that API tier. Financial impact: enterprise AI deployments averaging $45,000–$250,000 in first-year implementation costs hemorrhage monthly API budgets over a single weekend due to runaway agent detection failures. — [Cascading Agent Collapse — DEV Community](https://dev.to/jarendev/cascading-agent-collapse-how-a-single-runaway-llm-loop-takes-down-your-entire-production-1om8)

- **GitHub — Open Source Framework:** The `runaway-tool-loop` repository (MIT license, 2026) catalogs production post-mortems and categorizes the two bugs every high-star agent ships: (1) the agent retries the same failing action with the same args because nothing fingerprints "I already tried this," and (2) silent token/dollar burn with no pre-emptive cap. The proposed solution: a deterministic circuit breaker at the orchestration layer that blocks the next call before it executes. — [runaway-tool-loop — GitHub](https://github.com/rohitsalesforce132/runaway-tool-loop)

- **HN Show — Product Launch:** A developer lost $200 to an agent loop and built per-tool AI budget controls as a product (Lava). The insight: per-tool spend limits are more actionable than per-session limits because a loop typically concentrates spend in one or two tools. Surfacing spend at the tool level makes anomalies visible before the budget is exhausted. — [Show HN: Per-Tool AI Budget Controls — Hacker News](https://news.ycombinator.com/item?id=46991656)

- **AgentOps Survey (2025):** Cleanlab's production survey found that only 5% of respondents have AI agents live in production — primarily because of reliability concerns. Of those with agents in production, fewer than 1 in 3 are satisfied with observability and guardrail solutions. 63% plan to improve observability in the next year. — [AI Agents in Production 2025 — Cleanlab](https://cleanlab.ai/ai-agents-in-production-2025/)

## Gotchas

- **LLM retries are not circuit breakers.** The model's built-in retry logic is inside the failure loop — it doesn't know it's making things worse. The breaker must live outside the model's reasoning.
- **Silent failure looks like success.** If your monitoring tracks only request count and final output, a loop that produced 10,000 wasted calls looks identical to a fast, correct run. You need step-level observability, not just session-level summary.
- **Pre-emptive caps beat post-hoc alerts.** Alerting after the budget is exhausted is too late. The circuit breaker must block the next call, not notify after the fact.
- **Version pinning doesn't prevent loops.** Even if your agent, framework, and API versions are all pinned, a malformed response from a live third-party API will still trigger a retry loop. The breaker must handle external failures, not just internal ones.
- **The human escalation path is not optional.** If your circuit breaker trips and the task simply fails silently, you've traded a budget problem for a reliability problem. Dead-letter queues and human review must be wired in from day one.
