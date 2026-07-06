# S-713 · Agent Eval & Cost Governance: The Unseen Liability

[Agents fail silently in production and cost 3–10x more than expected. The gap between an agent that works in a notebook and one that holds up at scale is not a tuning problem — it is an eval and FinOps problem that most teams discover only after the first ugly invoice.]

## Forces

- **Agents are non-deterministic: traditional logging doesn't work.** Same input ≠ same output. You cannot reproduce failures from logs alone. Agents need trace-level observability, not request-level logging.
- **Eval suites are a snapshot; production is a moving target.** A super-majority of YC agent builders report that keeping evals up to date becomes "an impossible task" as production traffic shifts daily. An offline suite written against last month's traffic does not catch regressions on next month's distribution.
- **Cheaper tokens do not mean lower bills (Jevons Paradox).** When per-token prices fell 280x (GPT-3.5-equivalent: $20 → $0.07/M tokens, 2022–2024), enterprise GenAI spend climbed $2.3B → $13.8B → $37B. A platform team swapped to a 10x-cheaper model; single-request cost dropped 90%; the monthly bill tripled six weeks later because cheaper tokens enabled wider deployment, wider contexts, and second-pass quality calls.
- **Agents burn 3–10x more LLM calls than chatbots.** Unconstrained agents on software engineering tasks cost $5–8 per task in API fees alone. Teams rarely factor this multiplication into their unit economics.

## The Move

Layer eval and cost governance as first-class production infrastructure — not afterthoughts.

**Eval stack — two distinct layers:**

- **Offline regression gate (DeepEval):** Golden questions with ground-truth answers. Pytest-native, local execution, no data leaves your infra. Fails deploys on regression. Use for PR quality gates on every agent change.
- **Production monitoring loop (RAGAS or Phoenix):** Sampled live traces at 1–5% of traffic. Tracks faithfulness and context precision continuously. Publish to Langfuse as the single trace source of truth.

**Observability platform — pick one by data sovereignty need:**

- **LangSmith** if you use LangGraph/LangChain and accept managed hosting (400+ companies, 1T+ spans/month processed, time-travel debugging, enterprise self-host available).
- **Langfuse** if you need self-hosted, OpenTelemetry-native tracing (MIT open source, first-class self-hosting).
- **Phoenix (Arize)** if you want free, notebook-first debugging with the strongest built-in eval engine (Apache 2.0, single container deploy).

**LLM selection — match model to task, not preference:**

- **Claude 3.5 Sonnet** as default for interactive agents and long-context reasoning (synthesis across many retrieved docs).
- **GPT-4o** when downstream systems require guaranteed JSON schema compliance — structured output reliability is measurably better.
- **Gemini 2.0 Flash** for high-volume, latency-sensitive tasks — 25x cheaper than GPT-4o per token.
- **Llama 3.1 70B on Together AI** for batch document processing where acceptable quality trade-off exists (10x cost reduction).
- **Run both** for workflows with a synthesis turn and a structured-output turn — use eval infrastructure to make the call honestly.

**Cost governance — four compounding layers that stack to 60–80% reduction:**

1. **Semantic caching** deflects ~30% of queries entirely (cache semantically similar requests).
2. **Model routing** directs ~50% of calls to cheaper models (classifier-based routing before expensive calls).
3. **Prefix caching** reduces cost of remaining inference (provider-side repetition elimination).
4. **Batch scheduling** captures asynchronous workloads at ~50% discount.

**Agent-side budget awareness:** Agents that observe their own resource consumption (summarize older turns, prefer cheaper tools, early-exit on budget constraint) reduce cost structurally, not just per-call.

## Evidence

- **YC AI Agents Survey (2026):** "A super-majority of respondents said evals often under-deliver because keeping them up to date becomes an impossible task." — Voker, State of YC AI Agents 2026 — https://www.morphllm.com/ai-agent-evaluation-frameworks
- **Zylos Research (2026):** Agents make 3–10x more LLM calls than simple chatbots. Unconstrained agents on software engineering tasks cost $5–8 per task in API fees. Enterprise LLM spend reached $8.4B in H1 2025; 96% of teams report costs exceeding initial projections. Full optimization stack (semantic cache + routing + prefix cache + batch) delivers 60–80% token spend reduction. — https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing
- **Kalvium Labs (2026):** Teams that run Claude for synthesis and GPT-4o for structured-output turns within the same workflow outperform teams locked to a single model. Eval infrastructure is what makes this call honest. — https://www.kalviumlabs.ai/blog/llm-selection-for-production/
- **FinOps for AI analysis (2026):** Per-token prices fell 280x (2022–2024); enterprise GenAI spend climbed $2.3B → $37B over the same period (Jevons Paradox in action). — https://rickpollick.com/blog/finops-for-ai-llm-cost-governance
- **AI Agent Framework Decision Guide:** 3-second decision: CrewAI for demos, LangGraph for production (best cost predictability + observability), AutoGen for complex multi-agent reasoning, raw Claude API to avoid framework overhead entirely. — https://github.com/benconally/ai-agent-framework-decision-guide

## Gotchas

- **DeepEval's `ContextualPrecisionMetric` silently degrades** when you omit ground-truth contexts — it falls back to "LLM guesses what the context should have been." Use RAGAS context precision for RAG workflows instead.
- **Running RAGAS on every production trace** scales cost linearly with traffic. Sample at 1–5%; do not evaluate 100% of calls.
- **Judge model drift** — if you swap the judge LLM mid-production, historical scores become incomparable. Pin the judge or track version as a dimension.
- **Cheaper model migration without eval** is how bills triple. Always A/B on a representative slice of production traffic before cutting over a production model.
- **Context window size is a trap.** Retrieval beats stuffing for most real-world tasks. A 2M-token context window does not make retrieval unnecessary — it makes retrieval architecture more important.
