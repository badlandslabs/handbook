# S-2086 · The Tiered Model Stack · When Your Agent Uses Claude Opus to Answer "What's 2+2"

*When your agent routes a trivia question through a $15/M-token frontier model — because nobody told it to do otherwise. Tiered model routing matches request complexity to model capability, cutting inference costs 40–85% without touching output quality.*

## Forces

- **The 100x pricing spread is structural, not temporary.** GPT-4o Mini costs $0.15/M input tokens; Claude Opus costs $15. The same API call on the same task can differ by two orders of magnitude depending on which model you chose — and the choice is usually made once, at code-write time, and never revisited.
- **Hardcoding a single model means you're overpaying for most requests.** Enterprise surveys consistently find 50–70% of agent requests are routine: simple classification, formatting, single-step tool calls. These don't need frontier capability, but a single-model agent gives them frontier cost.
- **Routing quality loss is smaller than the cost savings.** FrugalGPT (Stanford, TMLR 2024) demonstrated 98% cost reduction with cascade routing; RouteLLM (UC Berkeley, 2024) achieved 85% savings on MT-Bench. The quality delta is often imperceptible to end users — and when it matters, the router escalates.
- **Agent steps have varying complexity within a single trajectory.** Unlike one-shot queries, an agent's reasoning loop means step 3 might be trivial (reformat JSON) and step 7 might need frontier reasoning. A fixed model choice is wrong for most of the steps.

## The Move

Implement a tiered model router that dispatches each LLM call to the cheapest model that can reliably handle it:

- **Define 3–4 model tiers.** Nano/Flash (Haiku, GPT-4o Mini, Gemini Flash-Lite, $0.07–0.30/M input) for extraction, formatting, classification. Mid-tier (Sonnet, GPT-4o, $0.50–3/M) for general reasoning, tool orchestration. Frontier (Opus, GPT-4.5, $5–25/M) for multi-step planning, ambiguous judgment calls.
- **Route by signal, not guesswork.** Use fast heuristics: query length, presence of "analyze/explain/evaluate" keywords, number of tools requested, conversation turns so far. More sophisticated routers use a lightweight classifier (matrix factorization, as in RouteLLM) trained on query-difficulty pairs.
- **Cascade as the simplest working pattern.** Try nano first. If confidence is below threshold, escalate to mid. If still uncertain, go to frontier. FrugalGPT's cascade approach cuts cost dramatically because most requests clear at the cheap tier.
- **Route at the step level, not the session level.** A single agentic trajectory has steps of varying difficulty. Route each LLM call independently — the classification step is nano, the planning step is frontier, the formatting step is nano again.
- **Instrument every routing decision.** Log (query_hash, selected_model, router_confidence_score, actual_quality_signal). This is what closes the feedback loop. Without it, you're flying blind.
- **Handle escalation failures.** If the nano model returns low-confidence output, the escalation logic must trigger reliably. Build explicit retry-on-escalate, not just "if error then retry with same model."

## Evidence

- **Research paper:** FrugalGPT (Stanford/TMLR 2024) — cascade routing approach achieving up to 98% cost reduction by sequentially trying cheaper models before expensive ones. — https://arxiv.org/abs/2305.05176
- **Research paper:** RouteLLM (UC Berkeley, 2024) — matrix-factorization-based router achieving 85% cost savings on MT-Bench while maintaining quality within 3% of GPT-4. — https://arxiv.org/abs/2405.11038
- **Engineering blog:** Zylos Research (March 2026) — dynamic routing reduces inference costs 40–85% while maintaining 90–95% of frontier quality; 50–70% of enterprise agent requests can be handled by nano tier without quality loss. — https://zylos.ai/research/2026-03-02-ai-agent-model-routing/
- **HN Discussion:** "Ask HN: How are you orchestrating multi-agent AI workflows in production?" (2026) — practitioners describing custom routing logic, some using semantic classifiers to dispatch between model tiers. — https://news.ycombinator.com/item?id=47660705

## Gotchas

- **Semantic caching is cheaper than routing.** Before building a custom router, check whether caching hits (69% of repeat queries return a cache hit at swfte.ai). The simplest possible "cost reduction" is not making the API call at all.
- **Routing adds latency, not just cost savings.** Cascade routing tries nano → mid → frontier sequentially, which can add latency for the 10–30% of queries that escalate. Use parallel probing with confidence estimation if latency is a constraint.
- **Agents need routing at step granularity, not session granularity.** A router that picks one model for the whole session has already failed — step complexity within a trajectory varies wildly. The routing decision must live inside the step loop, not outside it.
- **Hardcoded routing rules break when models are updated.** When Anthropic releases a new Sonnet version or OpenAI adjusts pricing, if/else routing rules scatter across your codebase. Centralize routing behind an abstraction layer — one file to change when the model landscape shifts.
- **Don't route safety-critical decisions through nano.** Escalation thresholds must account for stakes. A medical or financial judgment call should never land on a nano model regardless of what the router thinks.
