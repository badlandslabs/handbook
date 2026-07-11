# S-945 · The Memory Decay Stack — When Your Agent Forgets Who You Are by the Third Turn

You build a customer support agent. First interaction: great. Second: decent. Third: "I don't have any record of our previous conversation." The agent has Alzheimer's. It forgot everything. The fix isn't a longer system prompt — it's a memory architecture.

## Forces

- **Context windows are expensive and slow.** A 200k-token context means you're paying to re-send everything on every call. At scale, this is cost-prohibitive and latency-inducing.
- **Vector retrieval is opportunistic, not authoritative.** Stuffing everything into a vector store and retrieving top-k doesn't tell you what the agent *knows for certain* vs. what it *happened to recall*. Contradictions pile up silently.
- **Agents degrade over time without persistent state.** Every session starts cold. The agent re-establishes context from scratch, paying the retrieval pipeline tax on every turn — and still getting coherence wrong.
- **The HN consensus is stark:** "Most frameworks treat memory as a vector store — everything goes in, nothing gets resolved. Over time the agent is recalling contradictory facts with equal confidence." [HN, 2025](https://news.ycombinator.com/item?id=47328951)
- **Token budgets force compaction, but naive compression destroys signal.** Summarizing a 50-message thread into one paragraph loses what was actually decided, what was contradicted, and what remains open.

## The move

Treat memory as a first-class persistent layer — not a retrieval add-on. The pattern has four components:

**1. Structured fact extraction, not raw storage.**
  - Ingest conversation turns and extract structured facts automatically (who, what, when, resolved status).
  - Tag facts with source reliability: `[direct_observation]` vs `[user_reported]` vs `[inferred]`.
  - Don't store the raw transcript as the memory — store the interpreted meaning. DeltaMemory reports 3,714x token compression doing exactly this. [DeltaMemory.com](https://www.deltamemory.com/)

**2. Certainty scoring, not binary recall.**
  - Store each fact with a continuous confidence score, not just presence/absence.
  - Flag `[contradicted]` facts when the same entity is asserted differently later. The agent should weight confident, consistent facts higher than fresh-but-unverified claims.
  - On HN, practitioners describe this as solving the "equal-confidence hallucination" problem: "Over time the agent is recalling contradictory facts with equal confidence." [HN item 47328951](https://news.ycombinator.com/item?id=47328951)

**3. Persistent working state, not per-session initialization.**
  - Files the model initializes from every run: append-only logs, active rules, known inventory, conversation history.
  - Key distinction: not queried opportunistically like a vector DB — present as working context on startup. [HN item 46385179](https://news.ycombinator.com/item?id=46385179)
  - This eliminates the retrieval pipeline tax on every turn. The agent boots with a coherent self-model.

**4. Temporal-aware retrieval.**
  - Rank memories by recency, relevance, and certainty — not just semantic similarity.
  - For queries about current state ("where are we in this task?"), prioritize the most recent resolved facts. For historical queries ("what did we agree on in May?"), retrieve by date.
  - Mem0's April 2026 algorithm update achieved 92.5 on LoCoMo and 94.4 on LongMemEval benchmarks using single-pass retrieval at a 7K token budget. [Mem0 GitHub, 2026](https://github.com/mem0ai/mem0)

## Evidence

- **Open-source library (60.6k stars):** Mem0 ("mem-zero") is the canonical open-source implementation — universal memory layer for AI agents and assistants, Y Combinator S24 backed, Apache 2.0. Benchmarks: 92.5 LoCoMo, 94.4 LongMemEval, 64.1 BEAM at 1M tokens. [GitHub mem0ai/mem0](https://github.com/mem0ai/mem0)
- **HN production discussion:** "I built DeltaMemory — persistent cognitive memory for production AI agents." Claims 89% accuracy on LoCoMo (highest score), 50ms p50 query latency, 97% cost reduction vs raw token re-processing. [HN Show HN, 2026](https://news.ycombinator.com/item?id=47161647)
- **HN root-cause analysis:** One practitioner explains why vector-only memory collapses: "Agents aren't deterministic systems. They make decisions based on context, they choose which tools to use, they navigate multi-step workflows... Standard unit tests that work beautifully for regular software? Pretty much useless here." [HN, 2025](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Naive RAG isn't memory.** Semantic similarity retrieval against a flat vector store doesn't solve coherence — it solves search. Without contradiction detection and certainty scoring, you get confident hallucinations layered on confident hallucinations.
- **Compaction destroys resolution.** Summarizing a thread into a paragraph loses `[resolved]` / `[open]` / `[contradicted]` tags. The agent forgets what was settled. Use structured extraction instead of summarization for compression.
- **Per-session amnesia is the default, not the exception.** Teams reach for longer context windows as the first solution. This is expensive and still doesn't solve continuity across sessions. The fix is persistent working state, not bigger context.
- **Memory quality degrades without lifecycle management.** Facts need to be revisited, contradicted, and resolved — not just accumulated. Without active management, memory grows unbounded and quality converges to noise.
