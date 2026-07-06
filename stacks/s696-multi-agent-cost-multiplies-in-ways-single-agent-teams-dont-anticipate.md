# S-696 · Multi-Agent Cost Multiplies in Ways Single-Agent Teams Don't Anticipate

A single-agent demo costs $0.14. Your production pipeline costs $5–8 per task. The gap isn't a pricing problem — it's an architecture problem that most teams discover after they've already shipped.

## Forces

- **A single agent's cost is a fiction.** The relevant unit is the pipeline, not the call. A 4-agent workflow multiplies not just token counts but per-agent context management, memory overhead, and tool calls.
- **Multi-agent LLM calls run 3–10× higher than chatbot equivalents.** Agentic loops, retries, and inter-agent handoffs compound token spend in ways that don't show up in your per-token cost model.
- **Enterprise teams consistently underestimate by 2–4×.** 96% of enterprises report agent cost overruns, with teams routinely budgeting for single-agent inference when their architecture is multi-agent.
- **Naive RAG pipelines fail at retrieval 40% of the time**, adding wasted LLM calls on top of already-multiplied costs. You're paying for inference on the wrong data.
- **Context window costs are the silent killer.** Every inter-agent handoff re-injects context. A 3-hop pipeline with shared memory can consume 10× the tokens of a single equivalent model call.

## The move

**Model the pipeline, not the call.** Before building, map the cost of a complete task end-to-end — including retries, context re-injection, and memory summarization. This is your real unit cost.

**Stack composable savings layers.** The most effective production architectures apply optimization at every layer: semantic caching (30% deflection), model routing (50% cheaper calls), prefix caching (remaining inference), and batch scheduling (50% off async). Composed together: 60–80% reduction from naive baseline.

**Route by task complexity, not by budget.** Assign GPT-4o-mini or equivalent to routing, classification, and simple retrieval. Reserve Claude Opus and GPT-5 for synthesis, complex reasoning, and final output. This is the single highest-leverage architectural decision.

**Budget per agent, not just per pipeline.** Agents that observe their own token consumption — summarizing old turns, preferring cheaper tools, stopping early when budget is constrained — reduce cost structurally rather than by accident.

**Instrument retrieval before scaling.** Naive RAG at scale is the most common source of runaway costs. Hybrid search + cross-encoder reranking is the production baseline; without it you're burning tokens on wrong context.

## Evidence

- **Zylos Research (2026):** Comprehensive production FinOps analysis documenting the "token cost trap" — single conversations at $0.14 scale to $5–8 per unconstrained agent task. Full optimization stack achieves 60–80% reduction. Agent LLM calls run 3–10× higher than chatbot equivalents. — [https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)
- **RaftLabs / Gartner (Nov 2025):** 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025). 57% of organizations already running agents in production. 96% of enterprise teams report cost overruns. Complex multi-agent tasks cost $5–8 per task in inference. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Lushbinary RAG Survey (2026):** Naive RAG pipelines fail 40% of the time at retrieval, adding unnecessary LLM calls on hallucinated or absent context. Production RAG requires hybrid vector + keyword search with cross-encoder reranking as the minimum viable architecture. — [https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Amazon Engineering Blog (Feb 2026):** Multi-agent evaluation requires human-in-the-loop because automated metrics fail to capture emergent inter-agent behaviors — specifically coordination failures that waste inference cycles. — [https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

## Gotchas

- **Cost overruns don't show up in the demo.** Agentic loops and retries are hard to predict from a controlled demo. Load-test with realistic task distributions before committing to architecture.
- **Prefix caching helps but isn't a solution.** It reduces cost on repeated prefixes (system prompts, tool schemas) but doesn't address the multiplicative cost of multi-agent context re-injection.
- **Routing models add latency.** Model routing introduces a classification step before task delegation. For latency-sensitive flows, pre-classify at the orchestration boundary instead of per-agent.
- **Retrieval is the most expensive place to fail.** A wrong context chunk causes an LLM to reason on hallucinated data, producing output that then requires human review. The cost of bad retrieval is not just wasted tokens — it's rework.
