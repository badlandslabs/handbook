# S-751 · Agentic RAG Is a Control Loop, Not a Pipeline — The Self-Check Architectures That Actually Ship

The classic RAG mistake: build a linear pipeline (chunk → retrieve → generate → ship), observe confident hallucinations, and try to fix it by swapping the embedding model. The fix that actually works is architectural. RAG fails in production not because retrieval is weak but because there's no feedback signal between retrieval and generation. The teams shipping reliable agentic RAG treat it as a control loop — with explicit self-check nodes, iteration budgets, and faithfulness gates — and the delta in hallucination rates is measurable.

## Forces

- **Naive RAG silently amplifies confident wrong answers.** A loosely relevant retrieved chunk gives the model just enough grounding to generate with high confidence but low accuracy. No span in the pipeline flags it. The failure is invisible until a customer reports it.
- **Adding more retrieval calls without a judge makes things worse.** Agentic RAG with multi-hop decomposition and re-retrieval retrieves more context — and therefore multiplies the surface area for confident fabrication if each hop lacks a faithfulness gate.
- **LLM-as-judge evaluation has solved the ground-truth problem for RAG quality.** You no longer need a labeled dataset to measure faithfulness, answer relevance, and context precision — the model can score itself, and the metrics are actionable.
- **Iteration without a hard cap turns self-correction into infinite loops.** The self-check loop only works if there's a maximum step budget — without it, the agent re-retrieves and re-generates until it hits a confidence threshold that may never arrive.

## The move

Treat RAG as a closed-loop control system, not a pipeline. Embed four non-negotiable components:

- **Relevance grader between retrieval and generation.** A lightweight LLM call that scores each retrieved chunk for topical and semantic relevance before it reaches the generator. Corrective RAG studies show 60–70% drops in hallucination-inducing retrievals with this single addition.
- **Faithfulness judge on the generated draft.** A second LLM call that validates whether every claim in the answer is grounded in the retrieved context — not just that the context is relevant. If the judge fails, the pipeline loops back to re-retrieve or re-generate.
- **Hard step budget on all loops.** Cap re-retrieval iterations at 2–3, re-generation at 1–2. When the budget exhausts without a passing judge, surface the best partial answer with a confidence caveat — don't silently return a confident hallucination.
- **Per-span token tracking and cost gates.** Agentic RAG makes 3–8 LLM calls per query versus 1–2 in naive RAG. Track cost per call in tracing and fail or degrade gracefully when a single query exceeds a cost threshold.

## Evidence

- **Production case study:** A practitioner on iwajunnews.com rebuilding internal RAG pipelines in 2026 found that adding a relevance grader between retrieval and generation — Corrective RAG — produced a "60–70% drop in hallucination-inducing retrievals." Core reframe: "RAG is not a pipeline — it's a control loop."
  — https://iwajunnews.com/2026/05/19/agentic-rag-multi-agent-orchestration-in-production-what-we-actually-learned-in-2026
- **Benchmark data:** Amazon's agentic systems team (AWS blog, Feb 2026) found that traditional single-model benchmarks are insufficient for agentic evaluation — the emergent behaviors of multi-step systems require end-to-end trace evaluation including retrieval quality and self-correction rates.
  — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon
- **Framework guidance:** Ragas provides reference-free metrics — faithfulness, answer relevancy, context precision, context recall — using LLM-as-judge evaluation. DeepEval extends this with 50+ metrics including tool correctness, with native Pytest integration for CI/CD. Production target: retrieval precision ≥ 70%, generation groundedness ≥ 90%, end-to-end task success ≥ 85%.
  — https://aliac.eu/blog/agentic-rag-in-production
- **Failure mode documentation:** A production trace documented on futureagi.com showed an agent retrieved 8 chunks, used 6, and invented the seventh fact entirely — no span scored faithfulness, no judge gated the answer. The agent had every framework feature except the self-check loop that would have caught it.
  — https://futureagi.com/blog/agentic-rag-systems-2025
- **Cost/latency reality:** Agentic RAG costs 3–10x more tokens and adds 2–5x latency versus one-pass RAG. Build cost: $8K–$50K over 3–16 weeks. It earns that price on multi-hop research, compliance, and ambiguous queries — not FAQ bots.
  — https://www.marsdevs.com/guides/agentic-rag-2026-guide

## Gotchas

- **Retrieval quality gates are upstream of generation quality.** Swapping the generator model or prompt does not fix bad retrieval. The grader belongs between retrieval and generation, not after it.
- **LLM-as-judge introduces judge drift.** The scoring model changes over time. Log judge outputs alongside generation outputs and monitor for score inflation or sudden drops — treat the judge as a production component with its own regression surface.
- **Iteration caps must be enforced at the framework level, not as a best practice.** In LangGraph, use a step counter in the graph state and raise if max_steps is exceeded. In CrewAI, use the max_iter parameter on agents. Don't rely on developers to break loops manually.
- **The faithfulness metric requires the retrieved context to actually be in the prompt.** If your retrieval system silently drops context to save tokens or reduce prompt length, the judge will score faithfully against incomplete context — the answer will be confidently wrong with a high faithfulness score.
