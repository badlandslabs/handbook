# S-670 · The Stack Stratifies: Why Agentic Architecture Is an Engineering Problem

[You built a demo agent in an afternoon. Now you need it to handle 10,000 users, recover from partial failures, and cost less than $0.01 per task. The LLM that felt magical now feels like the least of your problems. The agent stack is splitting into distinct layers — and treating it as one monolith is why most production agents quietly fail.]

## Forces

- **The demo tax is invisible until it isn't.** Demo agents work because edge cases are hand-waved. Production agents must handle every branch the LLM could take — and you won't know which branches exist until the 3 AM alert fires.
- **Observability ≠ evaluation.** 89% of teams have agent observability; only 52% have actual evals (RaftLabs/Gartner, 2025). This gap explains why multi-agent debugging is still mostly guesswork.
- **Cost compounds across agents.** A single-agent workflow costs cents. A 4-agent orchestrator-worker workflow costs $5–8 per complex task. Architecture decisions have direct dollar consequences.
- **Framework choice shapes thought patterns.** LangGraph, CrewAI, and AutoGen each impose a mental model. Picking wrong means fighting the framework instead of shipping.
- **Tool overload kills accuracy.** Tool selection accuracy drops below 90% past 8–10 tools. The instinct to give agents more tools makes them worse.

## The move

The 2025 production AI agent stack has crystallized into distinct layers. Treating it as a monolith — or skipping layers you don't "feel" yet — is the root cause of most agentic failures.

**1. Foundation layer — pick one primary model per capability tier**
- Fast/frequent tasks: Claude Haiku, GPT-4o-mini, Gemini Flash (low cost, acceptable quality)
- Complex reasoning: Claude Sonnet, GPT-4o, Gemini Pro (higher cost, better accuracy)
- Route based on task complexity, not preference. Don't route everything through your most capable model.

**2. Orchestration — choose by mental model, not features**
- LangGraph (state-machine graphs): production default for durable execution, retries, and debugging. Used at Klarna, Replit, Elastic. Best when you need observable, replayable agent flows.
- CrewAI (role-based crews): fastest path to multi-agent role-mapping problems (content pipelines, support escalation). Active v0.98+ development. Best for teams that think in org charts.
- AutoGen (conversational agents): maintenance mode as of October 2025. Successor is Microsoft Agent Framework. Avoid for new projects.
- Custom (raw loops): justified only when you need fine-grained control over token budgets and latency that no framework exposes.

**3. Memory/persistence — layer it by access pattern**
- Short-term: conversation context window (managed by orchestration framework)
- Medium-term: semantic memory (Mem0, pgvector, Qdrant) for cross-session persistence
- Long-term: structured memory (PostgreSQL, SQLite) for user preferences, facts, state
- Don't reach for a vector DB until you have a retrieval problem, not just a storage problem.

**4. Tool calling — constrain ruthlessly**
- Expose ≤10 tools per agent. Beyond that, accuracy drops and latency compounds.
- Use MCP (Model Context Protocol) for tool standardization across providers.
- Design tools as coarse-grained operations, not fine-grained steps — each tool call has latency and cost overhead.
- Validate tool outputs with schemas (Pydantic) before passing to the next step.

**5. Guardrails — build the safety net before the demo**
- Input validation: schema check all user inputs before they reach the agent.
- Output validation: validate tool return values and LLM outputs against expected shapes.
- Action budget: hard cap on steps per task (e.g., max 20 tool calls) to prevent loops.
- Cost guardrails: per-task token budgets, automatic fallback to cheaper models on simple tasks.

**6. Evaluation and observability — close the gap**
- Observability (what happened): LangSmith, Phoenix, or custom structured logging. Covers traces, token usage, latency.
- Evaluation (did it work): RAGAs, DeepEval, TruLens. Covers answer quality, retrieval precision, hallucination rate.
- The 37-point gap (89% observability vs 52% evaluation) means teams can see what agents do but can't tell if they're doing it right.

**7. RAG — agentic retrieval is the 2025 evolution**
- Naive RAG pipelines fail 40% of the time at retrieval (Lushbinary, 2026).
- Hybrid search (dense vectors + keyword BM25 with Reciprocal Rank Fusion) outperforms either alone.
- Rerankers help but can hurt quality if over-applied — rerank the top 20, not top 200.
- Agentic RAG: agents decide when and how to retrieve, not just once at query time.
- Chunking strategy matters more than embedding model. Semantic splitting beats fixed-size. Q&A augmentation on technical docs yields large quality gains.

## Evidence

- **Research report:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025; 40% of agentic AI projects are at risk of cancellation by 2027. — [RaftLabs citing Gartner](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Framework analysis:** LangGraph is the production default for durability and debugging; CrewAI leads for role-mapping problems; AutoGen entered maintenance mode October 2025. — [JetThoughts](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025), [MMNTM](https://www.mmntm.net/articles/orchestration-showdown)
- **Production lessons:** "The technology (the model) is maybe 30% of the challenge. The remaining 70% is engineering." Constrain action space, validate everything at boundaries, build evals before demos. — [The AI Vibe](https://theaivibe.org/blog/building-production-ai-agents-lessons-2025)
- **RAG failure data:** Naive RAG fails 40% at retrieval. Hybrid search + semantic chunking + reranking addresses the top failure modes. — [Lushbinary](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)
- **Multi-agent patterns:** Four orchestration patterns cover most production use cases (hierarchical, pipeline, orchestrator-worker, peer-to-peer). Untyped handoffs between agents kill workflows faster than any other issue. — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Amazon internal lessons:** Multi-agent HITL evaluation is critical for production. Automated metrics fail to capture emergent behaviors, coordination failures, and inter-agent communication quality. — [AWS Machine Learning Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

## Gotchas

- **Don't start with the most capable model.** Route tasks. GPT-4o on a routing decision costs 10x what Gemini Flash costs for the same accuracy on that subtask.
- **The observability you skip is the debugging you'll need.** If you don't instrument every tool call and state transition on day one, you'll instrument it at 2 AM under pressure.
- **Multi-agent handoffs need schemas, not trust.** Every agent-to-agent boundary is a failure point. Define validated schemas with version numbers — not just "I trust the output format."
- **CrewAI's "fast to start" advantage disappears in complex flows.** Sequential processes are easy; hierarchical processes with 5+ agents accumulate latency and failure modes that require the same engineering rigor as LangGraph.
- **Evaluation can't be retroactive.** Teams that add evals after deployment find that 30–50% of their "working" agent outputs don't meet quality bar. Build the eval harness on day one.
