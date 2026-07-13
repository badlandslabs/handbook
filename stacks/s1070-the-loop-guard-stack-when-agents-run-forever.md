# S-1070 · The Loop Guard Stack: When Agents Run Forever

You've shipped a multi-step agent. It works in demos. Three weeks in, someone notices the API bill is 40× normal and the agent has been retrying the same failed Elasticsearch query since Tuesday. No alert fired. No one was watching the conversation trace.

This is the failure-handling gap: agents fail silently in ways traditional software doesn't.

## Forces

- Agents can operate *incorrectly* without raising any exception — the code doesn't know something is wrong
- Loop patterns emerge gradually: flaky dependency → retry → pattern → loops that cost real money before anyone notices
- Standard observability (HTTP status codes, error logs) misses the failure modes that matter: semantic drift, tool hallucination, progress stalls
- Every external call — model API, tool endpoint, vector store — is an independent failure point with different retry semantics
- Recovery isn't one-size-fits-all: transient timeouts want retry, hallucinated tool names want re-prompting, spec failures want a human
- Loop prevention can't live in prompts alone; it needs to be in code as a hard policy

## The Move

Build a layered failure-handling stack. Each layer catches a different failure mode.

### Layer 1 — Hard Budget Guards (always on, in code)

- **Max iterations cap**: set `max_steps=50` or equivalent as a non-negotiable bound — the agent hits it and returns whatever state it has, no exceptions
- **Token and cost budget**: track cumulative tokens per run, hard-stop at a configured ceiling (prevents the "GPT-4o ran for 6 hours" scenario)
- **Step-idempotency dedup**: keep a rolling window of the last N tool-call signatures; if the same call appears 3× in a row, break the loop and escalate

### Layer 2 — Error Taxonomy & Targeted Recovery

Not all errors retry the same way. Segment by type:

| Error Class | Example | Recovery |
|---|---|---|
| **Transient** | HTTP 429, 503, timeout | Exponential backoff retry (1s, 2s, 4s, cap at 32s) |
| **Semantic** | Malformed JSON, hallucinated tool name | Re-prompt with corrective context, max 2 attempts, then fail |
| **Specification** | Agent chose wrong tool, bad plan | Rollback to last checkpoint, re-plan |
| **Fatal** | Auth failure, quota exceeded | Fail immediately, no retry |

Per [Neel Mishra's agent error taxonomy](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html), each category needs its own retry contract — exception classes, max attempts, and backoff specified *per call site*, not globally.

### Layer 3 — Stateful Checkpointing

Save agent state to durable storage (Redis, Postgres, or LangGraph's `MemorySaver` / `PostgresSaver`) at defined checkpoints — before each major tool call, not just on failure.

This enables **resume without redo**: if the agent crashes mid-flight or you deploy a fix mid-run, you can rehydrate state and continue from the last good checkpoint rather than restarting from scratch.

```python
# LangGraph checkpoint pattern
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(os.environ["DATABASE_URL"])
app = graph.compile(checkpointer=checkpointer)
# Resume: pass thread_id to pick up where you left off
```

This is [LangGraph's native checkpoint/resume primitive](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md), adopted by the Microsoft Agent Framework with equivalent semantics.

### Layer 4 — Circuit Breakers for LLM APIs

Apply distributed-systems circuit breakers to model calls. Three states:

- **Closed** (normal): requests pass through; failures increment a counter
- **Open** (blown): after N failures in a window, stop calling the provider for a cooldown period — prevents cascading thread exhaustion
- **Half-open**: after cooldown, allow a test request through; if it succeeds, close the circuit

Per [GitPlumbers' analysis](https://gitplumbers.com/blog/circuit-breakers-for-llms-how-we-stop-hallucinations-drift-and-latency-spikes-fr/), the key insight is that LLM providers brown out gradually (latency spikes, degraded quality) before they hard-fail — circuit breakers catch the cascade before thread pools exhaust.

### Layer 5 — Graceful Degradation

For each critical workflow, define the **bare-minimum degraded experience** before you build anything else:

- If the primary model is unavailable → fallback to a cheaper/slower model
- If a non-critical tool fails → skip it, note the failure, continue with remaining steps
- If the full pipeline can't complete → return a partial result with a clear "incomplete" flag, never silently swallow the failure

This is the last line before the agent hands off something wrong with high confidence.

### Layer 6 — Loop Detection & Alerting

The failure mode that burns money: the agent makes progress for 10 minutes, hits a consistent failure, and retries that same failed call in a tight loop. Traditional logs won't help — you need behavioral monitoring.

- **Sentrial** (YC W26, [HN launch thread](https://news.ycombinator.com/item?id=47337659)) specifically detects loop patterns, hallucinations, and tool misuse from conversation traces — not just log lines
- Track **unique tool-call signatures per step window**; if a step repeats >2× with identical inputs, flag and halt
- Instrument step-level latency: a step that normally takes 2s but takes 30s with no progress = stuck

Per [DEV Community / Ceyhun Aksan](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai): "Dozens of similar reports show up across GitHub, HN, and Reddit — agent loops and burns through API credits, agent works fine for weeks then silently degrades, developers find out from users not from monitoring."

## Evidence

- **HN Launch (Sentrial):** "When agents fail, choose wrong tools, or blow cost budgets, there's no way to know why — usually just logs and guesswork. As agents move from demos to production with real SLAs, this is not sustainable." — [HN #47337659](https://news.ycombinator.com/item?id=47337659)
- **DEV Community post:** A GPT-4o agent got stuck in a retry loop, ran up a significant bill, no alert fired. LangChain agent went into a recursive loop in production. Dozens of corroborating reports on HN and Reddit of the same pattern. — [DEV Community](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai)
- **GitHub (ombharatiya/ai-system-design-guide):** "Error handling has moved from Try-Catch blocks to Agentic Self-Correction and Stateful Rollbacks, with frameworks like LangGraph and Microsoft Agent Framework providing native checkpoint/resume primitives." — [GitHub](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **GitPlumbers:** Circuit breakers for LLM APIs prevent cascading thread exhaustion when providers brown out. Latency spikes and degraded quality cascade before hard failure — circuit breakers catch the cascade. — [GitPlumbers](https://gitplumbers.com/blog/circuit-breakers-for-llms-how-we-stop-hallucinations-drift-and-latency-spikes-fr/)
- **Neel Mishra / MLOps:** Four-category error taxonomy (transient, semantic, specification, fatal) with per-category retry contracts — retry semantics must be defined per call site, not globally. — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

## Gotchas

- **Hard budget guards are the only ones that actually fire.** Soft prompts ("try not to loop") fail in production — policy must be in code
- **Checkpointing without a resume path is half-measured.** Saving state is useless if you don't have the resume logic wired up to use it on the next call
- **Global retry logic is wrong.** A rate-limit error and a hallucinated tool name require completely different responses — treating them the same leads to wasted retries on unrecoverable errors and insufficient retries on transient ones
- **Loop detection requires tracing, not logging.** Standard HTTP logs won't show you that the agent called the same tool 47 times with identical arguments; you need step-level conversation tracing
- **Circuit breakers need tuning per provider.** OpenAI, Anthropic, and self-hosted models have different failure signatures — a circuit that opens after 5 errors in 10 seconds might be right for one and too aggressive for another
