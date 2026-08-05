# S-2156 · The Recoverable Agent Stack — When Your Agent Fails (But Most of Those Failures Are Fixable)

Your agent hits a rate limit, hallucinates a function parameter, and compounds the error by calling the wrong tool three more times. In a traditional system, this is a crash. In an agentic system, it's a Tuesday — and 86% of these failures are recoverable with the right architecture. The problem is not that agents fail. The problem is that most agentic architectures have no recovery path, so a fixable failure becomes a cascade.

## Forces

- **Agents fail in ways traditional software doesn't.** Tool calls return HTTP 200 but semantically wrong data. A function parameter gets hallucinated into existence. The agent confidently loops on a bad plan. These aren't exceptions — they're the normal operating environment.
- **Cascade amplification makes single failures expensive.** A bad tool output from one agent becomes a bad instruction for the next, which produces bad data for the third. The failure isn't the error — the failure is what the error propagates into. (Corroborated by S-2155 on cascade boundaries.)
- **The gap between pilot and production is almost entirely an error-handling problem.** McKinsey's late-2025 survey found 62% of enterprises experimenting with agentic AI but only 14% production-ready. The 48-point gap is not model capability — it's systems that weren't built to handle failure.
- **Recoverable failures become permanent failures without the right infrastructure.** An agent that can't detect, route around, or recover from a bad tool call will keep retrying the same broken plan indefinitely.

## The Move

Build a layered failure architecture: surface-level retry logic, a circuit breaker to stop cascading, a state checkpoint so recovery is clean, and a human-in-the-loop guardrail for high-stakes decisions. The goal is not to prevent failure — it's to make every failure survivable.

### 1. Separate error types before choosing a recovery strategy

Deterministic errors (network timeout, 500, auth expiry) have clear fix paths — retry with backoff, refresh credentials, reroute. Non-deterministic errors (hallucinated parameters, confident wrong answers, semantically broken responses) need different handling: validate outputs before using them, and break the loop rather than retry into a black hole.

### 2. Circuit breaker pattern for tool calls

Wrap every external tool call in a circuit breaker. After N consecutive failures on a tool or API, stop calling it and fall back to an alternative or a safe default. The agent should know what to do when the primary path is broken — not keep hammering the failing endpoint and compounding the damage.

### 3. Checkpoint state before every major step

Write agent state (current plan, tool call history, intermediate outputs, working memory) to durable storage before each step executes. If a step fails, recovery loads the checkpoint rather than starting from scratch. This is write-ahead logging for LLM agents — the equivalent of not losing your document because the power went out.

### 4. Human-in-the-loop for high-stakes steps

Define a risk threshold. Any tool call that writes to external systems (databases, deployment pipelines, financial APIs, user-facing messages) must pass through a human approval step or a strict output validator before executing. This isn't optional guardrail — it's the mechanism that converts a cascade failure into a recoverable one.

### 5. Graceful degradation over crash

When the primary agent path fails, the system should degrade to a known-safe fallback: a simpler agent, a rule-based response, or a human escalation. Never let the agent fail into silence. A "I'm having trouble — here's what I tried and what I need" message is a successful outcome, not a failure mode.

### 6. Idempotency as first-class design

Every tool call should be safe to retry. Design function calls so that calling them twice with the same parameters produces the same result as calling once — no double charges, no double writes, no duplicate records. Idempotency makes retry safe, and safe retry is the foundation of all recovery.

## Evidence

- **Engineering blog:** Anthropic's code execution with MCP case study showed agents misusing tools in long-running workflows, and recommended on-demand tool loading (loading tools only when needed, not all at once) to reduce hallucinated parameter errors by narrowing the context. A 98.7% token reduction in tool loading was documented in production deployments. — [Anthropic Engineering: Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Industry survey:** The Operator Collective's 2026 production guide cited Gartner predicting 40%+ of agentic AI projects will be cancelled by 2027 — not due to model limitations but due to systems not handling failure. Their analysis found 86% of agent failures are recoverable, but recovery requires explicit architecture. — [The Operator Collective: AI Agent Error Handling](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Technical breakdown:** Preporato's NCP-AAI article documented that "errors include hallucinations that return HTTP 200" — the core distinction between traditional and agentic error handling. Recommended combining write-ahead logging (state checkpoints before each step) with event sourcing for recovery paths, plus structured circuit breaker patterns per tool. — [Preporato: Error Handling in AI Agents](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)
- **HN corroboration:** Hacker News discussion on Anthropic's "Building Effective AI Agents" (543 points, 88 comments) surfaced broad agreement that most agent frameworks lack explicit failure handling — practitioners recommended building recovery logic directly into tool wrappers rather than relying on framework defaults. — [Hacker News Thread](https://news.ycombinator.com/item?id=44301809)
- **Case study:** Neo4j documented an enterprise team using a graph database as the memory/checkpoint layer for a multi-agent system — storing each agent's tool call history, intermediate outputs, and session state as a graph, enabling post-failure trace-back to the exact step where the cascade started. — [Neo4j: AI Agent Case Studies](https://neo4j.com/blog/agentic-ai/ai-agent-useful-case-studies/)

## Gotchas

- **Retrying without idempotency creates new failures.** Retrying a non-idempotent tool call (a payment, a database write, a message send) on a network timeout doesn't recover — it duplicates. Idempotency must be designed in, not assumed.
- **A circuit breaker without fallback is just a faster failure.** Tripping the breaker on a bad API is correct; continuing without any response to the user is not. The breaker trip should trigger an alternative path, not an empty silence.
- **Checkpoint state that isn't tested is a false promise.** Teams implement write-ahead logging for agent state but never run a failure drill — so when a real failure happens, the checkpoint is corrupt, empty, or the recovery code has a bug. Test recovery path the same way you test disaster recovery for databases.
- **Human-in-the-loop that blocks all progress is not a guardrail, it's a bottleneck.** Approval gates should be tiered by risk — low-risk tool calls flow through, only high-stakes calls pause for review. If every agent step requires a human, you've built a chatbot with extra steps.
- **Silent degradation hides the failure signal.** When an agent degrades gracefully to a fallback, the fallback should surface that it was triggered. Otherwise, the team never learns that the primary path is broken, and the fallback becomes the permanent degraded state.
