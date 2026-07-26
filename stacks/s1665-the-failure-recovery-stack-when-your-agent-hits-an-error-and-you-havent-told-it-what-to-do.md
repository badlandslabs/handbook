# S-1665 · The Failure Recovery Stack — When Your Agent Hits an Error and You Haven't Told It What to Do

Your agent hits a rate limit on step 4 of a 12-step workflow. It crashes. The conversation ends. The user has to start over and re-explain everything. There was no rollback, no recovery attempt, no partial result returned — because you treated error handling as "add some try-catches at the end." Agentic failure recovery is not exception handling. It is a separate architectural discipline, and ignoring it costs real deployments.

## Forces

- **Agent failures are non-deterministic.** A prompt that works once fails the next time due to model drift, token limits, or a hallucinated tool argument. Traditional try-catch blocks do not catch "the model decided the wrong tool" (Microsoft AI Red Team, "Taxonomy of Failure Modes in Agentic AI Systems v2.0," April 2026; COMPEL Framework, "Operational Resilience for Agentic AI," 2026).
- **State compounds the blast radius.** A failure at step 3 of a 10-step workflow leaves the system in an intermediate state — mid-write, mid-decision, mid-API call. Unlike a crashed API, there is no HTTP 500 to catch. The agent has already partially acted on bad information (COMPEL Framework, 2026).
- **Silent failures are the most dangerous.** An agent can produce confident, wrong output with zero error signal. It completes the task, reports success, and the downstream system acts on bad data. Detecting this requires proactive quality monitoring — reactive error handling is structurally blind to it (Microsoft Security Blog, June 4, 2026).
- **Recovery is 30% code and 70% expecting the unexpected.** Practitioners at miaoquai.com report that even well-architected retry logic covers only the failures you anticipated. The remaining 70% — cascading errors, corrupted state, hallucinated parameters — require graceful degradation and human fallback paths (GitHub Discussion, anthropics/anthropic-sdk-python #1341, April 2026).

## The Move

Failures are inevitable. Recovery must be architectural. The stack has five layers, from cheapest to most expensive:

### Layer 1 — Surface-Level Guards (Cheapest)

- **Iteration limits and step budgets.** Cap the maximum number of agent steps per task (commonly 20–50, tuned to your use case). This is the single most effective guard against runaway loops — it costs nothing and catches the widest range of failure modes (agentpatterns.ai, "Stuck-Loop Recovery," June 2026; DEV Community / NeuralTrust, 2026).
- **Timeout budgets per step.** Give each tool call a wall-clock timeout, not just a retry count. A search tool that hangs should not consume your full step budget waiting.
- **Return partial results on partial failure.** If step 7 of 10 fails, return what step 6 produced and a clear statement of what is missing. Partial success is better than total silence (COMPEL Framework, 2026; NVIDIA NCP-AAI exam materials, 2026).

### Layer 2 — Retry Infrastructure

- **Exponential backoff with jitter.** Start at 1s, cap at 60s, with ~30% jitter to prevent thundering-herd on shared resources. Max 3 retries. Beyond 3 retries on the same failure class, escalate — the problem is not transient (GitHub Discussion, anthropics/anthropic-sdk-python #1341, April 2026).
- **Circuit breakers per tool or service.** If a downstream API has failed 5 times in 30 seconds, stop calling it and return a graceful degradation response. Do not spend your step budget hammering a broken service (COMPEL Framework, 2026).
- **Fallback chains.** For a given task class, maintain an ordered list of approaches: primary model → smaller/faster model → rule-based heuristic → human escalation. Do not fall back on every failure — fall back only after a defined threshold.

### Layer 3 — Stateful Rollback (LangGraph / LangChain)

- **Checkpoint at every decision boundary.** LangGraph's `MemorySaver` works for local dev but loses state on any restart. Production requires `SqliteSaver` (single-process, low concurrency) or `PostgresSaver` (multi-agent, high concurrency). On crash, reload the last checkpoint and resume — the agent never knows it restarted (ActiveWizards, "LangGraph State Management: Checkpointing & Recovery," 2026; LangGraph agentic workflows blog, manutej/langgraph-agentic-workflows, 2026).
- **The rollback pattern is 3 lines.** After a failed tool call, invoke `graph.update_state()` with the previous checkpoint's `thread_id` and re-run from the last good node. This recovers a 12-step run from a bad parameter without restarting from scratch (AI Dev Day India, "Roll Back a Failing Agent in 3 Lines," May 2026).
- **Automated rollback triggers.** Configure the graph to call `update_state` automatically when a tool returns a validation error or a defined sentinel value — no human trigger needed.

### Layer 4 — Semantic Self-Correction

- **Verifier agents.** Pipe critical tool outputs through a smaller, faster verifier model that checks: "Does this output actually answer the query?" If the verifier says no, trigger self-correction as if it were a hard error. This catches hallucinated tool outputs that produce no exception (ai-system-design-guide, GitHub, 2026; ombharatiya/ai-system-design-guide).
- **Reflexion-style reflection memory.** After each failed attempt, store the error signal and the agent's self-diagnosis in a reflection log. On the next attempt, feed the reflection log into the prompt so the agent does not repeat the same mistake. This requires multiple trials but dramatically improves success on multi-step reasoning tasks (ai-system-design-guide, referencing Shinn et al., "Reflexion," 2024; Jangwook.net, "Self-Healing AI Systems," October 2025).
- **Schema validation on tool responses.** Before passing a tool output to the next agent step, validate it against the expected JSON schema. A tool returning a 200 OK with the wrong shape is a silent failure; schema validation catches it explicitly.

### Layer 5 — Human Escalation (Most Expensive, Always Required)

- **Static and dynamic interrupts.** LangGraph's `interrupts` pause the graph and wait for human input. Use static interrupts at high-stakes decision points (approve payment, send email, delete data). Use dynamic interrupts when confidence is below a threshold — a human reviews only when the agent signals uncertainty, not on every step (manutej/langgraph-agentic-workflows, 2026).
- **Context-preserving handoff.** When escalating, serialize the full agent state — conversation history, tool call log, current step, and intermediate artifacts — into a human-readable summary. A human who receives "the agent failed at step 7, here is why and what it produced so far" can make a decision in 30 seconds. A human who receives "the task failed" starts from scratch.
- **Graceful degradation is not giving up.** It is returning a structured partial result with enough context for the next actor (human or system) to continue. The goal is zero dead ends, not zero failures (COMPEL Framework, 2026).

## Evidence

- **Microsoft AI Red Team:** Taxonomy v2.0 (April 2026) documents 7 failure categories across 15 named modes, grounded in 12 months of red-team engagements. Key finding: 73% of AI agent projects fail due to reliability and failure-handling gaps. New v2.0 failure modes include MCP/plugin abuse (99 MCP-related CVEs published in 2025), Computer Use Agent visual attacks, and supply-chain compromise via natural-language tool descriptions — all of which require recovery strategies beyond traditional exception handling. — [Taxonomy v2.0 PDF](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/bade/documents/products-and-services/en-us/security/Taxonomy-of-Failure-Modes-in-Agentic-AI-Systems-v2-0.pdf); [Microsoft Security Blog post](https://www.microsoft.com/en-us/security/blog/2026/06/04/updating-taxonomy-failure-modes-agentic-ai-systems-year-red-teaming-taught-us/)
- **LangGraph resilience patterns (manutej/langgraph-agentic-workflows):** Three resilience pillars: checkpointing (determines recovery granularity), human-in-the-loop (determines oversight quality), and bounded autonomy (determines maximum blast radius). PostgresSaver uses a four-table schema with configurable garbage collection and durability modes. Human-in-the-loop uses `Command(resume=)` API for dynamic interruptions. — [GitHub: langgraph-agentic-workflows/blogs/09-resilience-patterns.md](https://github.com/manutej/langgraph-agentic-workflows/blob/main/blogs/09-resilience-patterns.md)
- **Production practitioner patterns (Anthropic SDK discussion #1341):** Real production teams report tiered retry configs: 1s initial delay, 60s cap, 3 max retries, 30% jitter. Circuit breakers per tool with per-tool failure thresholds. Fallback model chains. State cleanup on mid-task failure. Key insight: "error recovery is 30% code, 70% expecting things to fail in ways you never imagined." Multi-agent systems require domino-prevention thinking — an error in one agent can cascade silently through the rest. — [GitHub Discussion: anthropics/anthropic-sdk-python #1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Stuck-loop recovery (agentpatterns.ai):** Recovery should NOT fire on slow-but-converging work. Detection must distinguish flat progress (stuck) from rising-but-slow progress (converging). Recovery ladder: nudge → replan → escalate → reset → human handoff — escalating in sequence until the agent escapes. Activity proxies (API call counts, file edits) rise during stuck loops too and cannot distinguish the two states. — [agentpatterns.ai/stuck-loop-recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/)
- **AI agent benchmark — Hermes Agent Reviews Lab (June 2026):** Injected 6 failure categories into running agent tasks. Measured recovery rate, recovery latency, recovery strategy (retry/fallback/escalation/degradation), and task completion rate. Found that LangChain implements 6/7 built-in error features, LlamaIndex implements 1/7, and that ToolException in LangChain converts failures into LLM observations — making the model your error handler, which is powerful but unpredictable. — [Hermes Agent Reviews](https://hermes-agent.reviews/error-recovery-patterns.html)

## Gotchas

- **Do not use `MemorySaver` in production.** It resets on every restart. Teams that do this spend a sprint reverse-engineering a database schema while in-flight agent threads die silently (ActiveWizards, 2026).
- **Iteration limits alone are not enough.** A step budget catches runaway loops but does not handle mid-task failures gracefully. You need both iteration limits and stateful rollback.
- **Silent failures outnumber loud ones in production.** Rate limits, timeout errors, and hallucinated tool parameters often produce HTTP 200 responses. Monitor for task completion signals, not just HTTP status codes.
- **Recovery ladder order matters.** Nudge before replan. Replan before reset. Reset before handoff. Skipping levels means paying the cost of a human intervention when a parameter adjustment would have sufficed.
- **Graceful degradation is not the same as giving up.** Returning partial results with a structured "here is what succeeded, here is what failed" is almost always better than a raw error message or silent failure.
