# S-1207 · The Agent Cost Engineering Stack — When Your Agent Runs for Eleven Days and Costs $47,000

An AI agent's monthly bill arrives. It is larger than your salary. Not because a model got more expensive — it didn't — but because your agent ran 2,000 more steps than anyone authorized, each one re-sending 80,000 tokens of context to a frontier model. By the time the alert fired, the damage was already done. This is the agent cost engineering stack: treating token budget as a first-class production constraint, not a post-mortem line item.

## Forces

- **Agents make 10–20x more LLM calls than chatbots.** A simple chatbot = 1 call. An agent solving the same task = plan → tool-select → execute → verify → error-recover → respond = 10–20 sequential calls, each re-sending full context. This multiplication is the primary cost driver, not model price.
- **Inference is 20% of the bill; the other 80% hides in orchestration.** Licensing, orchestration infrastructure, retry logic, state management, observability tooling, and compute for tool execution add up to 4x the inference cost. Teams that optimize only the model price miss the bigger lever.
- **Context bloat compounds silently.** Naive memory injection scales linearly: 24 memory entries cost ~594 tokens/call, but 500 entries cost ~8,000 tokens/call. Production traces show 80–120K token contexts within 2–3 weeks of deployment. Nobody watches this until the bill arrives.
- **Budget alerts are not budget enforcement.** A dashboard showing $12,000 spent is not a circuit breaker. By the time a human reads the alert, every API call in the gap has already happened. Real budgets must be synchronous — checked before the next step, not after.
- **80% of AI spend is recoverable — but only with deliberate engineering.** Prompt caching, model routing, and hard budget enforcement together recover 60–85% of agent spend. Teams that build these in from the start are spending $0.40 per task where others spend $5.

## The move

**Measure cost per completed task, not cost per prompt.**

1. **Instrument every agent run at the step level.** Track tokens in, tokens out, step count, and cumulative cost per run. Log this to your observability pipeline alongside latency and quality. You cannot engineer what you do not measure.

2. **Set synchronous per-task token and dollar budgets.** Hard limits enforced in the orchestration layer — not dashboard alerts. Budget gates must block the next step, not just record it. Common values: $0.50–$2.00 per task for mid-complexity workflows.

3. **Enforce step count caps with semantic similarity checks.** Step limits alone truncate legitimate multi-step work. Layer in a "is this making progress?" check: if the last 3 steps produced semantically similar outputs, halt. This catches mutual recursion loops (Analyzer ↔ Verifier calling each other indefinitely) that step limits alone miss.

4. **Route tasks to the cheapest capable model.** Task complexity classification gates model tier: simple lookups → budget model (Gemini Flash, GPT-5 mini, Claude Haiku); classification + summarization → mid-tier (GPT-5, Claude Sonnet); multi-hop reasoning, complex code gen → frontier (Claude Opus, GPT-5.2). Teams running 4–7 distinct models per account report 60–80% cost reduction with negligible quality impact.

5. **Enable prompt caching aggressively.** Anthropic, OpenAI, and Google all offer cached context at 90%+ discount. Cache system prompts, shared tool definitions, and repeated knowledge base chunks. The savings compound: a 50K-token system prompt cached across 1,000 daily runs saves ~50M tokens/month.

6. **Separate inference cost from infrastructure cost.** Budget the orchestration layer, retry logic, tool compute, and observability as distinct line items. The 80% non-inference spend is where most teams are actually hemorrhaging money — and it's the easiest to cut.

7. **Set per-user, per-department, and per-agent budgets with automatic rollback.** Developer power users running agentic coding loops have different risk profiles than casual summarization users. Budget tiers prevent a single runaway developer from consuming the entire org's quota.

## Evidence

- **Engineering blog — 6-month production cost analysis:** Four production agentic systems tracked Oct 2025–Apr 2026. System A (single agent, 3 tools, 2.4 avg steps/run, 12K runs/month) cost $0.08/run. System D (multi-agent graph, 18 tools, 12.4 avg steps/run, 2,400 runs/month) cost $4.20/run. The data shows cost-per-task scales with orchestration complexity, not just volume. — [Inventiple](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)

- **Engineering post — the $47,000 mutual recursion incident:** In November 2025, a four-LangChain-agent setup fell into Analyzer ↔ Verifier mutual recursion. The Analyzer produced analysis; the Verifier asked for more analysis; the loop ran for eleven days until someone checked the bill. The dashboard showed spend climbing — but there was no enforcement. No malicious intent; just healthy agents in an unhealthy architecture. — [Jatin Bansal](https://blog.jatinbansal.com/ai-engineering/agent-budgets-and-runaway-prevention)

- **Engineering post — the 80/20 cost split:** Enterprise AI inference now represents 85% of total AI budgets, but orchestration, tooling, retries, and state management account for 80% of total cost of ownership. Uber's CTO noted in April 2026: "the budget I thought I would need is blown away already" after Claude Code adoption jumped from 32% to 84% of engineering. Cockroach Labs' analysis confirms inference is "only about 20% of TCO" — the majority hides in what surrounds the model. — [CockroachLabs](https://www.cockroachlabs.com/blog/agentic-ai-costs-at-scale/)

## Gotchas

- **Setting budgets too low truncates legitimate work.** A $0.10 task budget on a complex code refactor produces incomplete output and triggers a costly retry that costs more than a generous budget would have. Calibrate by running your 95th-percentile task through the system and setting the budget at 1.5x that value.
- **Model routing without validation causes quality regressions.** A task that routes to Haiku because it's cheap might need Sonnet. Validate routing decisions with A/B tests on real task distributions before cutting over production traffic. Historical success rates by model tier are the most reliable signal.
- **Caching creates invalidation complexity.** If a cached system prompt or knowledge base chunk changes, you must invalidate the cache or serve stale context. Document your invalidation triggers explicitly — this is an operational cost that doesn't show up in the token bill but requires engineering time.
- **Context bloat from memory systems is the silent killer.** Mem0's 2026 analysis found production memory traces reaching 80–120K tokens within 2–3 weeks of deployment with naive injection. The fix is not "add more memory" — it is "rank and truncate" with a fixed context budget, or switch to retrieval-based memory that selects relevant entries rather than concatenating all.
