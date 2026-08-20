# S-2898 · The Agent Memory Stack — When Your Agent Forgets Everything the Moment the Session Ends

Your agent aced the demo. In the session, it knew the customer's name, the agreed-upon price, and the half-finished plan from yesterday's conversation. You end the session, start a new one, and it asks for the customer's name again. The context window was fine. The model was fine. The problem is that you never gave it memory — you gave it a very expensive per-call scratch pad. This is the amnesia problem, and "just increase the context window" is not the fix.

## Forces

- **Context window ≠ memory.** Even models with 200K–1M token contexts fail at cross-session continuity. The BEAM benchmark (designed for million-token conversations) shows all frontier models still struggle with contradiction resolution — maintaining globally consistent state when earlier facts conflict with later updates. A larger window raises the per-call ceiling; it does not create persistence.
- **Retrieval is a double-edged sword.** Vector-store retrieval injects facts efficiently, but "lost in the middle" means retrieved context buried in the middle of a prompt is weighted less than beginning/end content. Retrieval quality depends heavily on query formulation and embedding freshness.
- **Write overhead compounds at scale.** Mem0 write latency is ~80–200ms async. Letta is ~150–400ms sync. Zep with Graphiti is ~300–800ms. At millions of facts, these costs hit your per-turn latency budget.
- **Staleness is invisible.** Agents act on stored facts without knowing when they were last verified. An agent serving a customer based on last-quarter pricing data is a silent failure unless staleness is surfaced.

## The Move

Build a two-tier memory architecture — not a single vector store.

**Tier 1: Checkpoint store (session continuity).** Every agent step writes a checkpoint — thread-scoped, write-heavy, low-latency. SQLite, Postgres, or Redis. This is for resumability: if the agent crashes mid-task, it picks up where it left off. Not for retrieval — the agent does not re-read every checkpoint.

**Tier 2: Semantic memory (cross-session knowledge).** Extracted facts, user preferences, learned domain knowledge. Backed by Mem0, Zep/Graphiti, or Letta. This is what the agent reads at session start to feel coherent with prior interactions.

The two tiers serve different retrieval patterns:
- Checkpoint → sequential replay for resumability, not query
- Semantic → vector search or graph traversal at session start

**Tier 3 (optional but valuable): Procedural memory.** Stored prompts, system instructions, tool definitions. This is stable and rarely changes — keep it separate from volatile facts.

On session start: inject a memory summary into the system prompt (not the raw store — that's too many tokens). Use a model-generated synthesis: "User prefers concise responses, has an ecommerce background, current project is migrating from Stripe to LemonSqueezy."

Track fact staleness. Store timestamps on every fact. Before injecting, filter or flag facts older than a threshold. Some teams store access frequency — cold facts (not retrieved in 2+ weeks) get evicted or down-ranked.

**The reflect pattern (Generative Agents architecture, now in Claude Code's `/diary`):** At session end, the agent writes a structured diary — task summary, decisions made, open items. A separate consolidation pass routes these into episodic (what happened) and semantic (what's true) stores. This is how you compound learning without re-deriving context every time.

**Tool portability matters more than you think.** Hmem (HN Show, 2025) stores agent memory in a single SQLite file accessible via MCP — same memory, any tool, any machine. Agents that lock memory to a specific IDE or platform create fragile systems.

## Evidence

- **Redis.io blog (2026):** "A context window and agent memory are two different things. One is a per-call input buffer the model reads fresh every time. The other is a system you build around the model so it can recall what happened yesterday, last week, or three sessions ago." Benchmarks show an agent executing 47-step return requests — step 48 it forgot the customer's name. — [Redis.io Blog: Why a bigger context window won't fix agent memory](https://redis.io/blog/why-bigger-context-window-wont-fix-agent-memory/)
- **Letta Gist / research survey (2025–2026):** Letta benchmarks show a plain filesystem scores 74% on memory tasks, competitive with specialized vector-store approaches. 60+ memory architecture sources reviewed. The "reflect" session-end loop pattern identified as the primary mechanism for turning session data into persistent knowledge. — [GitHub Gist: Memory Architectures for AI Agents](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)
- **Show HN: Hmem (2025):** Two core problems identified: (1) context dilution — earlier decisions silently pushed out of context window during long sessions, not just at session end; (2) tool lock-in — switching from Claude Code to Cursor erases memory. Solved with a portable `.hmem` SQLite file accessible via MCP protocol. — [Hacker News Show HN](https://news.ycombinator.com/item?id=47103237) / [GitHub](https://github.com/Bumblebiber/hmem)
- **AI Workflow Lab (2026):** Mem0 vs Letta vs Zep comparison. Mem0: ~80–200ms write latency, best for personalization. Letta: explicit memory-block API, best for long-running agents. Zep: temporal knowledge graph, best for CRMs where fact changes over time matter (user moved, price changed). — [AI Workflow Lab: Mem0 vs Letta vs Zep 2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)
- **Perea.ai research (2026):** Mem0 achieves 91.6% on LoCoMo benchmark (cross-session memory) and 93.4% on LongMemEval. Vector DB hierarchy settled: Qdrant (default), Weaviate (tool registries), pgvector (<10M facts), Pinecone (zero-ops). — [Perea.ai: Agent Memory in Production](https://www.perea.ai/research/agent-memory-production)
- **Anthropic's Claude memory system:** Automatic conversation synthesis every 24 hours. Project-level memory isolation. 39% improvement on agentic search tasks combining memory with context editing; 84% token reduction in 100-turn evaluations. — [GitHub Gist citing Anthropic architecture](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)

## Gotchas

- **Do not inject the raw vector store.** At scale, a semantic memory store can contain thousands of facts — injecting all of them burns tokens and dilutes relevance. Always synthesize: run a summarization pass over retrieved facts, inject a structured summary into the system prompt.
- **"Just use a bigger context" is a deferred failure.** Larger windows delay the problem. They do not solve cross-session continuity, fact staleness, or the cost of re-sending history on every call.
- **Fact staleness is the silent killer.** A Mem0 store with no staleness tracking will serve a 6-month-old customer preference as current fact. Store timestamps and access frequency on every fact; evict or flag cold facts.
- **Checkpoint stores are not for retrieval.** Writing a checkpoint every step is fine for resumability. Re-reading all checkpoints on every turn is not — the agent needs synthesized episodic summaries, not raw step-by-step logs.
- **Multi-agent memory is not the same as single-agent memory.** When multiple agents share a memory store, you need namespace isolation (per-agent memory spaces) and write-authorization rules. A supervisor agent that can write to all memory blocks is different from a worker agent that should only read its own context.
