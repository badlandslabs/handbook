# S-694 · Multi-Agent Coordination: Why Better Coordination Beats Bigger Models

The moment you split one agent into two, you've taken on a coordination problem you can't test with unit tests. And the data says the coordination pattern you choose matters more than the model size behind it.

## Forces

- **More agents should mean more capability — but often means more failure.** AppWorld benchmarks show 86.7% failure on cross-app workflows. Multi-agent is not automatically better.
- **The naive split (parallel agents, merge results) is the worst split.** Without a coordination layer, agents produce conflicting outputs, lose shared state, and fill context windows with duplicated reasoning.
- **Bigger models do not solve coordination failures.** MultiAgentBench found GPT-4o-mini beats larger models on coordination tasks. Coordination is a structural problem, not a reasoning problem.
- **The choice of orchestration pattern is made once and paid for repeatedly.** Switching from supervisor to peer coordination after you've built a production system is a rewrite.
- **Naive RAG fails at document extraction before it fails at retrieval.** Teams blame the vector search — the actual bottleneck is lossy PDF parsing and arbitrary chunk boundaries.

## The move

The pattern you choose for multi-agent coordination is the highest-leverage decision in the stack. Evaluate on these dimensions before picking a framework:

### Choose coordination patterns by failure mode, not by framework popularity

| Pattern | Structure | Best for | Failure mode |
|---------|-----------|----------|--------------|
| **Sequential (pipeline)** | Linear chain, A→B→C | Fixed-step workflows, clear handoffs | brittleness if any step needs branching |
| **Supervisor (hierarchical)** | One orchestrator, N workers | 3-5 agents, complex routing decisions | supervisor becomes bottleneck as it accumulates all state |
| **Consensus (debate)** | Multiple agents, output merged | ambiguous tasks requiring diverse perspectives | cost doubles with each agent; winner-take-all collapses to single-agent quality |
| **Blackboard (shared state)** | All agents read/write shared context | exploratory tasks, shared knowledge | race conditions on writes; eventual consistency is not intuitive |
| **Dynamic (event-driven)** | Agents subscribe to events, react autonomously | loosely-coupled systems, independent specialists | invisible failures — agents silently miss events |

### Design the handoff interface before splitting agents

Define explicitly: what does Agent A produce that Agent B consumes? If you can't write that contract down, you don't have a split — you have a pile of agents waiting to pass None errors.

- **Supervisor bottleneck fix**: checkpoint state to DB at each step, not just at end. LangGraph's `MemorySaver` and SQLite checkpointing persist thread state per conversation, enabling horizontal scaling and crash recovery.
- **Context window management**: tool outputs consume the most context — load them on demand via Agent Skills (structured instruction sets loaded per-task), not pre-loaded at session start. The "lost in the middle" problem hits hardest at 6+ tool calls.
- **Memory systems need temporal reasoning**: most memory layers store conflicting facts as separate entries. Build conflict-driven updates — when a user contradicts a prior preference, the system should overwrite, not append. GDPR semantic deletion is unsolved in most stacks; flag it as a compliance risk.

### For RAG: fix the extraction pipeline first

- Naive RAG fails 40% at the retrieval step — not because embeddings are weak, but because **PDF parsing produces semantically broken chunks**.
- Hybrid search (dense embeddings + BM25 sparse keyword index) handles both semantic similarity and exact identifiers (ticket numbers, code references).
- Re-rankers can *hurt* quality when the reranker model is weaker than the generation model — validate before deploying.
- Q&A-augmented chunking (generate Q&A pairs per chunk at ingestion) dramatically outperforms naive chunking for question-answering tasks.

## Evidence

- **Multi-agent benchmarks:** ChatDev achieves 33.3% correctness on programming tasks; logistics systems show 27% throughput gains, 22% cost reduction with multi-agent coordination patterns. Pattern choice is the dominant variable. — [Thread Transfer blog](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)
- **LLM stack in production:** Production reliability: 55% at $847/month → 78% at $312/month after optimization. Initial cost is not the real cost — teams underestimate by 3x. — [Calder's Lab](https://calderbuild.github.io/blog/2025/01/16/ai-agent-2025-breakthrough)
- **Framework choice:** "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites 6-12 months in." LangGraph has 90K+ GitHub stars; CrewAI leads for rapid prototyping; AutoGen is in transition to Microsoft Agent Framework (GA Q1 2026). — [Gheware DevOps AI Blog](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **HN production sentiment (543 points):** "We've removed LangChain and LangGraph from our project because they are literally not worth it. Best advice: use the API directly. Frameworks add abstraction layers that you have to adapt to your internal observability setup." — [Hacker News](https://news.ycombinator.com/item?id=44301809)
- **Context engineering:** Supervisors become bottlenecks as they accumulate state from all workers. Tool outputs filling context windows is the primary failure mode. "Agent Skills" — on-demand structured instruction sets loaded per-task — is the emerging solution. — [HN: Agent Skills for Context Engineering](https://news.ycombinator.com/item?id=46351787)
- **Memory layer gaps:** Conflict-driven fact updates (e.g., user changing a preference) not reliably handled. GDPR semantic deletion is unsolved — memories stored as embeddings/summaries cannot be surgically removed without collateral fragments. — [Reddit r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1ra0ude/ai_memory_layers_are_promising_but_3_things_still/)
- **Production RAG:** Naive pipelines fail 40% at retrieval due to brittle document extraction, not weak vector search. Hybrid search (RRF fusion of dense + sparse) handles both semantic and exact-match queries. Re-rankers can degrade output quality. — [onseok.github.io](https://onseok.github.io/posts/building-production-rag-system) and [dasroot.net](https://dasroot.net/posts/2025/12/advanced-rag-techniques-hybrid-search/)

## Gotchas

- **Parallel agents without a merge strategy is not multi-agent — it's a race condition.** If two agents produce different answers and you just pick one, you got worse than a single agent.
- **The demo infrastructure cost ($50-60/month) is a fiction for production.** Real production runs $200-2,000/month minimum before LLM API costs, which alone run £1,800-£10,500/month depending on token volume and model tier.
- **Supervisor pattern does not scale past 5 agents.** The supervisor's context window becomes the bottleneck; consider moving to a peer or event-driven pattern.
- **Re-rankers add latency and cost — test whether they actually improve your specific retrieval quality before committing to them.**
- **Memory summarization is lossy and irreversible.** If you summarize a conversation before storing it, you cannot recover the original. Keep raw checkpoints for high-stakes interactions.
