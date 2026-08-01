# S-1981 · The Token Budget Stack — When Your Architecture Burns More Than Your Model Costs

*Your model costs $0.003/1K tokens. Your agent costs $4.20 per customer support ticket. The model price is irrelevant — what matters is how many tokens your architecture burns per decision, and most teams are spending 10x what they need to because they optimized the wrong variable.*

## Forces

- **Architecture costs dwarf model costs.** MightyBot (July 2026) measured identical workloads: single-pass = $1/task, iterative agent = $4-6/task, voting ensemble = $12-20/task. The same model. The same input. Three architectures, 4-20x cost spread. Teams that negotiate model discounts while ignoring architecture are optimizing the wrong lever.
- **Context snowballing turns linear work into quadratic costs.** Every agent loop step re-sends the full conversation history. A 20-step workflow doesn't cost 20x a single-pass — it costs progressively more as the context grows with each step. TokenPilot (Xu et al., Zhejiang Univ., Jun 2026) shows validated compaction enabling O(n) token growth vs O(n²) naive approaches, cutting inference costs by up to 87% in continuous task streams.
- **80% of AI cost overruns are architectural, not pricing.** Pickaxe (Aug 2026) analysis: most teams blame model pricing when their agent bills explode, but 80% of budget overruns trace to architectural inefficiency — redundant retrieval, no early-exit gates, over-retrieval, and missing circuit breakers.
- **Input tokens are the hidden budget killer.** Agents burn more on input context than output. A 50-tool agent that loads all definitions on every request consumes 5-7% of its context budget before the user's message arrives (MLMastery, Jul 2026). The model is spending tokens to figure out which tool to use before it can even answer the question.

## The move

Design for cost-per-decision, not per-token-rate. The three architectural levers that dominate your bill:

**1. Architecture selection — the biggest multiplier.**

| Pattern | Cost/Decision | When to use |
|---------|-------------|-------------|
| Single structured pass | $0.10-1.00 | Linear tasks, clear output schema |
| Iterative agent (loop) | $1.00-8.00 | Multi-step, non-linear, variable paths |
| Voting ensemble (N agents) | $3.00-20.00 | High-stakes, quality-critical only |

The same model at identical per-token pricing produces 4-20x cost spread depending on which pattern you chose. Default to single-pass. Graduate to agents only when the task genuinely requires iteration or tool use with variable paths.

**2. Context engineering — the biggest untapped lever.**

- **Retrieve, don't dump.** Feed only the minimum data needed per step. Context engineering reduces token usage 60-80% regardless of model — more than model-tier differences, and it's free.
- **Chunk retrieval to the task horizon.** Fetch only what the current step needs, not the full conversation or document corpus. TokenPilot's dual-granularity framework aligns text reduction with prompt cache behavior simultaneously.
- **Early-exit gates.** Add a confidence or completion check before every loop iteration. If the task is 80% done, don't re-run the full context through the model again.

**3. Budget governance — the circuit breaker.**

- **Set per-task token limits, not per-month budgets.** A budget cap of $10K/month tells you nothing mid-task. A per-turn limit of 2,000 output tokens with a hard stop prevents runaway loops from generating $47,000 invoices.
- **Three-tier model routing.** Route by task complexity: small model (cheap, fast) for routing/deduplication, medium model for standard tasks, large model only for the hard cases. TrueFoundry (2026) reports 60-80% token spend reduction from full-stack routing + caching + compression.
- **Cost attribution by task type.** Tag every run with task category (classification, generation, reasoning, retrieval). Without attribution, you cannot identify which task type is burning the budget. With attribution, you can route expensive task types to cheaper paths.

**4. The budget review cadence.**

Run a cost-per-decision analysis monthly. Take the total tokens spent in the period, divide by decisions made. If cost/decision is trending up, check three things: (a) is context growing faster than task complexity?, (b) are more tasks falling into the iterative agent pattern than necessary?, (c) is retrieval returning more documents than the top-K needed?

## Attribution

MightyBot.ai, "The Token Economics of AI Agents in 2026" (Jul 2026) — measured cost-per-decision across three architectures. Pickaxe, "The Real Cost of AI Agents: Token Economics" (Aug 2026) — 80% architectural inefficiency finding. TokenPilot (Xu et al., Zhejiang Univ., arXiv, Jun 2026) — O(n) vs O(n²) context growth, 87% cost reduction. arXiv:2603.07670 "Memory for Autonomous LLM Agents" (2026) — five mechanism families for memory management. MLMastery "Tool Selection in AI Agents" (Jul 2026) — 5-7% context consumed by tool definitions.
