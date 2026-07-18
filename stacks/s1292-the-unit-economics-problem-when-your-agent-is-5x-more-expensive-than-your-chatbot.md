# S-1292 · The Unit Economics Problem — When Your Agent Is 5x More Expensive Than Your Chatbot

Your LLM API costs tripled last quarter. Per-token pricing dropped 67% during the same period. You didn't add users. The model didn't change. You shipped an agent — and it turns out the 20 sequential LLM calls your agent makes per task cost more than the 1 call a chatbot makes, even when each call is cheaper. Token prices fell. Volume exploded. The bill went up anyway.

## Forces

- **The agentic multiplication effect.** A simple chatbot task costs $0.012 (1 call, ~800 tokens). A basic 5-step agentic task costs $0.18 — 15x more. An advanced 10-turn ReAct loop with tool calls and memory: $1.50-$3.00+ per task. The architecture compounds the per-call cost reduction into a net cost increase.
- **Context accumulation is a silent multiplier.** Each tool result appends to the context window, which is then re-sent in full on the next turn. A 10-step agent re-transmits its accumulated context 9 times. A 2,000-token initial prompt balloons to tens of thousands of output tokens by task completion.
- **System prompt repetition.** Production agents carry 2,000–8,000 tokens of system prompt on every call. Without prefix caching, this is a fixed overhead on every single API call — billed repeatedly.
- **Output tokens are the hidden budget burner.** Output tokens cost 3–5x more than input tokens across all major providers. Agents that generate reasoning traces, tool call arguments, and verbose tool outputs consume disproportionate output budget.
- **The monitoring gap.** 96% of enterprises report LLM costs exceeded initial projections. Most teams discover the problem only when the bill arrives — not when the architecture is designed.
- **Failure is expensive in a new way.** A traditional software bug crashes or returns a bad value. An agent bug loops, re-tries, and burns tokens until something external gives out. A single runaway loop cost one fintech team $47,000 in 11 days.

## The move

Treat cost as a first-class architectural constraint — not a billing line item to optimize later. The full stack:

- **Instrument before touching anything.** Log cost per request, per feature, per user tier, per model. Break down input vs. output token split. Without visibility, every optimization is guesswork. A `CostRecord` interface tracking `requestId`, `feature`, `model`, `inputTokens`, `outputTokens`, `costUsd`, `cachedHit`, `durationMs` is the minimum viable observability layer.
- **Implement Anthropic-style prompt caching.** Cache the reusable prefix of your system prompt and tool definitions (2,000–8,000 tokens) across calls within a session. Anthropic's extended TTL (up to 1 hour) makes this viable for most production agent flows. Delivers ~90% discount on the cached portion.
- **Add semantic caching with embeddings for near-duplicate requests.** Store recent requests as vectors; serve cached responses for semantically identical queries. Cuts repeated research/summarization calls by 40–70%. Be careful: semantic matching can conflate requests that differ on critical constraints (e.g., "CPC" vs. "CPM"). Validate cache keys against lexical constraints for correctness-sensitive requests.
- **Route by task complexity, not habit.** Classify incoming tasks by complexity tier (extraction → routing → reasoning → creation) and route to the cheapest model that handles that tier reliably. Average enterprise now runs 4.7 distinct models per account — up from 2.1 in Q1 2025. Teams using tiered routing report 60–75% blended savings.
- **Enforce token budgets per task.** Set hard caps on input context size, output length (`max_tokens`), and maximum tool call count per session. Couple with cost-per-task alerts. This is the brake that prevents runaway loops from reaching $47,000.
- **Prune aggressively.** After each tool call, strip the context of tool outputs that are no longer relevant. A research agent reading 10 sources doesn't need all 10 raw HTML pages in context for the final synthesis — it needs the extracted facts. The `rtk-ai/rtk` benchmark shows 60–90% token waste from passing raw command output.
- **Batch independent operations.** When multiple tool calls are independent (fetch data from N sources, analyze N files), send them as a single batched API call or parallelize with concurrency limits. Eliminates per-call overhead and amortizes system prompt costs.
- **Capture the sweet spot.** Frontier models have a cost-per-hour sweet spot where capability and efficiency align. o3 hits $350/hour at its maximum 1.5-hour horizon — exceeding human rates — while succeeding only ~50% of the time at that horizon. A multi-agent pipeline using o3 for planning and a smaller model for execution typically outperforms a single o3 call at 20% of the cost.

## Evidence

- **Primary research / Analysis:** A fintech team's two LangChain agents entered an infinite conversation cycle for 11 days, undetected by monitoring. Final bill: $47,000 from a $200/month budget. Root cause: no per-task cost cap, no max-iteration limit, no cost alerting. — [AgentMarketCap, "AI Agent Token Consumption Gap," April 2026](https://agentmarketcap.ai/blog/2026/04/12/ai-agent-token-consumption-gap-enterprise-agentic-workloads)
- **Engineering blog / Benchmark:** A production research-and-summarize agent run: $0.14/task before optimization, $0.04/task after applying prompt caching, context pruning, model routing (Haiku for routing, Sonnet for synthesis), batched calls, and output constraints. 71% reduction. — [AI University, "Token Optimization," 2026](https://theaiuniversity.com/docs/cost-optimization/token-optimization)
- **Market research / Survey:** Enterprise LLM spending reached $8.4B in H1 2025, with 96% of enterprises reporting costs exceeded projections. Teams applying model routing, semantic caching, and context optimization report 60–80% token spend reductions. Average enterprise account runs 4.7 distinct models — up from 2.1 in Q1 2025. — [Zylos Research, "AI Agent Cost Optimization," April 2026](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
- **Community benchmark:** Token waste from passing raw command output (instead of extracted facts) accounts for 60–90% of unnecessary token spend in AI coding agents. AI coding agents overspend by 60%+ compared to optimized equivalents. — [awesome-agent-cost-optimization, GitHub](https://github.com/aptratcn/awesome-agent-cost-optimization)

## Gotchas

- **Semantic caching fails on constraint-sensitive requests.** Two prompts that differ only in a single critical term (e.g., "revenue in USD" vs. "revenue in EUR") will match semantically and return wrong results. Use lexical validation for correctness-critical cache keys.
- **Output constraint is a double-edged sword.** Setting `max_tokens` too low truncates agent reasoning mid-thought, creating corrupt context for the next turn. Calibrate against the 95th-percentile output length for each task type.
- **Prompt caching requires stable prefixes.** If your system prompt changes frequently (per-user preferences, dynamic instructions), the cache hit rate collapses. Design prompts with a stable base layer and a mutable overlay.
- **Cost-per-task alerting catches loops but not slow burns.** A single runaway loop generates a large cost spike that's easy to alert on. A 20% context overhead that applies to every request is invisible to spike-based alerting — it requires per-request cost tracking.
- **The per-token price drop is a trap.** Per-token prices fell 85% since GPT-4 launch. But agentic architectures consume 10–100x more tokens per task than chatbots. Most teams see costs rise despite cheaper tokens. The price drop is real; the volume increase is faster.
