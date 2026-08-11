# S-2458 · The Fallback Chain Stack — When Your LLM Provider Goes Down and the Whole System Goes With It

Your primary model returns 429 rate-limit errors for the third time this week. Your agent retries — once, twice, three times — each retry resending the full conversation context and burning tokens on a degraded dependency. Meanwhile, 50 tasks queue behind it. This is not a theoretical risk: OpenAI, Anthropic, and Google each had significant outages in 2024–2025. Any production agent that depends on a single provider has a reliability ceiling equal to that provider's worst day. The fix is a **fallback chain**: ordered provider routes with circuit breakers, timeout budgets, and an explicit degradation contract.

## Forces

- **LLM providers fail probabilistically, not cleanly.** Unlike a database that returns a connection error, an LLM API returns a 429, a malformed JSON tool call, a timeout after 90 seconds, or a hallucinated function signature. Traditional try-catch blocks don't catch these failure modes.
- **Retries amplify outages.** Naive retry logic on a struggling provider creates a thundering herd. At 500 jobs/minute with 3 retries per job, you're generating 15,000 additional calls over 10 minutes against a dependency that is already overwhelmed. Each agent retry also resends the entire conversation context — a microservice retry sends KB; an agent retry sends the full conversation window.
- **No standard fallback in most frameworks.** LangChain, CrewAI, and AutoGen v0.4 do not ship with production-ready fallback chains out of the box. Teams build these ad hoc, often after their first major outage.
- **Model capability degrades across the chain.** A fallback to a cheaper or local model is not functionally equivalent. You need an explicit contract for what "degraded" means — and whether the degraded output is acceptable for this task type.

## The move

**Layer 1 — Build an ordered fallback chain by capability, not by cost.**

The chain orders providers by the quality bar your task requires, not by price. A typical production chain: `GPT-5 → Claude Sonnet 4.5 → Claude Opus 4.1 → Ollama (local Llama)`. Each rung in the ladder should be capable of completing the task, not just "good enough." If rung 3 can't handle the task class, your chain ends at rung 2.

**Layer 2 — Per-provider retry budgets with exponential backoff.**

Retry budgets are per-provider, not global. Exhausting GPT-5's 3 retries doesn't consume Claude's retry budget. Backoff doubles on each attempt: 1s → 2s → 4s. After the final retry on the primary, immediately route to the next provider — do not wait for backoff on a failed provider you are leaving.

**Layer 3 — Wire a circuit breaker per provider.**

Track failure rate and latency per provider. Open the circuit when failure rate exceeds 50% over a 30-second window, or when p99 latency exceeds 2× the SLA. While open, the breaker routes directly to the next provider for a configurable probe interval (typically 30s). Close the breaker only after a probe request succeeds. Cordum's production config: open at 3 failures for 30 seconds, shared state via Redis for distributed agents.

**Layer 4 — Budget total latency across the chain.**

Set a hard ceiling on total time spent in the fallback chain — typically 30–60 seconds for synchronous user-facing requests, longer for async batch tasks. When the budget is exhausted, return the best result obtained so far or invoke a graceful degradation handler. Do not continue cascading across providers while the user waits.

**Layer 5 — Define explicit degradation contracts per task class.**

Not all tasks should fall back equally. A customer-support draft can tolerate a mid-tier model with 70% accuracy. A medical document summarization should fail rather than return a degraded answer. Tag task classes with a `degradation_policy`: `fallback-acceptable` or `degrade-to-human`. A degraded lower-quality response may be worse than a clear "not available" message — **explicitly decide this per capability**, don't leave it implicit.

**Layer 6 — Instrument every failure and fallback in the chain.**

Log every provider handoff: which provider was tried, how many retries, final latency, and the output quality signal if available. This data drives circuit-breaker tuning and reveals which providers fail together (correlated failures that defeat naive round-robin). Observability is not optional — you cannot tune what you cannot see.

## Evidence

- **Anthropic Engineering Blog:** Recommends that teams "start by using LLM APIs directly" rather than complex frameworks, and emphasizes composable patterns — the fallback chain being a direct expression of that philosophy. The blog defines agents as systems where "LLMs dynamically direct their own processes and tool usage," and recommends workflows over agents when predictability matters. — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **Databricks / Flo Health (80M MAU):** The Databricks talk on production agentic AI explicitly recommends deterministic systems over autonomous agents for reliability-sensitive deployments, with the core recommendation being: "predetermined, sequenced steps" over "free choice across tools." This supports the fallback chain as an architecture that preserves deterministic behavior even under provider failures. — [URL](https://www.zenml.io/llmops-database/production-ai-deployment-lessons-from-real-world-agentic-ai-systems)
- **Cordum Production Incident:** At 500 jobs/minute, naive retry logic generated 15,000 additional avoidable calls over 10 minutes. The fix: a policy-aware circuit breaker that opens at 3 failures for 30 seconds and shares state via Redis across distributed agent instances. Documents the POLICY_CHECK_FAIL_MODE=closed vs. open toggle for governing what happens to in-flight actions while the breaker is open. — [URL](https://cordum.io/blog/ai-agent-circuit-breaker-pattern)
- **Mastra AI:** Shipped model fallbacks as a first-class configuration primitive, with explicit per-model retry counts and a tree structure: primary model → N retries → fallback model → N retries → fallback model. Documents the production need: "Every AI provider has outages. OpenAI goes down. Anthropic hits capacity. Google rate-limits you." — [URL](https://mastra.ai/blog/model-fallback)
- **Zylos Research (2026):** Synthesizes a 7-layer resilience model for production agents: LLM API fallback chains, circuit breakers, context compaction, tool error recovery, rate limiting / backpressure, agent-to-agent communication resilience, and partial result handling. Notes that LLM failures break every assumption of deterministic distributed systems (CAP theorem, Paxos, Raft). — [URL](https://zylos.ai/en/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems)

## Gotchas

- **Correlated failures sink naive round-robin.** If all your cloud providers fail simultaneously (upstream backbone issue), a round-robin fallback just tries each failing provider in turn. Your local/Ollama fallback is the only thing that saves you — but only if it's in the chain and the chain reaches it within the latency budget.
- **Context carries over the chain, but capability doesn't.** When falling back from GPT-5 to Claude Sonnet, the conversation context is preserved. But the model's tool-calling schema, response format, and instruction-following can differ. Test your fallback chain's outputs against your eval set, not just the happy path.
- **A breaker that never opens is a breaker that doesn't work.** Teams over-tune circuit breakers to avoid false positives, then discover the breaker never triggered during a real outage because the thresholds were too conservative. Start tighter (3 failures / 30s) and loosen based on production data.
- **The last fallback in the chain often becomes a silent failure.** If your chain ends with "return error," that error propagates as an unhandled exception unless you have a graceful degradation handler. Define what the last fallback does before you need it.
