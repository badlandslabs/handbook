# S-1920 · The Intra-Agent Router Stack — When Your Agent Pays Frontier Prices for a Job Haiku Could Do

Your agent runs a 12-step ReAct loop to answer a support question. Every step — the intent classification, the tool selection, the format check — goes to Claude Opus. Opus correctly identifies the user's intent in step 1, correctly picks the right tool in step 2, and correctly formats the response in step 12. It was also 60× more expensive than necessary on steps 1 and 2. The router that would have fixed this isn't hard to build. It's not built because nobody treats each step as an independent routing decision.

## Forces

- **Agent loops multiply LLM calls.** A single agent task generates 3–10× more calls than a chatbot task. Each step adds context tokens and cost. An unconstrained software-engineering agent averages $5–8 per task in API fees alone. The per-step cost surface is 3–10× the per-task surface.
- **Step complexity is bimodal.** Within a single agent turn, intent classification (step 1) and tool selection (step 2) are structurally trivial — a handful of tokens, predictable output schema, no reasoning required. The multi-hop reasoning step (step 3) genuinely needs frontier. Most teams hardcode one model for all steps; they overpay on the trivial ones and have no principled way to upgrade on the hard ones.
- **The cost-capability spread is extreme.** At 2026 pricing, the spread between a nano model (DeepSeek V4 at $0.44/M input tokens) and a frontier model (GPT-5.5-pro at $30/M) is ~68×. Even within a single provider's lineup, Haiku vs. Opus is 20–60×. A router that routes 70% of calls to the cheaper tier saves 56–69% on the blended rate — before any other optimization.
- **Per-step routing needs its own eval.** A bad router silently degrades quality on hard steps. Teams that skip router evaluation end up with a false sense of savings: the easy steps go fine, the hard steps silently fall back to the cheap model, and the failure shows up in production as silent quality degradation with no attribution.

## The Move

Route each step within the agent loop independently, based on the step's structural complexity — not on vibes or static config.

**1. Split the loop into step types with different model requirements.**

```
Intent classification  → nano/haiku tier  (structured, short input, predictable output)
Tool selection         → fast tier        (few-shot examples, deterministic)
Reasoning / planning   → frontier tier    (multi-hop, long context, complex logic)
Response synthesis     → medium tier      (coherence, formatting, tone)
Error recovery         → frontier tier    (diagnostic reasoning, novel errors)
```

**2. Use the cheapest model that satisfies the step's structural contract.**
The decision rule is not "how hard does this seem?" but "what model does this *type* of step consistently require?" Intent classification has been solved; route it to the cheapest model that passes its eval. Reasoning has not; route it to frontier.

**3. Attach a confidence gate before the routing decision.**
For steps where model requirement varies (e.g., a factual lookup vs. a novel synthesis), run a cheap classifier (embedding-based or fine-tuned DistilBERT) that scores the query complexity. Route to cheap if confidence > τ, escalate to frontier if < τ. The threshold is set by the router's own eval, not by intuition.

**4. Budget the router itself out of the savings.**
A semantic router adds 10–40ms of latency and one small embedding call per agent turn. The embedding call costs $0.02–0.10 per 1M tokens. If the router saves $0.50 per turn by routing 8 of 10 steps to a cheap model, the router overhead is noise.

**5. Track per-step cost attribution in production.**
Log which model handled each step type. Aggregate by step type to find where the budget actually goes. Most agents have a long tail of cheap steps (classification, selection) that dominate call count but consume a small fraction of total cost — and a small number of expensive steps (reasoning) that dominate cost but are a fraction of call count. The router's ROI is visible only when step-level attribution exists.

## Evidence

- **Research paper (arXiv:2508.12631):** Avengers-Pro — a test-time routing framework that embeds and clusters queries, then routes each to the most suitable model by performance-efficiency score. Across 6 benchmarks and 8 leading models (GPT-5-medium, Gemini-2.5-pro, Claude-opus-4.1), achieved **+7% accuracy improvement over the strongest single model** and **−27% cost reduction while maintaining equivalent accuracy**. Routing outperformed any single model by exploiting complementary strengths. — [arXiv:2508.12631](https://arxiv.org/abs/2508.12631)

- **Open-source tool (GitHub, 920 stars):** WorkWeave Router — a drop-in proxy for Anthropic/OpenAI/Gemini that acts as an agentic router, using an Avengers-Pro-derived tiny embedder to pick the optimal model per request in <50ms. Claims **40–70% token cost savings** with no noticeable quality or velocity difference for coding agents. — [github.com/workweave/router](https://github.com/workweave/router) (HN Show HN, 216 points)

- **YC S26 launch (HN):** Tokenless — an API gateway that routes AI agent traffic between models turn-by-turn, trained custom models to predict LLM performance per step. Novel approach: queries multiple models simultaneously and uses their progress signals to make the routing decision, with early cutoff of underperforming models. — [news.ycombinator.com/item?id=49099143](https://news.ycombinator.com/item?id=49099143)

- **Peer-reviewed benchmark (RouteLLM, Berkeley/Anyscale/Canva):** Routers trained on human preference data across MT Bench, MMLU, and GSM8K. Achieved **85% cost savings on MT Bench at 95% of GPT-4 quality** using only 14% of queries routed to the strong model. Matrix factorization and similarity-weighted ranking routers both outperformed commercial alternatives (Martian, Unify AI). — [arxiv.org/html/2406.18665v4](https://arxiv.org/html/2406.18665v4)

## Gotchas

- **Routing at the step level requires step-type classification first.** Before you can route, you need to know what step type you're in. If your agent loop doesn't have explicit step-type boundaries, the router falls back to routing on prompt length or keyword heuristics — both fragile. Model the loop structure before you model the routing.
- **The quality regression is invisible until you eval it.** A router that silently sends 30% of hard reasoning steps to a cheap model will pass the easy-query eval and fail silently on the hard queries that matter. Eval the router on the hard 20% of your query distribution, not the median. If quality on the hard set drops by more than 5%, raise the confidence threshold or remove those step types from cheap routing.
- **Savings projections assume calibration.** Vercel's analysis of routing strategies found: "Calibration determines the result. Tune the router to avoid any quality regression, and it keeps routing most queries to the expensive model, so the savings evaporate. Measure the actual fraction of production traffic that lands on cheaper models before you project anything based on list-price differences."
- **The router becomes a single point of failure.** If the router endpoint goes down, your agent is dead in the water — even if the underlying model APIs are healthy. Build a deterministic fallback (hardcode the frontier model) that activates on router errors, not just on quality regressions.
