# S-1387 · The Durable Execution Stack — When Your Agent Forgets Everything on Crash

You built a 10-step agentic workflow. It ran for 45 minutes, then crashed on step 9. Now it restarts from zero. This is the default state of AI agents — and it is a production disaster waiting to happen.

## Forces

- **Reliability math is brutal.** Chain ten steps each succeeding 85% of the time → only ~20% end-to-end success rate (0.85¹⁰ ≈ 0.20). More steps, more failure surface. Doubling task duration quadruples the failure rate.
- **Agents fail differently than software.** A web service crashes and logs a stack trace. An agent may silently loop, spawn redundant subprocesses, accumulate context until the model halts, or take an irreversible action before a human intervenes.
- **Retries aren't enough.** Naive retry (re-run from step 1) duplicates side effects, burns tokens, and has no memory of progress. An idempotency key on a retry does not fix a mid-reasoning crash.
- **Durable infrastructure is underinvested.** Only 1.6% of Claude Code's codebase is AI decision logic; the other 98.4% is operational infrastructure (per the 2026 _Dive into Claude Code_ analysis, arXiv:2604.14228). Teams build the brain and forget the spine.
- **Production agents without durability fail early.** 73% of enterprise AI agent deployments experience reliability failures within their first year of production. GPT-4o agents demonstrate >91% failure rates on complex multi-step tasks without durability infrastructure.

## The Move

Treat your agent's state as a first-class durable artifact — not a Python variable in memory. Use checkpoint-and-resume at every step boundary so failures become inconvenient pauses, not total losses.

### 1. Checkpoint at Every Step Boundary

Serialize agent state (full message history, tool call results, intermediate outputs) to durable storage after every tool call completes. Use LangGraph's built-in checkpointer, Temporal's workflow history, or a simple Redis-backed key-value store for lightweight cases. The checkpoint is your resume point.

### 2. Layer Self-Correction Before Retrying

A retry with the same error message wastes a turn. Instead: when a tool output fails validation, route it to a **repair agent** or **structured error description** that tells the model exactly what was wrong — then retry with the corrected context. This is a retry with a better error message.

### 3. Set Step and Cost Circuit Breakers

Hard limits prevent runaway agents. Cap maximum steps (e.g., 20), maximum total cost per run, and context window budget. When a breaker trips, halt gracefully and surface partial results. Never let an agent iterate indefinitely — that is where cost overruns and silent failures live.

### 4. Classify Failures Before Acting

Per Arun Baby's four-class taxonomy:

| Class | Problem | Recovery |
|-------|---------|----------|
| **Syntactic** | Broken JSON, malformed output | Structured output mode or repair agent |
| **Semantic** | Wrong tool, wrong arguments | Re-plan with corrected context |
| **Environmental** | Network timeout, API rate limit, container restart | Exponential backoff + retry with idempotency key |
| **Intentional** | Hallucination, prompt injection | Guardrails, output validators, Pydantic schemas |

Environmental failures are retried. Semantic failures re-plan. Syntactic failures repair. Intentional failures halt and escalate.

### 5. Use Durable Execution Frameworks as Infrastructure, Not Libraries

LangGraph's checkpointing, Temporal's workflow persistence, and Pydantic AI's structured output mode are not optional add-ons — they are the production runtime. For MCP-based architectures, mcp-agent's one-config-line Temporal integration provides durable execution without learning Temporal's workflow DSL.

### 6. Track State as an Append-Only Event Log

For auditable or regulated workflows (customer support actions, finance ops, incident response), append tool outputs and LLM reasoning traces to an event log. On restart, replay from the last checkpoint. Consider hash-chaining or Merkle root verification for tamper-evident logs.

## Evidence

- **arXiv (March 2025, revised October 2025):** Systematic study of 1,600+ annotated multi-agent traces across 7 frameworks. Found 17.14% of failures are step repetitions and 13.98% are reasoning-action mismatches — failure modes that naive retry loops amplify rather than fix. — [arXiv:2503.13657](https://arxiv.org/abs/2503.13657)

- **Engineering Blog (June 2026):** Walkthrough of LangGraph durable execution patterns. Key insight: a 10-step pipeline at 85% per-step reliability succeeds only 20% of the time without checkpointing. With checkpoint-and-resume, each failure resumes from the last completed step rather than from zero. — [Vadim's Blog — Durable Execution in LangGraph](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)

- **HN "Show HN" (April 2025):** TengineAI creator identified the core architectural problem: "LLMs are being used to trigger application code directly — that's the wrong abstraction." Proposed treating tool calls as discrete, auditable, permissioned events rather than in-process function invocations. — [HN #47427554](https://news.ycombinator.com/item?id=47427554)

- **HN "Ask HN" (early 2025):** Practitioner reliability audits identified 7 core agent failure modes including hallucination under unexpected inputs, edge case collapse (null values, Unicode names), and prompt injection — all of which bypass standard try/catch error handling. — [HN #47325105](https://news.ycombinator.com/item?id=47325105)

- **AgentMarketCap Analysis (April 2026):** GPT-4o agents show >91% failure rates on complex multi-step tasks without durability infrastructure. 73% of enterprise deployments experience reliability failures within year one. Temporal recommended when task duration exceeds 4 hours or cost of full restart exceeds infrastructure cost. — [AgentMarketCap — Durable Agent Execution in Production 2026](https://agentmarketcap.ai/blog/2026/04/10/durable-agent-execution-production-temporal-modal-event-sourced)

## Gotchas

- **Retries without idempotency keys duplicate side effects.** If your agent sent an email on step 7 and crashes, a retry from step 7 sends it again. Wrap side-effecting tools with idempotency tokens from day one.
- **Checkpointing the wrong granularity.** Saving state only on final completion defeats the purpose. Checkpoint after every tool call result — that is your atomic unit of progress.
- **Self-correction loops that never converge.** An agent told "that was wrong" on step 5 may re-plan, fail again, and re-plan again indefinitely. Combine self-correction with a hard step cap and a "give up and surface partial results" path.
- **Treating structured output as optional.** Pydantic validation as a pre-execution shield catches syntactic failures before they propagate into downstream steps. Without it, malformed outputs silently corrupt the agent's reasoning context.
- **Forgetting to test failure paths.** Most teams test the happy path. Test: container restart mid-run, API rate limit on step 4, injected prompt on step 6, null database field on step 8. If the agent survives your chaos test, it is production-ready.
