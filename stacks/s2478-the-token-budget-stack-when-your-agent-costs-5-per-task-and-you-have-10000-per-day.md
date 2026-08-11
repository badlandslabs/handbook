# S-2478 · The Token Budget Stack — When Your Agent Costs $5 Per Task and You Have 10,000 Per Day

Enterprise LLM spend hit $8.4B in H1 2025, with 96% of teams exceeding their projections. The culprit is not model pricing — it is the arithmetic of multi-turn agents: every API call replays the full conversation history, and a single software task can consume 230K tokens. Your agent is not expensive because the model is expensive. It is expensive because it keeps rereading everything it already knows.

## Forces

- **The 50x token multiplier.** Agents consume roughly 50x more tokens per session than a code-chat interaction (Vantage, 2026). A typical agentic session runs ~1M input tokens across 50 turns with a 25:1 input:output ratio. Every turn adds its own input overhead before producing output.

- **The cost compound.** Unconstrained agents cost $5–8 per software task in API fees alone. At 10,000 tasks per day, that is $50K–$80K daily. A single 100-agent deployment (OpenClaw) ran $1.3M in 30 days — 603B tokens, 7.6M requests.

- **Token count vs. token cost is not the same problem.** HN user benchmark testing found that pre-indexing — adding structured reference data upfront — increased total tokens processed by 20% (19.6M → 23.4M) but cut costs by 58% ($16.29 → $6.89). Cache hit rate and token tier matter more than raw token count.

- **Context rot is invisible.** As context grows, models exhibit the "lost-in-the-middle" effect — attention concentrates at the beginning and end while middle content becomes unreliable. The model does not error out. It just quietly ignores instructions buried at turn 12 of 30. Critical threshold: 60–70% context capacity utilization, where performance degrades silently before hitting the hard limit.

- **The o3 at full capability costs $350/hour** — exceeding the fully-loaded cost of a senior engineer (Toby Ord, Dec 2025). For tasks near the current capability plateau, frontier agents routinely cost 10–100x more per hour than human labor.

## The Move

Build an explicit token budget stack before you scale, not after you get a $50K bill from LangChain.

- **Prompt caching as the first lever.** Anthropic's prompt caching delivers a 90% discount on cached input tokens. Cache the system prompt, tools schemas, and any stable reference context. For repeated-task workloads (code review, support triage), this alone cuts costs 60–80%. Do not leave it disabled — it is the single highest-ROI change available.

- **Observation masking over truncation.** Parcle.ai (HN Show, 2025) and academic research (Lindenbauer et al., arXiv:2508.21433) independently found that selective removal of repeated context — keeping unique observations, dropping redundant replays — achieves >60% token reduction with no measurable accuracy loss. Do not naively truncate from the middle; identify and preserve information density.

- **Token budget per step with hard abort.** Set a per-step token cap that forces early exit or escalation when exceeded. This is the guardrail that prevents the LangChain-style infinite loop ($47K in 11 days, Nov 2025). Budget should be expressed in expected-cost-per-task, not total tokens, since costs vary by model and tier.

- **Model routing by task complexity, not by cost.** The optimal stack uses 4–7 distinct models routed by task signature. Cheap models (Qwen 3.5 at $0.05–0.10/task) handle extraction, classification, and formatting. Capable models handle reasoning, debugging, and multi-step synthesis. Open-source models now capture 38% of enterprise token volume (first time crossing 1/3 threshold, RockB, May 2026). Route on capability match, not price.

- **Pre-index before you iterate.** The benchmark finding that +20% tokens → −58% cost via pre-indexing (HN 47326918) is counterintuitive but robust: spend tokens on structure upfront (RAG index, tool schema normalization, task templates) so the agent stops generating wasted exploration tokens. Structured input is cheap; wasted output is expensive.

- **Semantic caching for retrieval-heavy agents.** Return cached results for semantically similar queries instead of re-running the model. Redis benchmarks show 40–70% hit rates for production workloads. Cache TTL and similarity threshold tuning matters more than cache size.

- **Track cost-per-task, not spend-per-month.** The metric that blindsides teams is aggregate spend. The metric that enables control is cost-per-task by type. Benchmark your agent's cost on SWE-bench Verified ($500–$2,000 per full run) or the PointFive Index (~230K input + 30K output per task) before scaling to production volume.

## Evidence

- **Toby Ord, "Are the Costs of AI Agents Also Rising Exponentially?":** o3 at full 1.5-hour task horizon costs $350/hour — exceeding human rates. GPT-5 costs $120/hour for 2-hour tasks. Frontier agents are priced above their capability plateau. — [tobyord.com/writing/hourly-costs-for-ai-agents](https://www.tobyord.com/writing/hourly-costs-for-ai-agents) (Dec 2025, 306 pts on HN)

- **Zylos Research, "AI Agent Cost Optimization: Token Budgets, Model Routing, and Production FinOps":** Enterprise LLM spend $8.4B H1 2025. 96% of teams exceeded projections. Teams applying the full optimization stack (caching + routing + masking + budgets) report 60–80% token spend reduction. — [zylos.ai/research/2026-04-12](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing) (Apr 2026)

- **HN 47326918, "More tokens, less cost":** Pre-indexing benchmark: 19.6M → 23.4M tokens (+20%), but cost dropped from $16.29 → $6.89 (−58%). Cache read rate: 93.8% → 95.3%. The counterintuitive finding: optimizing for token count is wrong; optimize for token tier mix. — [news.ycombinator.com/item?id=47326918](https://news.ycombinator.com/item?id=47326918)

## Gotchas

- **Leaving prompt caching disabled because it "adds complexity."** It is a 1-line config change that delivers 60–90% off repeated context. The complexity is in knowing what to cache and managing TTL, not in setup.

- **Routing on cost instead of capability.** Sending a complex debugging task to a $0.01/task model because it is cheap does not save money — it generates failed traces, retry costs, and quality incidents that dwarf the original price difference.

- **Setting budgets too late.** Token budgets must be set at design time, not tuned after the first surprise bill. By the time you see the cost dashboard, the runaway has already happened.

- **Ignoring context rot because there is no error.** The agent produces outputs that look fine but drift silently from instructions added in earlier turns. Budget context size as a reliability variable, not just a cost variable. Test instruction retention at turn 15, 25, and 40.
