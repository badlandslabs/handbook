# S-1303 · The Budget Spiral — When Your Agent Is Profitable in Demo and Bankrupt in Production

Your agent prototype passed every test. Your production bill passed no one.

Agents cost 3–10x more per task than a simple chat completion. A single user request triggers planning, tool selection, execution, verification, and response generation — each step an LLM call that compounds. An unconstrained coding agent on software engineering tasks runs $5–8 per task in API fees alone. At scale, the math is brutal: 3,000 employees × 10 interactions/day × $0.14 = $1.5M/year from what felt like a trivial feature.

## Forces

- Agents make 3–10x more LLM calls than chatbots — a single request triggers planning, tool use, verification, and response, each with its own token cost
- Most teams track cost-per-call, not cost-per-successful-task — so routing optimizations silently trade quality for savings with no detection mechanism
- Tool outputs that feed back into prompts multiply tokens exponentially over time; a 200-token file read echoed 10 times becomes 2,000 tokens
- The three optimization levers (routing, caching, budgets) interact — tightening budgets without measuring quality is a silent regression, not a win
- Agent loop costs scale quadratically with conversation length: every new tool call re-sends accumulated context, and cache reads accumulate until they dominate the cost

## The move

**Measure cost-per-successful-task first. Then apply three independent levers that compose to 60–80% cost reduction from naive baseline.**

1. **Semantic caching** — embed incoming queries, store responses, return cached results for semantically identical inputs. Deflects ~30% of production queries entirely at near-zero cost. Implement before anything else; it has no quality downside.

2. **Model routing by task complexity** — classify each step, not each request. Classification, FAQ lookups, and structured extraction route to cheap models (Claude Haiku ~$0.80/$4.00 per 1M tokens). Planning, multi-step reasoning, and error recovery route to frontier models. This alone handles 50% of calls with cheaper models. The classifier itself can be a simple rule or a lightweight 7B model — do not route through the same frontier model you're trying to avoid.

3. **Context compression on every loop** — summarize conversation history at N-turn boundaries (8–12 turns is the sweet spot; summaries over 40–60% shorter with negligible accuracy loss), compress RAG retrieval to top-k chunks with explicit relevance scoring, truncate tool outputs to error + result fields only (not full stdout). Prevents the quadratic cost explosion where context accumulation dominates.

4. **Per-agent budget caps in code** — set iteration limits, token ceilings, and wall-clock timeouts at the orchestration layer, not in prompts. A budget in a system prompt is advisory. A budget in the runtime loop is a circuit breaker.

5. **Batch processing for non-urgent work** — OpenAI and Anthropic Batch APIs offer 50% discounts for deferrable tasks. Any agent task with a >30-second SLA tolerance is a candidate.

**The measurement contract:** Before touching any lever, instrument cost-per-successful-task broken down by feature, task type, and model. Add the evaluator before the router. Savings cannot be trusted until a regression suite confirms quality survived.

## Evidence

- **Hacker News discussion (131 pts, 81 comments):** "Expensively Quadratic: The LLM Agent Cost Curve" — practitioners documenting that cached reads dominate costs by 50,000 tokens of context; tools reading files and feeding outputs back into prompts create exponential token growth. Thread debates truncation vs. full reads, summary-at-boundary strategies, and per-call cost tracking. — [https://news.ycombinator.com/item?id=47000034](https://news.ycombinator.com/item?id=47000034)

- **Research synthesis (Zylos, April 2026):** Enterprise LLM spending reached $8.4B in H1 2025; 96% of teams report costs exceeding projections. Agents make 3–10x more LLM calls than chatbots; unconstrained software engineering agents cost $5–8/task in API fees. Four-pillar framework: understand true token cost → implement routing → implement caching → enforce budgets. Combined strategies yield 60–80% reduction. — [https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing/](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing/)

- **Practitioner case study (AI Agents First, 2026):** Three optimization patterns that move the needle: model tiering by task complexity (simple tasks → Haiku at 4–10x lower cost than Sonnet), aggressive prompt caching (system prompts as shared prefix infrastructure), and batch processing (defer non-urgent work to Batch API rates). Together consistently produce 60–80% cost reduction vs. naive API usage. — [https://aiagentsfirst.com/ai-agent-deployment-cost-2026](https://aiagentsfirst.com/ai-agent-deployment-cost-2026)

## Gotchas

- **Routing without regression testing** — the most common failure of a cost stack is not a wrong setting; it's a savings change deployed without a quality measurement loop attached. Savings are trusted until users report degraded output weeks later.
- **Treating context optimization as post-launch** — context architecture is significantly harder to retrofit than to design in from the start. Cacheability, summarization boundaries, and tool output truncation need to be part of the agent's initial design.
- **Optimizing only one lever** — routing alone, caching alone, or budget alone almost always reverts within a week of production traffic. All three are needed, and they must be measured together.
- **Naive prompt truncation** — blindly truncating tool outputs or conversation history destroys agent continuity. Use structured summarization with a lightweight model rather than fixed token cuts.
