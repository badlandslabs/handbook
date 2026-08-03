# S-2057 · The Boring Stack: Agent Failure Handling That Survives Production

Your agent worked perfectly in testing. Then in production it hit a rate limit at step 3 of a multi-step workflow, threw an uncaught exception, and left your system in an undefined state. No checkpoint. No retry. No fallback. Just silence — and a broken pipeline you restart by hand.

86% of agent failures are recoverable. The difference between a demo and a production system is deliberate failure architecture, not better prompts.

## Forces

- A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time — the math punishes naive chaining
- Agents fail in shapes single-LLM calls don't: silent loops, redundant subprocesses, context overflow, and irreversible actions before human intervention
- 62% of enterprises are experimenting with agentic AI, but only 14% have production-ready implementations — failure handling is the gap
- The most common mistake is treating observability as a substitute for actual recovery infrastructure

## The Move

Build failure handling as a first-class architectural layer, not an afterthought.

**Hard caps from the start:**
- `MAX_STEPS = 12` — hard stop if the agent doesn't finish within that many turns. The single most impactful guardrail. (Rajpoot, 2026; markaicode, 2026)
- Cost cap per run (e.g., `$1 default`) — multiple HN reports document agents running for 8 hours and costing $437 before someone noticed

**Classify failures before you retry:**
- **Transient**: rate limits (HTTP 429), timeouts, DNS failures — retry with backoff
- **Tool-level**: API returns wrong schema, endpoint changed — fix the tool or switch it
- **Agent-level**: model gets stuck in a loop, context overflow — intervene programmatically
- **Catastrophic**: agent took irreversible action, corrupted state — escalate to human

**Retry with exponential backoff + jitter:**
```python
for attempt in range(max_retries):
    try:
        return call_api()
    except (RateLimitError, TimeoutError):
        sleep = (2 ** attempt) * random.uniform(0.5, 1.5)
        time.sleep(sleep)
```
Exponential backoff with jitter reduces retry storms by 60–80%. (Zylos Research, 2026)

**Circuit breakers on every external service:**
If a tool or downstream service fails N times in a row, stop calling it — prevent cascading failures and wasted spend. This emerged independently in multiple open-source projects: AgentCircuit, AgentFuse, FailWatch, and RuntimeFence all appeared on HN within months of each other. (HN "Show HN: SafeAgent", 2025)

**Checkpoint + resume for long-running workflows:**
Save agent state at defined boundaries. When the process crashes or you need to resume mid-run, pick up from the last checkpoint instead of starting over. LangGraph's built-in checkpointer handles this natively. Temporal's LangGraph plugin (public preview, July 2026) adds durable execution — crash-surviving runs, long-duration human-in-the-loop waits, and automatic retry of failed steps. (Temporal blog, 2026; Zylos Research, 2026)

**Escalation hooks for terminal failure:**
Define a confidence threshold. Below it, surface the decision to a human reviewer — queue the output, give operators a clear interface to inspect agent state, approve, reject, or correct. Human-in-the-loop is not a fallback; it is a first-class architectural component. (Wasil Zafar, Anthropic SDK guide; Operator Collective)

**Idempotency guards for side effects:**
Before any external action (API call, database write, email send), check whether it was already done. A simple idempotency key on every side-effecting tool call prevents double-sends when an agent retries. SafeAgent (HN, 2025) implements exactly-once execution guards for this specifically.

**Observability on every run:**
Log: input, steps taken, tools called + outputs, final outcome, cost, latency. Aggregate to find which agents loop most, which tools error most, which prompts cost most. This is the difference between debugging in 30 seconds and debugging all afternoon. (Orchid Trace; Rajpoot, 2026)

## Evidence

- **Blog post (Rajpoot, 2026):** Hard step cap + cost cap + per-tool retries + descriptive tool errors + whole-agent fallback to bigger model on hard failures + escalation hook + observability = "Boring. Bounded. Survivable." — [blog.rajpoot.dev](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **GitHub (vectara/awesome-agent-failures, 2025):** Community-curated failure taxonomy: Tool Hallucination, Response Hallucination, Goal Misinterpretation, Infinite Loops, Context Overflow, Rollback Hazards — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **GitHub (tanayshah11/ai-agent-error-patterns, 2025):** Four production patterns built with Trigger.dev v4: Circuit Breaker, Partial Success, Human-in-the-Loop, Graceful Degradation — [github.com/tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)
- **Blog (Zylos Research, 2026):** A 10-step pipeline at 85% step reliability = ~20% end-to-end success. Exponential backoff with jitter reduces retry storms by 60–80%. Checkpointing transforms brittle pipelines into fault-tolerant, resumable workflows. — [zylos.ai](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability/)
- **Blog (The Operator Collective, 2026):** 86% of agent failures are recoverable. Audit every external dependency. Explicit `in_progress` state in task tracking improved task completion rates. Human-in-the-loop as first-class architecture. — [theoperatorcollective.org](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Temporal blog (2026):** Temporal's LangGraph plugin (Python, public preview) adds durable execution — automatic failure recovery, long-duration human-in-the-loop waits, crash-surviving runs — without rewriting the LangGraph codebase. — [temporal.io](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution)
- **HN "Show HN: SafeAgent" (2025):** Exactly-once execution guard for AI agent side effects — prevents duplicate actions on retry. Multiple similar projects (AgentCircuit, AgentFuse, FailWatch, RuntimeFence) emerged from real developer pain with runaway agents. — [news.ycombinator.com/item?id=47294291](https://news.ycombinator.com/item?id=47294291)
- **Blog (Agentbrisk, 2026):** Specific retry logic with code examples, circuit breaker pattern, fallback model routing, graceful degradation for production AI agents. — [agentbrisk.com](https://agentbrisk.com/blog/ai-agent-error-recovery-2026/)

## Gotchas

- **Max_steps too low** — 5 is too aggressive for complex multi-tool tasks; 12–20 is the common production range. Calibrate by running your actual workflow and measuring step distribution.
- **Retry without jitter** — pure exponential backoff without random jitter causes thundering herd on shared rate limits. Always add jitter.
- **Treating observability as recovery** — logging what went wrong doesn't fix it. You need actual retry/retry/escalate mechanisms behind the logs.
- **No idempotency on side effects** — if your agent retries a database write or API call without checking if it already succeeded, you get double-charges, duplicate records, or corrupted state.
- **Checkpointing without resumable tool design** — if your tools aren't idempotent, resuming from a checkpoint can produce a different result than a clean run. Design tools to be safe to call twice.
