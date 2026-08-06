# S-2214 · The Stuck-Loop Recovery Ladder Stack — When Your Agent Is Spiraling and Nothing Stops It

Your lead-enrichment agent hits the Clearbit API at 10 req/sec in dev, silently drops to 30 req/sec in production, starts getting 429s, backs off, retries, backs off again. A second agent picks up the retry queue. They pass work back and forth for 11 days. Your billing statement arrives at $47,000. Every API call returned HTTP 200. Your monitoring dashboards showed green. The system looked healthy. It was burning cash.

This is the stuck-loop problem: your agent isn't failing, it's converging — on nothing. And the standard failure handling stack (HTTP error codes, exception handlers, retry loops) is structurally blind to it.

## Forces

- **Success-looking failures are invisible.** HTTP 200, well-formed JSON, logical responses — nothing in the normal error channel signals that the agent is looping.
- **Activity ≠ progress.** API call counts, file edits, and log volume all rise during stuck loops. An agent revising the same paragraph 800 times produces "healthy" activity metrics while making zero forward progress.
- **The obvious fix makes it worse.** Adding more retries, more agents, or more logging doesn't break the loop — it accelerates it and inflates the cost.
- **Human escalation is too heavy as a first move.** A stuck agent that would escape with a simple context hint shouldn't trigger a PagerDuty alert.

## The Move

Break the problem into two layers: **detect** that you're stuck, then **recover** by climbing an escalation ladder. These are separate disciplines — detection catches the problem, recovery escapes it.

**Detection — use a progress metric, not an activity metric:**

- Track something that must increase for legitimate progress: plan completion %, tokens toward a fixed budget, a monotonically advancing step counter on a bounded task.
- Activity proxies (API calls, edits, logs) cannot distinguish stuck from slow-but-converging — they rise in both cases.
- Fire the recovery ladder only when progress is flat across N consecutive checkpoints.

**Recovery — climb the ladder in order:**

1. **Nudge** — inject a hint about the stuck state into the next LLM call: `"You appear to be re-examining the same section. Have you completed the analysis?"` Cheap; often sufficient for a wanderer.
2. **Replan** — regenerate the plan from scratch with fresh context. Breaks a repeater by removing the stale context that was driving the loop.
3. **Reset** — restore to the last known good checkpoint and restart from there. For LangGraph agents: use a named checkpointer ID pointing to a verified-good state.
4. **Escalate** — trigger a human notification with full trajectory context (last N tool calls, state snapshot, iteration count). Do not hand off yet.
5. **Handoff** — full human takeover. This is the last resort, not the first.

**Cost guardrails — always run alongside the ladder:**

- Set a hard iteration budget per task: `max_steps=50` or `max_cost_usd=5.00`. When the budget fires, pause the agent before escalating.
- Instrument a cost accumulator that fires an alert at 10× expected cost — not after the fact when the bill arrives.
- Log the iteration count per task type in production. If the median is 8 iterations but you see 800 on a task, the loop is already running.

## Evidence

- **GetOnStack post-mortem (ZenML LLMOps Database, 2025):** 4-agent LangChain system (Analyzer + Verifier + two others) coordinating via A2A/MCP ran an infinite revision loop for 11 days — 1.8M API calls, $47,000 cost. Week 1: $127. Week 4: $18,400. Billing statement was the first alert. No iteration limit, no cost accumulator, no progress metric. — https://www.zenml.io/llmops-database/production-deployment-challenges-and-infrastructure-gaps-for-multi-agent-ai-systems
- **Stuck-Loop Recovery pattern (agentpatterns.ai, reviewed June 2026):** Documents the 5-step recovery ladder with the activity-vs-progress distinction. Progress must be monotonically increasing to distinguish from slow convergence. — https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/
- **Synapse AI Stuck Errors guide (June 2026):** Independent documentation of the same ladder — nudge → replan → reset → escalate → handoff — with implementation details for LangGraph and CrewAI. — https://ddaekeu3-cyber.github.io/synapse-ai/guide/loop-stuck-errors

## Gotchas

- **LangGraph default timeouts are too short for tool-heavy agents.** `max_execution_time` defaults can cause premature interruption on complex multi-tool calls, triggering retry loops that look like stuck loops. Recommended: `max_execution_time=120`. — https://markaicode.com/langgraph-production-agent/
- **LangGraph durability="sync" checkpoint ordering is unenforced.** Post-crash recovery can restore inconsistent state where writes from a partial superstep are restored against a checkpoint from a different superstep (open issue #8234, July 2026). If you're using Temporal + LangGraph for crash recovery, verify checkpoint atomicity explicitly. — https://github.com/langchain-ai/langgraph/issues/8234
- **The billing statement is not a monitoring tool.** By the time you see the bill, the loop has already run for days. Cost accumulation must be instrumented proactively — per-task, near-real-time, with alerting at a threshold well below the budget limit.
