# S-680 · The Multi-Agent Cost Multiplier — and How Teams Stop Bleeding Money

Multi-agent architectures compound costs in ways that aren't obvious from single-agent prototyping. A 4-agent pipeline that looks reasonable can hit $47,000 in 11 days from a single infinite loop. Teams that survive production implement three non-negotiable controls before launch.

## Forces

- **Token volume compounds across agents.** Each agent in a pipeline adds its own input/output context — a 4-agent LangGraph orchestrator-worker workflow commonly runs 5-8× more tokens per task than a single-agent equivalent. Token prices fell ~80% YoY (2024–2025) but agent workloads grew faster, so absolute spend still doubled ($3.5B → $8.4B globally).
- **Lower token count ≠ lower cost.** The 2026 Agent Framework Benchmark found CrewAI averaged 22,800 tokens/query at $0.15/task while AutoGen averaged 24,200 tokens at $0.35/task — AutoGen's higher per-token cost (complex models by default) overwhelmed CrewAI's comparable token volume.
- **Enterprise AI ops cost floor is high and invisible until hit.** The average enterprise now spends $85,521/month on AI operational costs (2025), and most teams don't have observability granular enough to catch the $15-in-ten-minutes incidents that precede the $47,000 ones.
- **The infinite loop is the #1 cost failure mode.** An unbounded multi-agent A2A loop (agent-to-agent messaging with no step ceiling) ran 264 hours at one company — no circuit breaker, no human alert in time. A hard step budget would have capped it at ~$50.
- **60–85% of spend is recoverable** through prompt caching, model routing, and budget circuit breakers. Teams discover this only after the first runaway.

## The move

**Three controls you implement before going multi-agent in production:**

- **Hard step-budget circuit breakers on every agent loop.** Set a maximum number of LLM calls per task (start at 20–50 depending on complexity). Track this in the state machine, not as an alert. An alert requires human intervention; a circuit breaker doesn't. This alone prevents runaway costs — it doesn't optimize them.
- **Intelligent model routing by task type.** Route simple retrieval, classification, and formatting to cheaper models (Haiku-class, ~$0.25/M input tokens). Reserve Opus/Sonnet-class models for reasoning, quality gates, and final synthesis. Route maps are configurable YAML or JSON — not hardcoded in the agent logic.
- **Prompt caching as the default, not the exception.** Both Anthropic and OpenAI now offer significant discounts (75–90%) on cached tokens. Multi-agent systems have high repetition by design (system prompts, shared context, tool schemas). Structure prompts to maximize cache hits: static prefix + dynamic body. Reuse the same tool schema definitions across agents where possible.

**Bonus: Cost attribution by agent.** Tag every LLM call with `{agent_id, task_type, session_id}` in the completion metadata. This lets you identify which agent or workflow is driving 80% of your spend — usually not the one you'd guess.

## Evidence

- **Benchmark study (2026):** Multi-agent systems cost 5–15× more per task than single-agent equivalents; CrewAI averaged $0.15/query at 22,800 tokens, AutoGen $0.35/query at 24,200 tokens, LangChain $0.18/query at 8,200 tokens — model choice dominates over token volume. — [MHTECHIN Cost Optimization Guide 2026](https://www.mhtechin.com/support/cost-optimization-for-autonomous-ai-agents-the-complete-2026-guide)
- **Enterprise ops data:** Model API spend grew $3.5B → $8.4B (late 2024 to mid-2025); average enterprise AI ops cost is $85,521/month; 60–85% of spend is recoverable through caching, routing, and budget enforcement. Runaway loop incident: $47,000 over 264 hours — bounded by prompt caching and step budgets after the fact. — [Zylos Research: AI Agent Cost Engineering](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Real production regret:** One LangChain multi-agent pipeline ran an unbounded A2A loop for 264 hours with no budget ceiling — alerts required human intervention; the circuit breaker that would have saved it didn't exist. — [Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

## Gotchas

- **Routing logic that lives inside agent prompts breaks deterministically.** If your "route to cheap model" logic is written as a prompt instruction, the agent may ignore it when busy or under load. Route at the infrastructure layer — the SDK or API call — not the prompt.
- **Cache hit rate drops as you approach zero-shot prompts.** Caching only helps when prompts repeat. Fully dynamic prompts (unique every turn) get no cache benefit. Structure system prompts to be maximally static.
- **Step budgets kill valid long-horizon tasks.** A budget of 20 steps is too low for multi-hop reasoning across 6 document types. Calibrate by running your worst-case task through the pipeline and measuring step count, then set the budget at 1.5× that.
- **Cost observability is useless without per-task attribution.** Aggregate spend dashboards hide which workflow is expensive. Tag at the call level.
