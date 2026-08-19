# S-2867 · The Tool-Call Error Taxonomy Stack — When Your Agent Passed Every Benchmark but Production Shows a 12–18% Failure Rate

Your agent scores 77% on SWE-bench Verified. Your CI suite is green across 847 test cases. You ship on Friday. Monday morning you learn the agent has been burning through retries on a rate-limited API, has fabricated 4 database transactions that never actually committed, and your monitoring dashboard shows zero alerts because every failure was "handled" by the LLM retrying silently until it gave up. The gap between benchmark performance and production reliability is the tool-call failure rate that no benchmark tests: **12–18% of tool invocations in a real agent pipeline fail**. This stack gives you the taxonomy and layered defenses to close it.

## Forces

- **Benchmarks don't test tool-call reliability.** SWE-bench Verified runs agents in controlled containers with stable network conditions and fixed dependency versions. Production has rate limits, OAuth tokens that expire mid-session, schema drift in APIs updated by other teams, and DNS failures at 2 a.m. The 12–18% failure rate lives entirely outside the benchmark world.
- **Retry logic is not one-size-fits-all.** Retrying a rate-limited HTTP call is correct. Retrying a tool that sends an email or writes a database row can cause duplicates, double-charges, or corrupted state. Teams that apply naive exponential-backoff retries across all tools cause new classes of failures on top of the original ones.
- **The ownership boundary between orchestration layer and LLM layer is violated constantly.** When teams handle everything at the LLM layer, they burn tokens re-prompting the model to retry on failures that infrastructure should handle silently. When teams handle everything at the orchestration layer, they miss application-level errors that require a behavioral pivot — not a retry.
- **The failure taxonomy has 12 categories across 4 phases** (initialization, parameter handling, execution, result interpretation) per arXiv 2601.16280. Treating all failures as the same and applying one recovery strategy covers zero of them correctly.

## The move

**Separate the error recovery ownership model across two layers**, classify failures into four categories with distinct recovery strategies, and treat retry-safety as a first-class tool design constraint.

### Layer 1 — Orchestration Layer (infrastructure handles silently)

- Route all transport and network failures here: dropped TCP connections, DNS timeouts, HTTP 503, HTTP 429 rate limits
- Apply exponential backoff with jitter for rate-limit retries — never fixed-interval retry, which amplifies thundering-herd problems
- Maximum 3–5 retry attempts with circuit breaker: after N consecutive failures on the same tool, stop retrying and escalate
- LLM layer never sees these — it's blind to infrastructure noise and stays focused on application logic

### Layer 2 — LLM Layer (model reasons through behavioral pivots)

- Route semantic failures, schema drift, auth rot, and ambiguous results here: the model decides whether to rephrase a query, use a different tool, ask a human, or abandon the task
- Feed the LLM structured failure context (not raw error messages): `{"type": "schema_mismatch", "expected": [...], "received": [...], "tool": "fetch_customer_record"}`
- Give the model a "recovery vocabulary" — explicit instruction in the system prompt about what options exist when a tool fails: retry_with_modification, fallback_to_alternative, escalate_to_human, abort_task

### Failure Classification — Four Categories, Four Owners

| Category | Examples | Owner | Strategy |
|---|---|---|---|
| **Transient infrastructure** | 429 rate limit, 503 unavailability, timeout | Orchestration | Retry with backoff + jitter, max 5 attempts |
| **Auth/session rot** | OAuth token expiry, API key revocation | Orchestration + LLM | Refresh credential → retry once; if retry fails, LLM handles |
| **Schema/interface drift** | API response shape changed, parameter renamed | LLM | Prompt adjusts tool invocation; falls back to alternative tool |
| **Semantic/result failure** | Tool returned data but it's wrong/empty | LLM | Re-evaluate goal, try alternative approach or escalate |

### Tool Design Constraints

- **Idempotency check before retry.** If a tool has side effects (email, DB write, payment), add an idempotency key to the request and check for prior execution before retrying. Non-idempotent tools should never be retried without explicit human-in-the-loop confirmation.
- **Structured error wrapping.** Every tool should return errors in a consistent schema: `{"error_type", "is_retryable", "retry_after_seconds", "context"}` — this lets both orchestration and LLM layers make correct routing decisions.
- **Timeout budgets.** Set per-tool budgets rather than global timeouts: a search tool gets 10 seconds, a database query gets 5 seconds, a code execution tool gets 120 seconds. When a budget exhausts, the correct behavior is escalation, not indefinite retry.

## Evidence

- **Benchmark post:** Tool-call failure rates of 12–18% in production agent pipelines vs. near-zero infrastructure failure assumptions in standard benchmark scaffolds — *AgentMarketCap, citing arXiv 2601.16280* — https://agentmarketcap.ai/blog/2026/04/10/agent-tool-call-retry-failure-mode-handling-production-2026

- **Field report:** 18-month production comparison across LangGraph, CrewAI, and AutoGen found LangGraph achieved 96% error recovery rate vs. 68% for AutoGen and 72% for CrewAI, attributed primarily to LangGraph's explicit state machine graph making error routing deterministic vs. LLM-dictated flow control in other frameworks — *hjLabs GitHub notes (field report, not benchmark)* — https://github.com/hemangjoshi37a/hjLabs-AI-Engineering-Notes/blob/main/04-crewai-vs-langgraph-vs-autogen-production-comparison.md

- **Architecture guide:** Multi-layered defense principle — "Divide recovery responsibilities between the orchestration layer (silent, infrastructure-level retries) and the LLM itself (reasoning-based recovery for application-level problems)" — *n8n Blog, LLM Tool Calling Error Handling, July 2026* — https://blog.n8n.io/llm-tool-calling-error-handling

- **Production numbers:** LangGraph at 34.5M monthly PyPI downloads with deployments at LinkedIn, Klarna, Uber, and Elastic — *datarekha.com, 2026 ecosystem comparison* — https://datarekha.com/blog/crewai-vs-langgraph-vs-autogen/

- **Architecture pattern:** Five-pattern orchestration spectrum (direct model call → single agent → sequential → parallel → hierarchical), with explicit guidance to match complexity to business value — *Gary Samuelson, synthesizing Anthropic's "Building Effective AI Agents: Architecture Patterns and Implementation Frameworks," July 2025* — https://garysamuelson.github.io/agentic/architecture-patterns/

## Gotchas

- **The thundering-herd retry trap.** Fixed-interval retries on rate-limited APIs cause all retrying agents to hit the limit simultaneously again. Use capped exponential backoff with full jitter: `random(0, min(base * 2^attempt, max_delay))`.
- **The silent LLM-retry loop.** Without a max-retry counter visible to the LLM, the model can enter a loop of retrying a failed tool with minor modifications — burning tokens and making no progress. Set a hard `attempt_count` in the structured failure context so the model knows when to stop.
- **Schema drift not caught by CI.** API schema changes from upstream teams are the most common cause of production failures that pass every local test. Add contract testing (e.g., Pact, Dredd) for tool interfaces, not just unit tests on your own code.
- **Idempotency keys are easy to forget.** When a tool call fails after the network call but before the response arrives, the request may have succeeded server-side. Retrying without an idempotency key is the root cause of a significant fraction of duplicate-email and duplicate-charge bugs in agent pipelines.
