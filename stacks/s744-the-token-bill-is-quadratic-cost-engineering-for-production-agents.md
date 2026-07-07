# S-744 · The Token Bill Is Quadratic: Cost Engineering for Production Agents

Most teams estimate agent cost like a chatbot — one call, one response. In production, a single user task triggers an 8–30-step plan → tool → observe → reflect loop, and every step resends the entire conversation context. What looked like $0.14 per task becomes $8.40. Enterprise teams report bills 3–14x above projections within weeks of launch. Cost is now a first-class architectural constraint, not an ops afterthought.

## Forces

- **The quadratic context trap**: Every agent step resends system prompts (2–8K tokens fixed overhead), tool definitions, conversation history, and tool results — costs compound, not accumulate — [AnhTu.dev, May 2026](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **The prototype-to-production multiplier**: A Singapore fintech burned **$87,000 in 11 days** when an agent loop recursively re-invoked itself on tool failure — each cycle added 12K tokens with no circuit breaker — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **96% of enterprise teams exceed initial LLM cost projections** — the gap between naive and optimized deployments spans **60–80% cost reduction** — [Zylos Research, April 2026](https://zylos.ai/en/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
- **Context discipline in multi-agent systems**: Passing complete conversation histories between agents (rather than structured summaries) makes costs grow exponentially — the reasoning agent needs structured outputs, not transcripts — [Zylos Research](https://zylos.ai/en/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)

## The move

Cost engineering for agents requires treating FinOps as a first-class engineering artifact, not a monthly review. The full optimization stack:

- **Token budgets as sprint artifacts**: Set per-task token budgets (e.g., 50K max) with hard stops — model the budget as a burndown chart alongside sprint velocity — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Prompt caching before it hurts**: Claude, OpenAI, and Gemini offer up to **90% discount** on repeated prompt prefixes — cache system prompts, tool schemas, and instruction sets; apply at every agent initialization — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Structured handoffs between agents**: Pass typed summaries, not full transcripts — a 4-agent orchestrator-worker workflow without context discipline costs **$5–8 per task** in inference fees; disciplined summaries drop it to $0.40–1.20 — [RaftLabs, November 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide) and [Zylos Research](https://zylos.ai/en/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
- **Step-count circuit breakers**: Implement hard step limits (default 15) with escalation paths — each step's expected cost times max steps must fit the task value — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Batch inference for non-realtime paths**: Report generation, research synthesis, batch analysis — batch API pricing offers **50% discount** with no latency constraint — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Tiered model routing by decision complexity**: Route simple decisions (formatting, routing, validation) to Haiku/ GPT-4o-mini-class models; reserve Opus/Claude 3.7 for reasoning and tool selection — teams optimizing this split report **60–80% spend reduction** — [Zylos Research](https://zylos.ai/en/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)

## Evidence

- **Engineering blog:** Shopify Sidekick built a Ground Truth Set evaluation framework to catch regressions before they ship cost — combined with JIT instructions, this let them constrain agent scope to high-value tasks only, avoiding the "agent does cheap work at expensive compute cost" pattern — [Shopify Engineering, August 2025](https://shopify.engineering/building-production-ready-agentic-systems)
- **Case study:** The orchestration gap drives 40% of multi-agent pilots to fail within six months of production deployment — teams that survive model cost as a primary design constraint from day one, not day 90 — [Xcapit / analysis, November 2025](https://www.xcapit.com/en/blog/real-cost-ai-agents-production) and [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Benchmark:** Average cost per SWE-Bench software engineering task dropped to **$2.40** by 2026 — down from $8–12 in 2024 — driven by improved model efficiency, better caching, and step-limit enforcement — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)

## Gotchas

- **System prompt overhead**: Most production agents carry 2,000–8,000 tokens of system prompt billed on every single API call — without prefix caching, this is a silent 20–40% surcharge on every step — [Zylos Research](https://zylos.ai/en/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
- **Recursive failure loops**: A tool that calls a parent agent on failure, which retries the tool, which fails again — this exponential token growth is the most common $50K+ bill surprise — always implement dead-man switches and max-recursion guards — [AnhTu.dev](https://anhtu.dev/token-economics-cost-optimizing-ai-agents-production-2026-2257)
- **Per-call framing is a lie**: A single "simple" agent task averages 8–30 LLM calls — 96% of enterprise teams underestimate this by an order of magnitude — [Zylos Research](https://zylos.ai/en/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
