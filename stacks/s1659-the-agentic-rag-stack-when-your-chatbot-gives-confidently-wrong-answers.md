# S-1659 · The Agentic RAG Stack — When Your Chatbot Gives Confidently Wrong Answers

Your RAG chatbot sounds authoritative. It cites docs you don't recognize, uses terms that aren't in your knowledge base, and nobody notices until a customer flags it. The standard fix — more documents, better chunking, higher top-k — keeps failing because the underlying problem isn't retrieval. It's that your pipeline generates answers without checking whether retrieved content actually supports them.

Agentic RAG fixes this by giving the retrieval pipeline a self-evaluation loop. Before answering, the agent checks whether retrieved content covers the question. If it doesn't, the agent re-queries, rephrases, or escalates. This is the difference between a system that retrieves and a system that reasons.

## Forces

- **Naive RAG fails silently.** A system that retrieves the top-k chunks and passes them to an LLM will confidently hallucinate whenever chunks are tangentially related to the query. You get plausible-sounding wrong answers with valid-looking citations.
- **Latency vs. correctness is a real trade-off.** The self-evaluation loop adds 1-3 LLM calls per query. For a customer-facing bot answering 10K queries/day, this compounds into significant cost and latency. You need a gating mechanism that only triggers deep retrieval on questions that actually need it.
- **"Agentic" is still undefined.** Practitioners disagree on whether an agent needs multi-step planning, tool autonomy, or just a reflective loop. This means teams implement wildly different architectures under the same label, making it hard to compare approaches or hire for them.
- **Orchestration overhead can outweigh the benefit.** Complex agent frameworks (LangGraph, AutoGen, CrewAI) add abstraction layers that obscure what the agent is actually doing, making debugging harder than the retrieval problem they were meant to solve.

## The move

The core pattern: embed a confidence-gating step between retrieval and generation. Before the LLM produces a final answer, a reviewer agent checks whether the retrieved context actually supports it. Only answers that pass the gate are returned. Everything else gets re-queried, escalated, or flagged.

**Query decomposition first.** Break the user query into sub-questions that can be answered independently. This prevents the "answer a related question" failure mode where the system retrieves plausible but off-topic content.

**Retrieve-then-evaluate, not retrieve-and-answer.** After retrieval, have a separate evaluation step: does this retrieved content actually answer the decomposed sub-questions? If confidence is below threshold, trigger re-retrieval with a rephrased query.

**Use a tiered retrieval strategy.** Simple questions (fact lookups, policy questions) use standard top-k retrieval and skip the agentic loop. Complex questions (comparisons, multi-step reasoning, ambiguous queries) trigger the full agentic pipeline. Gate this with a lightweight classifier or query complexity heuristic.

**Return citations with provenance, not just confidence.** The evaluator should produce a structured output: which chunks support which claims, and which sub-questions went unanswered. This makes the final answer auditable and gives downstream human reviewers something concrete to check.

**Fail loudly, not confidently.** When the retrieval-and-evaluation loop cannot reach confidence threshold after N iterations, return a "I don't have enough information" response rather than a generated answer. For compliance or safety-critical domains, this is the correct behavior.

## Evidence

- **Uber Engineering Blog (May 2025):** Transitioned their internal on-call copilot Genie from standard RAG to Enhanced Agentic RAG. Results: **27% relative increase in acceptable answers, 60% relative reduction in incorrect advice.** The agent does its own query expansion, multi-source retrieval, and reflection on whether the response covers the question before returning. Incorrect advice in a compliance context is worse than no answer — the re-planning loop is the safety mechanism. — [https://www.uber.com/us/en/blog/enhanced-agentic-rag/](https://www.uber.com/us/en/blog/enhanced-agentic-rag/)

- **Aliac Engineering: Agentic RAG in Production (Feb 2026):** Compiles enterprise results across multiple deployments. Harvey AI (legal): **0.2% hallucination rate** serving 700+ legal clients. Deutsche Telekom: **89% acceptable answer rate** across 2M+ conversations. A European bank's audit/compliance agent saved **EUR 20M+ over 3 years** by replacing manual document review with an agentic retrieval pipeline that flags inconsistencies rather than generating answers. — [https://aliac.eu/blog/agentic-rag-in-production](https://aliac.eu/blog/agentic-rag-in-production)

- **Hacker News discussion "Ask HN: Examples of agentic LLM systems in production?" (Dec 2024):** A 73-comment thread questioning whether real agentic systems exist beyond marketing. The most-cited production examples included internal developer tools (code search, documentation Q&A, on-call assistants), with the consensus that **"agency" means the system makes non-trivial tool choices, not just generates text**. One practitioner noted: "If the workflow gives no choice between tools, it's just an LLM workflow." This distinction — non-deterministic tool selection as the defining feature of an agent — was echoed across multiple top comments. — [https://news.ycombinator.com/item?id=42431361](https://news.ycombinator.com/item?id=42431361)

## Gotchas

- **Don't add agentic loops to everything.** A self-reflective retrieval pipeline on every query is expensive and slow. Gate on query complexity: fact lookups need one retrieval pass; comparative questions, ambiguous queries, and multi-hop reasoning benefit from the agentic loop. Use a cheap classifier or token-count heuristic to decide.
- **The evaluation LLM can be smaller and faster than the generation LLM.** You don't need GPT-4o or Claude Opus for the confidence-gating step — a smaller model (GPT-3.5-turbo, Haiku) is often sufficient to judge whether retrieved content answers a question. Reserve the expensive model for final answer generation.
- **Agentic RAG doesn't fix bad embeddings.** If your vector store has poor chunk quality, misaligned metadata, or outdated documents, the agent will retrieve bad content and fail the evaluation step repeatedly. Fix the retrieval corpus first — the agentic loop makes the problem visible but doesn't solve it.
- **Be careful with the escalation threshold.** If your "I don't know" escalation rate is too high, users lose trust. If it's too low, you return confidently wrong answers. In production, measure both the escalation rate and the answer quality rate separately, and tune the threshold based on domain: low-risk FAQ can tolerate higher tolerance; compliance, legal, and medical domains need near-zero hallucination tolerance.
