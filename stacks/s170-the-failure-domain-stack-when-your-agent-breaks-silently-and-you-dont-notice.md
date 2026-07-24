# S-170 · The Failure Domain Stack — When Your Agent Breaks Silently and You Don't Notice

Your agent has been failing for three hours. The logs show HTTP 200. The final answer looks plausible. There is no stack trace — only a wrong answer that a human won't catch until a customer reports it. This is the stack for making agent failures visible, recoverable, and survivable: a failure-handling architecture that assumes breakage as the default state and treats reliability as an engineering problem, not a model problem.

## Forces

- **Agents fail non-deterministically, unlike traditional software.** A prompt that works once may fail the next time due to model drift, token limits, or hallucinated tool arguments — and the failure often returns HTTP 200 with a confident wrong answer.
- **Context rot is invisible; exhaustion has a signal.** The model doesn't crash when context degrades — it quietly produces worse outputs. Hard exhaustion (API rejection) is clean and handleable. Drift is neither.
- **Retry is not always the right recovery.** The instinct to retry on failure is correct for transient errors but catastrophic for cascading loops, deadlocks, or agents that are in a reasoning spiral — retrying without changing the approach multiplies cost and extends the failure window.
- **Autonomy and safety are in tension.** The more authority you give an agent to self-correct, the more damage it can do before human intervention is possible. The less authority, the less useful it becomes.
- **Specification failures dominate multi-agent breakdowns.** 42% of failures in multi-agent systems stem from goal misalignment or ambiguous task definitions, not from tool or model errors — making correct specification as important as error handling code.

## The Move

Build a layered failure architecture: classify failures by recoverability, then apply the right response at each layer. This means circuit breakers at the tool-call level, context compaction at the memory level, token budgets at the resource level, and explicit escalation paths at the agent-coordination level.

### Circuit Breaker on Tool Calls
- Wrap tool invocations in a circuit breaker pattern: after N consecutive failures, stop attempting the tool and route to a fallback (cached result, degraded mode, or human-in-the-loop alert).
- The agent should receive the breaker state as a tool result, not silently retry. A `{ "error": "tool-circuit-open", "fallback": "use_cache" }` response is interpretable; a silent retry loop is not.

### Deadlock Prevention via Resource Locking
- Multi-agent systems create classical wait-for cycles when agents hold shared resources (memory-write locks, tool access) while waiting for each other.
- Implement timeout-based lock acquisition with automatic release. If Agent A holds "memory-write" for more than 30 seconds, release it and retry.
- Supervisor tree pattern: a parent agent monitors child agents and can kill/restart a stuck child without cascading into a full system stop.

### Token Budget as Failure Prevention, Not Just Cost Control
- Treat every token as a constrained resource. Set hard budget limits per task turn (e.g., 4,096 tokens for reasoning, 8,192 for tool outputs). When a budget is consumed, trigger compaction — summarize the conversation, prune tool-result history — before the next LLM call.
- Budget exhaustion before compaction should escalate, not truncate silently. A log entry and an alert are better than a truncated context that produces confident nonsense.

### Idempotency Guards on Side Effects
- Any tool call that creates state (write, send, delete, approve) must carry an idempotency key. If the agent retries after a failure, the downstream system recognizes the retry and deduplicates it.
- Without this, a failed `send_email(to="client@example.com", body="...")` that times out silently may be sent twice when the agent retries.

### Failure Classification Routing
- **Transient** (API timeout, rate limit): retry with exponential backoff.
- **Semantic** (tool returned valid but wrong data): retry with a modified prompt or alternate tool.
- **Cascading** (agent in a loop, resource contention): stop, escalate, log the full trace.
- **Context rot** (performance degrading without hard error): trigger compaction before the next turn.

## Evidence

- **Research Synthesis:** A systematic review of 84 papers from 2023–2025 found that 83% of agent evaluations report capability metrics while only 30% consider human-centred or economic axes — meaning most teams are measuring what the agent can do, not whether it is failing safely. — [arXiv:2509.00115](https://arxiv.org/html/2509.00115v1) (Shukla, August 2025)
- **Failure Distribution:** In multi-agent systems, specification failures account for 42% of incidents, coordination breakdowns for 37%, and verification gaps for 21% — indicating that clearer task definitions and coordination protocols prevent more failures than better error handling code. — [Zylos Research: AI Agent Self-Healing and Failure Recovery (2026)](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)
- **Context Drift Severity:** GPT-4's accuracy drops from 98.1% to 64.1% based solely on the position of information in the context window — demonstrating that silent degradation from context rot is a more dangerous failure mode than hard exhaustion, which at least produces an error signal. — [Tian Pan: Context Engineering (February 2026)](https://tianpan.co/blog/2026-02-26-context-engineering-memory-compaction-tool-clearing)
- **Enterprise Pattern:** AWS's experience deploying thousands of production agents shifted the evaluation focus from endpoint accuracy to behavioral traces — because agents that produce correct answers via wrong tool sequences are net liabilities in production. — [AWS ML Blog: Evaluating AI Agents (2025)](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

## Gotchas

- **Retrying without a circuit breaker turns a single failure into a cascading incident.** A stuck agent that retries every 5 seconds for 30 minutes burns through budget and may produce 360 duplicate side-effect calls. Exponential backoff with a hard cap is the minimum.
- **Context truncation is a failure mode, not a solution.** When the context window fills, many systems silently truncate the oldest entries. The agent continues running but has lost critical information — and produces outputs that seem valid but are built on an incomplete picture.
- **Idempotency is often skipped in prototype agents.** It adds code complexity and feels unnecessary when the agent "works fine." It becomes necessary the moment you add a retry path — and by then the retry path has usually shipped to production.
- **Silent HTTP 200 with wrong content is the most dangerous failure mode.** Unlike a crash (obvious) or an error message (interpretable), a confident wrong answer passes monitoring checks that look for error codes. Route on semantic correctness, not HTTP status.
- **Human-in-the-loop escalation sounds safe but can introduce latency that defeats the agent's purpose.** Make escalation optional based on stakes: low-risk tasks (summarize, format, route) get full autonomy; high-risk tasks (send, delete, approve) require explicit confirmation before the first attempt, not after a failure.
