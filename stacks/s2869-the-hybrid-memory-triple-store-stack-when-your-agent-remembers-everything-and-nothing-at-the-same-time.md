# S-2869 · The Hybrid Memory Triple-Store Stack — When Your Agent Remembers Everything and Nothing at the Same Time

When your agent pulls up a user's entire conversation history on a simple query but can't remember a preference set two sessions ago — the problem is not context length. It is that your memory stores data but doesn't tier it. You have a flat list where you need a ranked retrieval pipeline.

## Forces

- **Flat history is a liability, not memory.** Every message into context burns tokens and dilutes signal. Agents with raw conversation logs are slower and more confused than agents with targeted recall.
- **Working memory and long-term memory have incompatible requirements.** Working memory needs sub-100ms retrieval of the last N turns. Long-term memory needs semantic search across months of interactions. No single store does both well.
- **Context windows are finite but knowledge compounds.** The agent needs to learn from history without stuffing all of it into every prompt. You need a pipeline that compresses, ranks, and retrieves selectively.
- **Three memory types fight for architecture space.** Episodic (events), semantic (facts), and procedural (skills) each require different storage and retrieval strategies. Most teams collapse these into one, then pay for it.

## The move

Build a three-tier memory architecture: **working memory** (fast, ephemeral), **semantic memory** (retrieval-augmented, durable), and **procedural memory** (agentic, skill-embedded). Route each memory type to its optimal store and compose them at inference time.

### Tier 1 — Working Memory (Ephemeral, Sub-100ms)

- Holds the last 6–10 exchanges, active plans, constraints, and intermediate results.
- Lives **in-context** or in an L1 cache (Redis), never in a vector store.
- Retrieved before every LLM call; cleared on session end.
- Purpose: lets the agent know what it was doing 30 seconds ago.

```
Architecture: Redis sorted set (session-scoped, TTL ≤ 1 hour)
Latency target: <50ms retrieval
Size: bounded by token budget (~4K tokens for working memory)
```

### Tier 2 — Semantic Memory (Durable, Retrieval-Augmented)

- Stores distilled facts: user preferences, domain knowledge, entity relationships.
- Vector-embedded for similarity search; selectively injected into context.
- Implemented by Mem0 (63K GitHub stars, Y Combinator-backed) or equivalent.
- Purpose: tells the agent what it knows about this user, topic, or workflow.

```
Architecture: Mem0 → Redis (cache) → LLM
Key insight: Mem0's Memory Compression Engine reduces token costs up to 80%
by sending only relevant memories, not the full history.
Retrieved via semantic similarity, re-ranked by recency and importance.
```

### Tier 3 — Procedural Memory (Agentic, Skill-Embedded)

- Stores how-to knowledge: tool sequences, workflow templates, guardrail rules.
- Does not belong in the LLM's context — it belongs in the **agent harness itself**.
- Expressed as reusable skill definitions, tool chains, or policy files.
- Purpose: encodes institutional knowledge the agent should always follow.

```
Examples:
- "Before sending an email, check recipient against allowlist"
- "When database write fails, rollback before retrying"
- "Cross-reference SKU with the approved catalog before placing order"
```

### Memory Composition at Inference

At every LLM call, compose context from all three tiers:

```
1. System prompt (procedural memory — static, always loaded)
2. Retrieved semantic memories (weighted by relevance score)
3. Working memory buffer (session context — last N turns)
4. Task-specific retrieved documents (RAG layer, if applicable)
```

Rank and truncate. The goal is the smallest relevant context that lets the agent succeed — not the largest possible context.

## Evidence

- **Anthropic Engineering Blog:** Claude's Research system uses multi-agent subagents with isolated context windows, where each subagent holds only what it needs for its subtask. "Subagents enable compression by operating in parallel with their own scoped context." The supervisor agent composes results — it doesn't hold all subagent memory simultaneously. — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Mem0 arXiv paper (2504.19413):** Mem0's memory architecture dynamically extracts salient information, consolidates key facts and patterns, and retrieves relevant memories when needed. The graph-based variant uses knowledge-graph representations to model complex relationships between conversational elements. 63K GitHub stars; Y Combinator-backed. — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)
- **Cleanlab enterprise survey (2025):** Among the 5% of engineering teams with AI agents live in production, the top investment priority (63%) is improving observability and evaluation — categories that require structured memory to generate meaningful traces. 70% of regulated enterprises rebuild their agent stack every 3 months, indicating that memory architecture decisions are still actively unstable across the industry. — [Cleanlab](https://cleanlab.ai/ai-agents-in-production-2025/)

## Gotchas

- **Don't store everything as semantic memory.** Verbose conversations compressed naively into semantic memory create false confidence — the agent "remembers" a nuanced conversation as a flattened fact. Use episodic logs for audit trails; use semantic only for distilled facts.
- **Procedural memory lives outside the model, not inside it.** Encoding workflow rules into the system prompt creates prompt drift and makes changes require a model redeploy. Store procedural memory as structured data loaded by the harness.
- **Memory retrieval is not free.** Every semantic memory lookup adds latency and cost. Profile your retrieval pipeline end-to-end — a 200ms vector search that runs 5 times per task adds a full second. Cache aggressively.
- **Memory consolidation is not automatic.** Without periodic consolidation (nightly or after N sessions), semantic memory grows unbounded and retrieval quality degrades. See S-1002 on consolidation debt.
