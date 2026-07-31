# S-1926 · The Crash That Wasn't Stack — When Your Agent Fails Without Raising an Exception

Your agent has been running for 35 minutes. It hasn't errored out. It also hasn't done anything useful. This is the failure mode that no exception handler catches — and it accounts for a large share of why Gartner predicts over 40% of agentic AI projects will be cancelled by end of 2027.

## Forces

- **Agents fail ambiguously, not noisily.** Traditional software raises exceptions. Agents loop silently, drift from their goal, accumulate corrupted context, or produce confident nonsense — all without throwing a single error.
- **The retry instinct is wrong.** In conventional systems, "it failed, retry" is the answer. In agents, retrying without fixing the underlying cause amplifies the damage — you burn more tokens chasing the same broken reasoning path.
- **Durability costs are invisible until they aren't.** A crash during step 4 of 8 loses all progress. Teams discover this when a long-running research agent dies at 3am and someone has to restart it by hand.
- **Specification and coordination failures dwarf code bugs.** Galileo Research (2025) found that in multi-agent systems, specification failures account for ~42% of failures, coordination breakdowns for ~37%, and pure verification gaps for ~21%. Code-level exceptions are a minority.
- **The cost of silence is high.** An agent that fails loudly — explicit error, stack trace — gets fixed. An agent that loops for 35 minutes burning tokens, or approves a bad image because it optimized for "workflow complete," quietly eats budget and trust.

## The Move

Build failure handling into the execution layer, not the agent logic. Five patterns work together as a stack:

1. **Hard termination guards (enforced in code, not prompts).** Set `recursion_limit` in LangGraph (default 25). Add a step budget counter. Track no-progress iterations — if the last N tool calls returned empty or equivalent results, stop. The agent should never reason its way out of an infinite loop; the infrastructure must enforce the ceiling.

2. **Idempotency + structured error feedback as a prerequisite.** Every tool must return structured output (Pydantic/Zod validated). If a tool call fails, the error response tells the model *what* went wrong and *why*, not just "tool error." Idempotency keys on stateful operations ensure retries don't duplicate side effects — a retry that re-sends an email is not a retry, it's a bug.

3. **Checkpoint-and-resume for long-running workflows.** Persist state at defined boundaries (tool call completion, mid-run human review). On crash, resume from the last checkpoint rather than re-executing from scratch. LangGraph's built-in checkpointers handle this at the graph level; Temporal handles it at the infrastructure level and can wait days for human approval at a breakpoint at no cost.

4. **Durable execution as the execution substrate.** Move from "agent loop in a Python process that can die" to "agent workflow on Temporal/LangGraph + Temporal plugin." When the process crashes, Temporal re-executes only from the last checkpoint. OpenAI, Cursor, Lovable, Block, and Abridge all run agent workloads on Temporal in production.

5. **Tiered escalation — know when to stop.** Distinguish transient failures (retry with backoff) from terminal failures (hard stop, surface to human). Escalation queues route unresolved tasks to human review. The guardrail: if an agent has retried N times on the same step, escalate rather than retry again with the same context.

## Evidence

- **Engineering post — Anthropic:** "Agents fail in more complex ways: partial progress (completes steps 1–4 of 8 then fails — without recovery you lose all progress), ambiguous state (tool called but response malformed — did the action happen?), cascading failure (slow API causes timeout, agent retries aggressively, rate limit triggers, whole queue backs up)." — [Anthropic Engineering — Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Durable execution — Temporal:** "LangGraph and Temporal do different jobs. LangGraph defines what your agent does. Temporal handles recovery, human review, and long-running work. When the process crashes, Temporal re-executes only from the last checkpoint." Temporal now has a LangGraph plugin (public preview, July 2026) that makes this a drop-in integration. — [Temporal Engineering Blog](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution)
- **Failure taxonomy — Galileo Research 2025 (cited in Zylos Research):** In multi-agent production deployments, specification failures account for ~42% of failures, coordination breakdowns for ~37%, and verification gaps for ~21%. A separate Microsoft 2025 whitepaper identifies six agent-specific failure categories: tool misuse, context loss, goal drift, retry loops, cascading multi-agent errors, and silent quality degradation. — [Zylos Research — AI Agent Self-Healing and Failure Recovery (2026)](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)
- **GitHub library — hamley241/agent-reliability-patterns:** "Traditional circuit breakers catch network failures — but they can't catch reasoning failures. Your AI agent just burned through $47 worth of tokens chasing its own tail." Library implements reasoning circuit breakers that detect confidence degradation and hallucination spirals. — [GitHub — agent-reliability-patterns](https://github.com/hamley241/agent-reliability-patterns)

## Gotchas

- **Don't rely on prompts for termination discipline.** An agent told "don't loop forever" will eventually loop forever. Hard limits in code (`recursion_limit`, step budget, no-progress counter) enforce termination regardless of what the model decides to do.
- **Retries without idempotency amplify failures.** If a tool call sends an email and fails before you get a response, retrying with the same idempotency key re-sends the email. Design for idempotent operations *before* you add retry logic, not after.
- **Context accumulation causes silent failure.** When tool call results accumulate in context until they truncate or cause the model to halt, the agent doesn't crash — it just starts producing worse output. Use sliding-window summarization and explicit task-closure markers, not just max-token limits.
- **The two-layer problem.** Framework choice isn't either/or: LangGraph defines agent logic; Temporal handles durability. Teams that pick one and try to hand-roll the other's responsibilities end up with gaps in both. The pattern is to use both, or an equivalent stack (LangGraph + Inngest, LangGraph + Restate, etc.).
- **Monitor for silence, not just errors.** The 35-minute silent loop produces zero exceptions but costs real money. Set up token-budget alerts and step-count alerts — not just error rate dashboards.
