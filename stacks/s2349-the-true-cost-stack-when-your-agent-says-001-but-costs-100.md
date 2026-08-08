# S-2349 · The True Cost Stack — When Your Agent Says $0.01 but Costs $1.00

Your agent costs $0.01 per API call. You routed to the cheapest model. Your bill came in at $3,200 for the month — and only 12% of tasks completed successfully. A colleague running a frontier model spent $4,100 and hit 91% success. You thought you were optimizing cost. You were optimizing the wrong number.

The metric that actually decides whether your agent is economical is **cost per successful task**: `(cost per run) ÷ (success rate)`. Teams that don't measure it make every optimization decision backward.

## Forces

- **Cost-per-token hides failure cost.** A model that scores well on benchmarks and costs $3/M tokens can still be the most expensive option if it fails half the tasks — because every failure means running the task again, often with a more expensive fallback. Cost-per-token optimizes the wrong variable.

- **Agentic workflows multiply token volume.** A single task that takes a chatbot one LLM call takes an agent 10–20 sequential invocations: planning, tool selection, execution, verification, error recovery, synthesis. Moderately complex requests consume 20,000–60,000 tokens; non-trivial engineering tasks hit 150,000–200,000 tokens per problem. Context windows grow linearly but bills grow at every step.

- **The routing shortcut backfires.** Model routing — sending simple tasks to cheap models and hard tasks to frontier models — works in theory. In practice, existing routers target chat completion, not tool-calling. Agents that call tools have different capability profiles than chat models, and a router trained on the wrong task type routes incorrectly, cascading failures downstream.

- **Prompt caching looks like free money until you measure it wrong.** Anthropic's prompt caching delivers a 90% discount on cached tokens ($0.30/M vs $3.00/M). But an HN commenter on Tokenless (YC S26) noted that hot-cache calls only save money in user-facing turns where the user waits 5+ minutes for the cache to reset. For agentic workflows — which run long chains of successive tool calls with hot caches — the routing economics break down entirely. Most agentic work benefits from a hot cache anyway.

- **Error recovery loops double token consumption before anyone notices.** When an agent fails and re-prompts, it resends the full conversation context, runs another planning step, and retries the tool. Teams discover this when the monthly bill arrives.

## The Move

The shift from cost-per-token to cost-per-successful-task reorients every decision in the stack:

- **Log cost per run end-to-end.** Capture every LLM call in a task — including retries, sub-agent calls, and synthesis steps — as one unit. Divide by your actual success rate. Until you have this number, every optimization is a guess.

- **Build explicit token budgets per task type.** A token budget is a structured ceiling per task class (e.g., "repo analysis: 50k tokens max"). Budgets force early stopping or escalation before runaway loops. Budgets also surface which task types are actually cheap vs. which ones silently accumulate.

- **Route by task complexity, not by outcome.** A DistilBERT-based classifier trained on your specific tool-calling benchmarks can route requests to the cheapest capable model at 82.9% accuracy — matching frontier models while cutting inference cost by 84% (Switchcraft, Microsoft Research, arXiv:2605.07112). The key is using a router trained on function-calling benchmarks, not chat benchmarks.

- **Use provider-native caching before adding external caching layers.** Anthropic prompt caching gives 90% discounts on repeated context. OpenAI cached completions do the same. These are simpler, cheaper, and lower-latency than building a semantic cache on top.

- **Separate model tier from output quality tier.** Route factual lookups and context gathering to cheap models; reserve frontier models for synthesis and judgment. A multi-model blend — 4.7 distinct models on average for mature enterprises — produces a lower blended cost than any single model, when measured correctly.

- **Measure intervention rate alongside cost.** The fraction of tasks requiring human override is a leading indicator of failure rate. An agent that costs $0.01/run but requires a human review 40% of the time has a true cost of $0.017/run — plus human labor.

## Evidence

- **Research paper:** Microsoft Research's Switchcraft (arXiv:2605.07112, May 2026) introduced the first model router optimized for agentic tool-calling. Using a 66M-parameter DistilBERT classifier, it achieves 82.9% routing accuracy — matching or exceeding the best individual model — while reducing inference cost by 84% and saving $3,600+ per million queries. Key finding: "larger models do not consistently outperform smaller ones on tool-use tasks, and nominally cheaper models can incur higher total cost due to token-intensive reasoning." — [arXiv:2605.07112](https://arxiv.org/abs/2605.07112)

- **Industry analysis:** Langwatch's "Cost per Successful Task" analysis demonstrates the failure-metric problem concretely: a model costing $0.01/attempt that succeeds 3% of the time costs ~$1,000 per correct result. The analysis shows that as model subsidies end, cost-per-successful-task becomes the number that decides your AI stack — and most teams have never calculated it. — [langwatch.ai](https://langwatch.ai/blog/cost-per-successful-task)

- **Enterprise report:** The New Stack's analysis of agentic AI costs (July 2026) found that token consumption — not model selection — is the real cost driver. "A task that takes about 50,000 tokens with one agent can easily consume several hundred thousand with multiple specialized agents together." Per-request cost estimates built in staging diverge dramatically from production costs because session costs grow superlinearly as conversation extends. — [thenewstack.io](https://thenewstack.io/agentic-ai-token-costs/)

- **Primary source:** YC S26 startup Tokenless pitched automatic model switching to save money. HN discussion surfaced a critical constraint: caching-based routing only saves money when the cache is cold. For agentic workflows with successive tool calls (the dominant use case), the cache is hot by default — nullifying the routing benefit. The comment chain reveals the real production constraint: "Hot cache calls reduce input cost by 90%. This basically only delivers cost savings in turns where the AI delivers a result to the user." — [HN Item #49099143](https://news.ycombinator.com/item?id=49099143)

## Gotchas

- **Don't route on model price; route on cost-per-successful-task per task type.** A $0.05/M model that fails 60% of your "complex reasoning" tasks costs more per outcome than a $3/M model that succeeds 95% of the time.

- **Token budgets need task-class granularity, not global limits.** A global 100k-token budget per session will timeout on legitimate long tasks and still allow runaway token accumulation within a single task. Budgets must be set per task type with separate escalation paths.

- **Context compression before summarization.** Naive summarization of conversation history loses structured signals (action-outcome relationships, environment state). Approaches like ACON (Optimizing Context Compression for Long-horizon LLM Agents, arXiv:2510.00615) preserve failure-driven guidelines and decision cues that generic summarization drops. Compress context by what the agent needs to reason, not by token count alone.

- **Prompt caching savings are real but bounded.** Caching helps most when the same system prompt and fixed context appear across many requests. Agents with highly dynamic per-task context (most production agents) get minimal cache hit rates — don't budget around 90% savings unless you've measured your cache hit rate in production.
