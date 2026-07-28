# S-1756 · The Token Budget Stack — When Your Agent's Costs Are Unworkable at Scale

A single agent run looks cheap. One conversation at $0.14 does not raise eyebrows. But scale to 3,000 employee users, each running 20 multi-step tasks a day, and the invoice hits $500K/year. The problem is not cost-per-token — it has fallen 30–60% per year. The problem is the shape of agentic workloads: a task that starts at 5K tokens balloons to 80K–200K after 20 steps, because every step resends the system prompt, tool definitions, conversation history, and prior tool results. Cost rises quadratically, not linearly.

## Forces

- **Agent loops multiply token consumption 50–500x** over a basic chatbot. Each loop step re-sends the full context. A research agent running 15 turns on 3,000 tokens per turn accumulates 45,000+ input tokens per run — before output.
- **Per-task cost at scale is fatal.** SWE-Bench-class coding agents average $2.40/successful task at current pricing. A Singapore fintech burned $87,000 in 11 days when an agent loop recursively re-invoked itself on tool failures. Unconstrained agents are budget emergencies waiting to happen.
- **The unit economics work only with optimization.** Teams applying the full optimization stack report 60–80% token spend reductions. An unoptimized $0.25/task run drops to $0.04–0.06. That is the difference between a viable product and a line item that reaches the board.
- **The cost trap is invisible without measurement.** The first sign of trouble is not a warning — it is an invoice. Cost-per-task, cache hit rate, and model downgrade rate need to be first-class production metrics, not post-mortem surprises.
- **Cheaper model routing is proven but underused.** RouteLLM (peer-reviewed, ICLR 2025) hit 85% cost savings at 95% of GPT-4 quality in controlled benchmarks — needing the strong model on only 14% of queries. Most teams still route everything to their most capable model.

## The Move

Stack five optimization levers. None alone is sufficient; together they collapse per-task cost by 60–80%.

**1. Model routing — send each request to the cheapest model that can handle it.**
Route 60–80% of production traffic to small/fast models (Haiku, Gemini Flash, GPT-4o-mini). Use a classifier, embedding similarity, or LLM-as-judge to decide. Reserve Opus/Sonnet-level models only for tasks that actually need them. RouteLLM benchmarks show 85% savings at 95% quality on MT Bench. In production, expect 40–85% bill reduction depending on task mix.

**2. Prompt caching — eliminate redundant prefill computation on shared prefixes.**
OpenAI, Anthropic, and Gemini all offer prompt/caching that gives up to 90% discount on repeated system prompts and tool definitions. A research agent running 15 turns with a 3,000-token system prompt: before = 45,000 tokens per run; after with caching = ~18,000 cached reads. Cache hit rate target: >60% for prefix caching. Note: prompt caching reduces input-side costs but does not eliminate output token charges.

**3. Context pruning — aggressively discard tool results after consumption.**
Agents accumulate full tool outputs across turns. A web search returning 5,000 tokens that contributed 200 useful tokens to the final answer still costs the full 5,000 on every subsequent step. Prune aggressively after the LLM consumes the result: extract only what was used, discard the rest. Target: 75% reduction in accumulated context tokens.

**4. Budget governance — hard caps per-task and per-session.**
Set max_tokens per step and hard budget limits per task. The Singapore fintech case is the canonical warning: no per-task cap means a recursive loop can run indefinitely. Budget enforcement is a production requirement, not an optional polish layer.

**5. Batch inference scheduling — defer non-urgent tasks to 50% off batch endpoints.**
OpenAI and Anthropic offer batch APIs at 50% discount with async turnaround. Route throughput-heavy, latency-tolerant tasks (report generation, bulk analysis, batch document processing) to batch. Keep interactive tasks on realtime.

## Evidence

- **Research survey:** Enterprise LLM spending reached $8.4B in H1 2025, with 96% of enterprises reporting costs exceeding initial projections. AI agents make 3–10x more LLM calls than chatbots, and unconstrained agents on software engineering tasks cost $5–8 per task in API fees alone. — *AgentMarketCap, April 2026* — https://agentmarketcap.ai/blog/2026/04/08/agent-token-cost-optimization-production-inference-spend
- **Peer-reviewed routing benchmark:** RouteLLM (ICLR 2025) achieved 85% cost savings on MT Bench while retaining 95% of GPT-4 quality, routing to the strong model on only 14% of queries. — *Digital Applied, June 2026* — https://www.digitalapplied.com/blog/llm-model-routing-2026-cost-quality-optimization-engineering-guide
- **Production cost case study:** A typical research-and-summarize agent (15 turns, multiple sources) reduced cost from ~$0.14/task to ~$0.04/task (71% reduction) through model tier routing + prompt caching + context pruning + batch calls + max_tokens enforcement. — *AI University, 2025* — https://theaiuniversity.com/docs/cost-optimization/token-optimization
- **HN discussion (306 points, 137 comments):** Community debate on Toby Ord's analysis of agent hourly costs — o3 running at $350/hr with ~50% task failure rate was cited as economically untenable for most production use cases. — *Hacker News, 2025* — https://news.ycombinator.com/item?id=47778922

## Gotchas

- **Prompt caching does not eliminate output token costs.** It only discounts the prefill/input side. Semantic caching (Redis, custom embeddings) can bypass the LLM entirely on cache hits — saving both input and output — but requires matching logic and still needs a fallback to the LLM for misses.
- **Router overhead is real but small.** Rule-based routing adds <1ms, embedding-based ~5ms, ML classifiers 50–100ms. Against typical LLM response times of 500–2,000ms, this is negligible — but it must be measured, not assumed.
- **Routing on vibes is the silent quality killer.** A cheap model that "seems fine" in a demo can quietly degrade a downstream metric for weeks. Validate routing decisions against business metrics (resolution rate, thumbs-up, downstream conversion), not just benchmark scores.
- **Per-task budgets need to account for success rate.** A $0.05/task budget that succeeds 60% of the time costs more per *completed* task than a $0.10/task budget that succeeds 95% of the time. Track cost per successful task, not just cost per task.
