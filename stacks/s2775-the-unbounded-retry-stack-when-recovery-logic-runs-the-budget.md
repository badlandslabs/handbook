# S-2775 · The Unbounded Retry Stack — When Recovery Logic Runs the Budget

Your agent hits a rate limit, retries. Fails again, retries with backoff. Fails again, retries. 250,000 API calls later, you've burned the quarter's inference budget and the agent is still looping. The agent was doing exactly what you programmed — the ceiling was just missing. This is the unbounded retry problem: the failure modes that look like "reliability" are actually the ones most likely to bankrupt you.

## Forces

- **Retry logic compounds non-deterministically.** A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time. Each failure point spawns its own retry branch, multiplying cost and latency at non-linear rates.
- **Self-healing is indistinguishable from thrashing — until you measure it.** An agent that compacts context and retries looks identical to one that loops forever without instrumentation.
- **Every agent failure mode has a different correct response.** Rate limit? Back off. Tool not found? Never retry the same way. Model output malformed? Catch it at the schema layer, not the LLM layer.
- **Spec failures dominate multi-agent breakdowns.** Specification failures account for ~42% of multi-agent failures; coordination breakdowns 37%; verification gaps 21%. Most teams optimize for coordination failures while the bigger blast radius is upstream.
- **The unbounded loop is the most expensive failure mode.** It generates plausible-looking output, consumes resources, and provides zero useful result — making it invisible without explicit loop-count guards.

## The move

Set explicit, layered bounds on every failure recovery path before you ship.

**Hard caps on retry behavior:**
- Set `max_retries` per step, not per agent. A step that calls an external API gets 2 retries. A step that calls an LLM gets 0 (let the orchestration layer handle it).
- Set `max_loop_count` as a global pipeline guard — a circuit breaker that halts after N total iterations regardless of what the agent "decides" to do next.
- Set `max_cost_per_task` budgets. When the agent approaches the budget, it must either produce its best answer or escalate — it cannot retry.

**Classify failure types and route them to different handlers:**
- **Transient** (rate limit, network blip): exponential backoff with jitter, bounded retry, then escalate. Jitter reduces retry storms by 60–80% vs fixed-interval retries.
- **Structural** (tool not found, missing schema field): never retry the same way. Log the failure, halt, and surface to human — this is a bug, not bad luck.
- **Quality** (output malformed, low-confidence answer): route to a critic/recovery agent rather than retrying the original agent.
- **Oscillation** (same failure 3+ times in a row): this signals a systemic problem. Halt and alert.

**Build stateful checkpointing, not stateless retry:**
- Use LangGraph-style checkpoint/resume primitives or equivalent. When a pipeline fails at step 7, you can restart from step 7's saved state — not re-run steps 1–6.
- Idempotency guards on every side-effect operation (writes, API POSTs, DB mutations). SafeAgent's "exactly-once execution guard" pattern prevents a retried operation from running twice after a partial failure.
- Store failure history with structured metadata (step name, error type, retry count, model used, token spend) — not just logs. You need this to diagnose patterns.

**Instrument for observability before shipping:**
- Log every retry: why it happened, which step, how many total retries this pipeline has attempted.
- Track cost per task in real-time, not post-hoc.
- Use a trace system (LangSmith, or the agent-triage pattern from production traces) that can categorize failures by type and surface which failure modes dominate.
- A silent failure that costs $0.01 is fine to debug later. A silent failure that costs $800 in API calls needs an alert within the first 10 minutes.

## Evidence

- **Post-mortem:** A missing retry cap let 1,279 Claude Code sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. The agent was executing recovery logic — it just had no ceiling. — *AgentMarketCap, "Self-Healing Agent Pipelines 2026" (2026-04-10)* — https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery

- **HN discussion:** Show HN: Agent-triage — a tool for diagnosing agent failures from production traces by analyzing what went wrong, not just whether it succeeded. Built after the team couldn't distinguish "agent worked but produced wrong output" from "agent silently failed" in production. — *Hacker News, Show HN (5 months ago)* — https://news.ycombinator.com/item?id=47334775

- **Production lesson:** An open-source framework extracted from 500+ production AI agents built by GrowthX (clients include Lovable, Webflow, Airbyte) identified "orchestrating API calls that fail unpredictably" as a top-3 recurring engineering challenge. Their solution: filesystem-first, agent-friendly workflow definitions where every step has explicit bounds. — *Hacker News, Show HN (4 months ago, 40 points)* — https://news.ycombinator.com/item?id=47676157

- **Failure taxonomy:** Specification failures ~42% of multi-agent failures; coordination breakdowns ~37%; verification gaps ~21%. Exponential backoff with jitter reduces retry storms by 60–80%. A 10-step pipeline at 85% per-step reliability succeeds only ~20% of the time. — *Zylos Research, "AI Agent Self-Healing and Failure Recovery" (2026-05-06)* — https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery

- **GitHub AI system design guide:** "Agents fail in non-deterministic ways. Error handling has moved from Try-Catch blocks to Agentic Self-Correction and Stateful Rollbacks. Frameworks like LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives." — *ombharatiya/ai-system-design-guide, updated Dec 2025* — https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md

## Gotchas

- **Unbounded exponential backoff still has unbounded cost.** Backoff is good for reducing load on downstream services, but without a hard cap on total attempts, it just slows down the thrashing — it doesn't stop it.
- **"Halt and retry" is not always the right escalation.** For LLM quality failures, routing to a critic agent is cheaper and faster than retrying the original. Don't conflate transient failures with quality failures.
- **Checkpointing without idempotency is dangerous.** If you checkpoint before a write operation but retry after a partial failure, you can replay the write. Every recoverable path needs idempotency keys.
- **Instrumenting after a $5,000 incident is too late.** Budget alerts and loop counters must exist on day one, not be added during post-mortem.
