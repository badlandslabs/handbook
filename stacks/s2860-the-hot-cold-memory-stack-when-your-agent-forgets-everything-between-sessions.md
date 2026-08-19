# S-2860 · The Hot/Cold Memory Stack

[When your agent works great in a demo, then "forgets everything" the next morning — every preference, every half-finished task, every learned fact. The session boundary is where agents die.]

## Forces

- **Context windows are finite even when they feel large.** Conversation history, tool results, plans, and facts all compete for the same window. "We have 1M tokens" is not an architecture — it's a delay until the problem arrives.
- **Hot state and cold state have different access patterns.** Checkpoint state (where am I mid-task?) needs millisecond reads with full fidelity — a vector store's fuzzy retrieval is wrong for this. Cross-session facts (user prefers Railway) need semantic recall — SQLite row lookups are wrong for this. Most teams use one store for both and pay both costs.
- **Auto-capture beats manual memory.add() calls.** The moment you require the agent or developer to consciously call `memory.add()`, memory rots. People forget. Agents forget they forgot. The best systems intercept tool results and conversation turns automatically.
- **Adding memory makes retrieval harder, not easier.** More stored memories = more noise in the retrieval signal. Without a write discipline, you end up with a large corpus of stale, contradictory facts that hurt more than they help.

## The Move

Split memory into tiers by access pattern and retention policy. Do not use one store for everything.

### 1. HOT — Per-conversation checkpoint state
- Serialized agent state (current plan, completed steps, tool call history) written to a fast key-value or file store on every step
- This is the "pause and resume" layer: if the process dies or a human approval takes 30 minutes, restore from checkpoint and continue
- Store must survive process restart but has no semantic query requirement — exact deserialization is required
- Tool: Redis (sub-ms), in-memory + file sync, or iii-engine + SQLite for zero-DB setups
- **The harness** (the code driving the agent loop) decides what reaches the context window — the store does not push itself

### 2. COLD — Cross-session semantic memory
- Facts learned across sessions (user preferences, project context, established conclusions) stored in a queryable semantic store
- Not all "memory" goes here — extracted facts only, not raw conversation logs
- Retrieval combines multiple signals: semantic embedding similarity + BM25 keyword matching + entity linking + temporal ranking (recent facts for current-state queries, older facts for historical queries)
- Tool: Mem0 (open source, 27K stars, scored 92.5 on LoCoMo / 94.4 on LongMemEval v3), Graphiti, Zep, or any vector DB with hybrid search
- Mem0 v3 (April 2026) uses ADD-only extraction — one LLM call per memory write, memories accumulate, nothing is overwritten

### 3. Auto-capture hooks (non-negotiable in production)
- Intercept every tool result and conversation turn and feed them to memory automatically
- Zero reliance on human or agent to remember to call `memory.add()`
- agentmemory (GitHub, 27K stars) ships 12 auto-capture hooks that cover the full tool call lifecycle without manual calls
- Benchmark evidence: teams using auto-capture see 92% fewer tokens vs pasting full context (~$10/year vs ~$500/year at typical usage)

### 4. Document memory (optional but underrated)
- Human-readable files (Markdown, YAML) for project knowledge the agent can read AND write
- Unlike vector stores, these can be version-controlled, diffed, and reviewed by humans
- Best for: codebase conventions, architectural decisions, runbooks
- Works alongside vector retrieval, not instead of it

### 5. Write discipline — extraction beats accumulation
- Run a lightweight LLM extraction pass on conversation turns to distill facts before storing
- Don't dump raw conversation history into semantic storage — the retrieval noise will degrade signal
- Redis's architecture documentation recommends this explicitly: "Update working memory, extract facts to the long-term store, and optionally summarize old context"
- Mem0's single-pass extraction (one LLM call, no UPDATE/DELETE) operationalizes this

## Evidence

- **GitHub README:** agentmemory — "12 auto-capture hooks (zero manual effort), 95.2% retrieval R@5 on LongMemEval-S, 92% fewer tokens vs pasting full context" — [https://github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)

- **arXiv paper / GitHub README:** Mem0 v3 (April 2026) — single-pass ADD-only extraction, scored 92.5 on LoCoMo, 94.4 on LongMemEval, 6.8K tokens per retrieval at p50 1.09s — [https://arxiv.org/abs/2504.19413](https://arxiv.org/abs/2504.19413) + [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)

- **Engineering blog:** Slava Dubrov — "Separate memory by access pattern. Hot memory is per-conversation checkpoint state for pause and resume. Cold memory holds cross-session facts in a key-value or vector store. The harness decides which of their contents reach the context window; the stores do not." — [https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture)

- **Company blog:** Redis.io — "Three concrete failures without persistent memory: personalization dies between sessions, long-horizon tasks break, multi-system context evaporates." Redis covers all four memory functions: short-term through in-memory structures, long-term through vector search, operational state through hashes/JSON, coordination through streams — [https://redis.io/blog/long-term-memory-architectures-ai-agents/](https://redis.io/blog/long-term-memory-architectures-ai-agents/)

- **arXiv preprint:** Memory Tiering (clawRxiv:2603.00037, March 2026) — three-tier HOT/WARM/COLD architecture: HOT tier for active context (~128K tokens, ~5-minute TTL), WARM tier for recent session facts (~512K tokens, ~24-hour TTL), COLD tier for long-term semantic memory with vector retrieval — [https://clawrxiv.io/abs/2603.00037](https://clawrxiv.io/abs/2603.00037)

- **HN "Show HN":** Agents Remember — Git-aware memory for coding agents using Markdown files as the store, showing the document memory pattern in practice — [https://news.ycombinator.com/item?id=48413877](https://news.ycombinator.com/item?id=48413877)

## Gotchas

- **Do not put checkpoint state in a vector store.** Checkpoints need exact deserialization. Vector retrieval is fuzzy by design — you will get back a corrupted state and your agent will behave unpredictably. Checkpoints belong in Redis, SQLite, or flat files.
- **Do not put fuzzy facts in a structured key-value store.** User preferences and project context retrieved by semantic similarity need a semantic store. A raw key-value lookup can't find "the thing about Railway deployments" when the key is `user_pref_20240115`.
- **Retrieval quality degrades as memory grows.** Without periodic extraction or summarization, more memories means more noise. Mem0 v3's ADD-only accumulation model mitigates this by never overwriting, but you still need to tune your retrieval top-K.
- **The harness owns what reaches the context window.** Stores do not push. If your harness always retrieves and always includes the full result, you're back to the original context overflow problem. Be selective.
- **Context window size is not a memory architecture.** The teams running into memory problems at 1M-token context windows are the ones treating "we have a big window" as a substitute for a real tiering strategy. The problem is attention dilution and retrieval noise, not raw token capacity.
