# S-2614 · The Agent Failure Recovery Stack

When your agent loops into a dead end, burns tokens with no output, or silently fails mid-task — and you need a system that catches this before it costs you.

## Forces

- **Confident failures look like successes** — agents hallucinate their way past errors and return HTTP 200 with nonsense. Traditional try-catch doesn't cover this.
- **The compounding accuracy problem** — 30 tools at 95% reliability per call means only ~21% of executions complete cleanly. Failure recovery is load-bearing, not optional.
- **Loops are the most expensive failure mode** — unlike a crashed agent that stops billing, a looping agent burns $4.50–$9 every 5 minutes until a human notices.
- **Agents lose accumulated state on restart** — unlike microservices, agents carry conversation history, learned context, and intermediate progress that a simple retry wipes.
- **Recovery strategies must match error type** — retrying an auth failure is different from retrying a rate limit, which is different from retrying a semantic parse error.

## The Move

Build a **layered failure hierarchy** that promotes errors up the chain only when recovery is genuinely possible at each level:

1. **Classify the error type first** — this determines the entire recovery path.
2. **Enforce hard limits before recovery** — loop detection, token budgets, and circuit breakers prevent the most expensive failure modes.
3. **Retry only what's worth retrying** — transient errors (rate limits, timeouts, 503s) retry with backoff; 4xx errors and auth failures do not.
4. **Checkpoint state at every step** — so a mid-task crash resumes from the last completed step, not from scratch.
5. **Design explicit fallback paths** — agents asked to "do your best" when a tool fails will hallucinate their way through it.
6. **Track semantic quality, not just technical success** — a tool call that returns HTTP 200 but wrong data needs a different handler than a timeout.

## Evidence

- **HN Discussion (183 pts, 68 comments):** "Best Practices for Building Agentic AI Systems" — practitioner highlights: subagents as pure stateless functions, tools returning recovery instructions on failure, per-step validation before passing output to the next step. — [news.ycombinator.com/item?id=44919647](https://news.ycombinator.com/item?id=44919647)

- **Reddit r/AI_Agents:** "How are you handling recovery when AI agents fail mid-task?" — practitioners report hybrid approaches: BullMQ or Postgres for per-step state persistence, idempotent task design so retries don't double-execute, Temporal for durable execution that encodes reliability "almost for free." — [reddit.com/r/AI_Agents/comments/1u0bp9v](https://www.reddit.com/r/AI_Agents/comments/1u0bp9v/how_are_you_handling_recovery_when_ai_agents_fail/)

- **LoopBuster GitHub (88 stars, MIT):** Unified anti-dead-loop toolkit for LLM agents with 4 detection strategies (ExactRepeat, SemanticRepeat, CyclePattern, OutputStagnation). Documents token cost: a 5-minute loop burn at standard rates. — [github.com/liuchunwei732-cmyk/loopbuster](https://github.com/liuchunwei732-cmyk/loopbuster)

- **Chrono Innovation / HN Pattern Analysis:** Production agentic workflows require "explicit failure recovery paths" — fallbacks must be designed into the workflow, not handled by agent judgment. Per-step validation: verify output against schema before passing to the next step. — [chronoinnovation.com/resources/agentic-ai-workflows-architecture](https://www.chronoinnovation.com/resources/agentic-ai-workflows-architecture/)

- **NCP-AAI (NVIDIA Certified Professional) Error Taxonomy:** Agent errors break into 4 categories — Transient (retry), Semantic (re-prompt with corrective context), Resource (reduce payload or switch model), Fatal (escalate to human). Retry logic must be error-type-aware. — [preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

- **Show HN: AgentFuse & AgentCircuit:** Two independent "circuit breaker for AI agents" projects launched within months of each other — signals a real gap. AgentFuse explicitly marketed as "prevent $500 OpenAI bills." — [github.com/AbdulBasitA/agent-fuse](https://github.com/AbdulBasitA/agent-fuse), [github.com/simranmultani197/AgentCircuit](https://github.com/simranmultani197/AgentCircuit)

## Gotchas

- **Retrying everything is a cost explosion** — rate-limited APIs, timeout-prone tool calls, and semantic parse failures all look the same to a naive retry loop. Classify first.
- **Agents don't know when they've succeeded** — "undetected task completion" (agent finishes but doesn't recognize it) is a primary loop cause. Define and validate success conditions explicitly.
- **State loss on restart is silent** — without checkpointing, a crash after 58 minutes of work means all 58 minutes are lost. This is the gap durable execution (Temporal) targets.
- **Per-step validation catches semantic failures** — a tool call returning HTTP 200 with wrong schema is technically "successful." Only a validation gate between steps catches this.
- **Fallback paths must be explicit in workflow design** — the HN practitioner consensus: agents "asked to do their best" when a tool fails will hallucinate. Design the fallback before the agent needs it.
