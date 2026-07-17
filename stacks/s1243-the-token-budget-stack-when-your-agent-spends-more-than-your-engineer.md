# S-1243 · The Token Budget Stack: When Your Agent Spends More Than Your Engineer

You deployed an agent to handle customer support tickets. Three weeks later, a $47,000 invoice arrives. Four agents entered a feedback loop, ran for 11 days, and nobody noticed until the bill came in. The demo was cheap. The production agent is not — because agents don't call the LLM once, they call it dozens of times, and each call re-transmits the growing conversation history.

## Forces

- **Agents are compound-cost systems.** A 10-step run doesn't cost 10× a single call — it costs 25–50×, because the input context grows with every step. N-step agent runs have O(N²) input token cost, the "context accumulation problem."
- **Token prices are falling while per-task token counts are exploding.** GPT-4o-mini is 33× cheaper than GPT-4o, but an unconstrained agent burns 5–30× more tokens per task than a chatbot. Unit price drops while unit volume climbs — total spend goes up.
- **Agents don't stop on their own.** Chatbots fail gracefully when they produce a bad answer. Agents loop. Each failed tool call can trigger a retry that re-sends the full conversation history plus all previous tool outputs — one bad result can 5× your costs on a single task.
- **Cost visibility lags execution by days.** Most teams discover runaway spend through invoices, not dashboards. By the time you see the bill, the damage is done.
- **Cheaper models alone don't solve the problem.** Routing to GPT-4o-mini for simple steps helps, but without budget enforcement and loop detection, a looping agent will happily burn $8/task on cheap tokens instead of $8/task on expensive ones.

## The Move

The token budget stack applies cost controls at multiple layers that compose:

- **Budget enforcement at the infrastructure level, not the prompt level.** Set hard token/cost caps per session or per run that terminate or pause the agent before the next API call completes — not an alert that fires after spend occurs. At least one documented production incident involved four LangChain agents looping via the A2A protocol for 11 days at $47,000 before human detection.

- **Loop detection via semantic similarity.** Beyond simple step-count caps, compare consecutive agent states (action sequence, observation hash, or tool-call signature) using cosine similarity on embeddings. If the agent is performing semantically identical work across consecutive turns, terminate — even if tool result text differs. This catches the "retry with slightly different wording" pattern that step-count limits miss.

- **Context truncation as a first-class budget lever.** Proactively summarize or truncate conversation history before the context window fills. Don't wait for the model to hit the limit — truncate at 60–70% of the context budget and inject a "you have been working on task X; here is what you know so far" summary. This breaks the O(N²) accumulation directly.

- **Model routing by task complexity classification.** Classify each step as simple (classification, extraction, routing — 60–70% of calls) vs. complex (reasoning, multi-step planning, creative synthesis — 30%) before routing to a model. At 2025–2026 pricing, the difference between GPT-4o-mini ($0.15/M input) and GPT-4o ($5/M input) is 33×. Teams with working classifiers report 50–65% cost reduction with under 3% quality degradation.

- **Prompt caching to eliminate repeated prefix costs.** Both OpenAI and Anthropic offer prompt caching at ~90% discount — send the fixed prefix (system prompt + tool definitions + task context) once, and subsequent calls reference it. This is the fixed-cost component that compounds most on multi-turn agent runs; it must be targeted before variable-cost optimizations.

- **Semantic caching for duplicate-query deflection.** Embed incoming queries and store response vectors. If a new query has cosine similarity > 0.92 to a cached query, return the cached response. Engineering teams report 30–40% cache hit rates in production, directly eliminating LLM calls at zero quality cost. One Reddit practitioner documented an 80% cost reduction from this technique alone for a Q&A workload.

## Evidence

- **Engineering blog (Neel Mishra):** Documented the O(N²) context accumulation problem and the code-level architecture for a `ContextManager` that checks budget before each step, routes to the cheapest adequate model per step, and has a `FORCE_SYNTHESIS` / `HARD_STOP` policy — emergency synthesis at soft budget, hard termination at the cap. — [neelmishra.github.io/blog/mlops/llm-agents/agent-cost-management.html](https://neelmishra.github.io/blog/mlops/llm-agents/agent-cost-management.html)

- **Enterprise AI FinOps analysis (Inductivee, Nov 2025):** Quantified the 33× cost gap between GPT-4o ($5/M) and GPT-4o-mini ($0.15/M), showed that a routing classifier correctly handling 60–70% of queries reduces costs 50–65%, and that combined with semantic caching targeting 30–40% hit rates, 70–80% total cost reduction is achievable. — [inductivee.com/blog/enterprise-llm-cost-optimization](https://inductivee.com/blog/enterprise-llm-cost-optimization)

- **Case study (CloudAtler, Aug 2025):** Named and described the "Infinite Loop of Death" — an agent stuck retrying a failing task, burning through thousands of dollars. Documented two mitigation patterns: (1) step-count limits that cap retry iterations, and (2) semantic similarity checks that detect when consecutive turns are producing equivalent states. — [cloudatler.com/blog/the-50-000-loop-how-to-stop-runaway-ai-agent-costs](https://cloudatler.com/blog/the-50-000-loop-how-to-stop-runaway-ai-agent-costs)

- **Industry analysis (Zylos Research, Apr 2026):** Found that agents make 3–10× more LLM calls than chatbots, that unconstrained software engineering agents cost $5–8 per task in API fees alone, and that teams applying full optimization stacks (routing + caching + budget enforcement) report 60–80% token spend reductions. — [zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)

- **Practitioner report (Reddit r/SaaS):** A developer described building a semantic cache for their Q&A workload — embedding incoming prompts and returning cached responses for semantically similar queries — achieving 80% cost reduction because large fractions of prompts were variations of the same question ("how do I reset my account?" vs. "can I start over?"). — [reddit.com/r/SaaS/comments/1k112nm](https://www.reddit.com/r/SaaS/comments/1k112nm/how_i_helped_my_company_cut_llm_costs_by_80_by)

## Gotchas

- **Setting a cost alert is not cost enforcement.** An alert fires after spend occurs. Infrastructure-layer budget enforcement stops the agent before the next LLM call. The 11-day, $47,000 incident happened despite monitoring that existed — alerts don't prevent, they report.
- **Cheaper models plus loop detection beats cheap models alone.** A looping agent burning cheap tokens is still a budget catastrophe. Model routing and token budget enforcement must be deployed together.
- **RAG token bloat multiplies agent costs silently.** A typical RAG query adds 2,000–8,000 tokens of context before the actual question. With a 10-message chat history, you're sending 15,000+ tokens per query — on every turn, compounding. Count the full prompt when estimating agent run costs.
- **Prompt caching mechanics differ between providers.** OpenAI and Anthropic both offer ~90% discounts, but the mechanism and minimum cache key length differ. Anthropic requires longer prefix segments for caching to activate reliably — test against real production prompts, not synthetic ones.
- **Concurrent users break single-user cost estimates.** A workflow that costs $0.05 in testing costs $50/hour in production because of concurrent users, retry logic, and streaming overhead. Budget for the parallel case from the start.
