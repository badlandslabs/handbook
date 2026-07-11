# S-969 · The Agentic RAG Self-Check Stack — When Your Agent Invents Facts Between Your Chunks

A research agent answers a multi-hop question in production. The pipeline retrieves 8 chunks, generates a draft, and ships it. Two days later a customer flags one paragraph as fabricated. The trace shows the agent retrieved 8 chunks, used 6 of them, and invented a fact from nowhere. No span scored faithfulness. No judge gated the answer. The agent had every framework feature it needed — except the one that would have caught the hallucination. This is what agentic RAG looks like when the self-check loop is missing.

## Forces

- **Agents hallucinate even with perfect retrieval.** Retrieving the right documents does not guarantee the agent uses only those documents. LLMs fill gaps with plausible-sounding content, especially under partial information or multi-hop pressure.
- **Classic RAG has no gate between retrieval and output.** The pipeline is one-way: retrieve → generate → return. If the generation drifts from the retrieved content, nothing catches it.
- **Multi-hop queries make this worse.** When a question requires chaining across documents, the agent synthesizes from multiple sources — and every synthesis step is an opportunity to introduce an unsupported claim.
- **Increasing retrieval iterations amplifies hallucination surface.** Agentic RAG can make 3–8 LLM calls and 2–6 retrieves per turn (vs. 1+1 in classic RAG). Each generation step is a new chance to drift.

## The Move

The self-check loop adds a **faithfulness judge** between the generation step and the final output. Before the answer reaches the user, a separate model evaluates whether the generated content is actually supported by the retrieved documents. If not, the pipeline loops back to retrieve more or re-generate — iterating until the answer is grounded or a step budget is exhausted.

Five concrete patterns ship in production as of 2026:

- **Query rewriting with decomposition.** Before retrieval, the agent rewrites and decomposes ambiguous queries into sub-queries. "What was revenue growth in Q3 and how did it compare to Q2 guidance?" becomes two targeted retrievals. Prevents under-retrieval at the root.
- **Dynamic multi-hop retrieval with state.** The agent retrieves, generates an intermediate conclusion, then uses that to inform the next retrieval. State is maintained across hops so later steps build on earlier ones rather than starting fresh.
- **Tool routing across heterogeneous retrievers.** Not all information lives in the vector store. Production agentic RAG routes queries to specialized retrievers — keyword search for exact IDs, vector search for semantic similarity, SQL for structured data — and synthesizes across them.
- **Faithfulness judge gates the answer.** A separate model (often a smaller/cheaper judge) reads the generated answer alongside the retrieved chunks and scores each claim for support. If ungrounded claims exceed a threshold, the pipeline loops. This is the critical safety gate that most agentic RAG tutorials skip.
- **Re-retrieval on failure with step budget.** If the judge finds gaps, the agent attempts another retrieval cycle with revised queries. A maximum step budget (typically 5–10 iterations) prevents infinite loops. When budget is exhausted on an ungrounded answer, the system either returns a partial answer with explicit uncertainty markers or escalates to a human.

## Evidence

- **Blog post (FutureAgi, 2025/2026):** Documented the exact failure case — a research agent retrieving 8 chunks, using 6, and inventing a seventh fact. Introduced the five-pattern taxonomy (query rewriting, multi-hop, tool routing, self-check, re-retrieval). Notes that classic RAG has no gate; agentic RAG adds a faithfulness judge that "gates the answer." — [futureagi.com/blog/agentic-rag-systems-2025](https://futureagi.com/blog/agentic-rag-systems-2025)
- **Blog post (Agentbrisk, March 2026):** Catalogued agentic RAG failure modes including single-hop limitation, ambiguous terminology failure, and missing self-verification. Describes how the agent "evaluates what it found, retrieves again if needed, and reasons across multiple retrieved documents before producing an answer." — [agentbrisk.com/blog/agentic-rag-patterns-2026](https://agentbrisk.com/blog/agentic-rag-patterns-2026)
- **Blog post (Onseok, March 2026):** Production implementation covering hybrid search (Reciprocal Rank Fusion), reranker pitfalls, Q&A-augmented chunking, and MCP integration for serving retrieved results to agents. Documents vocabulary mismatch and "lost in the middle" as concrete retrieval-layer failures that compound at generation time. — [onseok.github.io/posts/building-production-rag-system](https://onseok.github.io/posts/building-production-rag-system)
- **Blog post (Coasty, June 2026):** Industry benchmark data showing OpenAI Operator fails 62% of basic desktop tasks on OSWorld; RPA projects fail 50% of the time. Core insight: "Model capability isn't the bottleneck. Robust error handling is." Distinguishes between tool errors (retryable) and logic errors (return 200 OK but are wrong). — [coasty.ai/blog/ai-agent-error-handling-recovery](https://coasty.ai/blog/ai-agent-error-handling-recovery-why-90-of-computer-use-proposals-fail)

## Gotchas

- **Adding a judge doubles your LLM call count.** The self-check pattern means every answer generation has an associated judge call. Budget this into latency (3–8 LLM calls per turn vs. 1 for classic RAG) and cost estimates.
- **A faithfulness judge can drift too.** If the judge model differs from the generation model in capability or fine-tuning, it may approve ungrounded claims (false negative) or reject grounded ones (false positive). Calibrate the judge's tolerance threshold on your specific domain.
- **Step budgets prevent loops but don't guarantee correctness.** An agent can exhaust its budget and still produce an ungrounded answer. Have an explicit fallback: partial answer with uncertainty flags, escalation path, or dead-letter queue for human review.
- **Over-retrieval is the agentic RAG failure mode opposite to classic RAG's under-retrieval.** The agent keeps looping and retrieving more chunks than necessary, inflating latency and token cost. Set per-turn retrieval caps and monitor retrieval-to-use ratios.
- **The most dangerous failures return 200 OK.** Hallucinated facts, wrong records modified, incorrect synthesis — these produce valid HTTP responses with semantically wrong content. You need trace-level observability, not just log-level monitoring, to catch them.
