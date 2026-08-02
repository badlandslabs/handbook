# S-2034 · The Agent Memory Stratification Stack — When Your Agent Forgets Everything the Moment the Session Ends

Your agent completed a 47-step data pipeline on Tuesday. On Wednesday it has no idea what it did, why it made the choices it made, or that pipeline-42 exists. You re-explain the project from scratch. Again. The LLM is stateless — every call starts from zero. The fix is not a bigger context window. The fix is **memory stratification**: the right data in the right store with the right retrieval mechanism for each information type.

## Forces

- **Context window size is the wrong metric.** A 2M-token window answers "how much can the model see?" but not "what does the agent need to know, and for how long?" A larger window just delays the failure mode — it doesn't eliminate it. Nearly 65% of enterprise AI failures in long-running sessions trace to context drift before any token limit is hit (Zylos Research, Feb 2026).
- **One memory store doesn't fit all.** Conflating semantic knowledge, episodic events, and procedural instructions into a single vector index produces noisy retrieval across all three types. Each memory type has a different access pattern, decay rate, and storage cost — and the right architecture separates them.
- **Multi-agent memory is a fundamentally different problem.** In single-agent systems, memory is about the agent remembering the user. In multi-agent systems (which now represent a 1,445% surge in production inquiries — Gartner), memory is about agents sharing a consistent view of state. 36.9% of multi-agent failures stem from inter-agent misalignment (Cemri et al., 2025). Better models don't fix it; better memory architecture does.

## The Move

The 2026 field has converged on a **stratified memory architecture** — layered stores serving different temporal scopes, retrieval mechanisms, and use cases. The foundational taxonomy comes from the **CoALA framework** (Cognitive Architectures for Language Agents, Sumers et al., 2024, arXiv 2309.02427):

**1. Working Memory — the context window.**
The LLM's live scratchpad. Holds the current task, recent tool outputs, and the active reasoning trace. Hard cutoff at token limit. No persistence — everything here disappears at session end. Design implication: keep it lean. The working memory's signal-to-noise ratio degrades as it fills, so compaction (progressive summarization of completed subtasks) runs at ~70-80% window capacity to preserve decision-relevant information.

**2. Episodic Memory — what happened.**
Stores specific past events: conversation turns, tool-call traces, interaction sequences. Key property: temporal ordering. Implementation tiers:
- *Checkpoint store* (session-level): SQLite, Postgres, or Redis — stores raw conversation state, enables session resumability and time-travel debugging. The `agent-handover` project (GitHub) specifically addresses coding agent statelessness: at session end it checkpoints decisions, half-done work, and project state to durable storage; next session resumes from that checkpoint instead of starting blank.
- *Event log* (cross-session): Append-only log of agent actions, timestamps, and outcomes. LangGraph, Temporal, and Dagster all ship first-class checkpoint primitives for this. Combined with idempotent tool design, this transforms brittle agent pipelines into fault-tolerant, resumable workflows.

**3. Semantic Memory — what the agent knows.**
Cross-session, long-term: learned facts, domain knowledge, user preferences. Stored in vector databases (Chroma, pgvector, LanceDB) or graph databases (Zep's Graphiti). Semantic search retrieves based on meaning, not keyword — critical because users phrase things differently across sessions. Key production tools:
- **Mem0**: Open-source (~48K GitHub stars, $24M raised), four scoping dimensions (user_id, agent_id, run_id, app_id), integrates with LangGraph, Vercel AI SDK, ChatGPT. The `langgraph-mem0-agent` project (GitHub) reports 26% better accuracy, 91% faster responses, 90% cost reduction vs. stateless baseline.
- **Zep**: Open-source, temporal knowledge graphs via Graphiti (bitemporal annotations — event time vs. record time), entity extraction, auto-classification. Now ships a unified plugin for Claude Code, Codex, and Cursor that gives coding agents Zep documentation and project-specific context memory. Python, TypeScript, and Go SDKs.
- **Letta** (formerly MemGPT): OS-inspired virtual memory — agent manages its own memory via function calls. Three tiers: core memory (in-context, editable by agent), recall memory (searchable conversation history), archival memory (long-term vector store). The agent self-edits its core memory block as facts change, deciding what to keep in the limited context window.

**4. Procedural Memory — how the agent acts.**
The agent's own instructions, tool definitions, and behavioral policies. Stored as system prompts, tool schemas, and (increasingly) as learned skills. Voyager-style systems accumulate reusable skills in skill libraries that persist across sessions. The agent doesn't re-learn "how to write a PR" on every session.

**Multi-agent memory patterns** (three options, hybrid is the production winner):
- *Centralized*: Single shared memory store all agents read/write. Simple, consistent, but creates bottlenecks at scale.
- *Distributed*: Each agent has private memory. Fast, independent, but agents operate on different versions of reality — the root cause of 79% of multi-agent coordination failures (TURION.AI research, 2026).
- *Hierarchical*: Agents have private episodic memory, shared semantic memory. The winning pattern in production — agents retain their own history while sharing a consistent world model. Mem0 implements this via its `agent_id` and `user_id` scoping dimensions.

## Evidence

- **HN Show HN:** "Everyone's trying vectors and graphs for AI memory. We went back to SQL" — Gibson AI team found that for agentic workflows, relational tables with typed schemas (user_preferences, conversation_summaries, entity_facts) outperformed vector stores for structured recall. 136 points, 63 comments on HN (item?id=45329322, ~late 2025).
- **Research paper:** "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory" (arXiv 2504.19413) — introduces Mem0's four-dimensional memory scoping, evaluates against Letta and vanilla baselines, demonstrates improved task completion on multi-session benchmarks.
- **Engineering blog:** TURION.AI benchmarks three multi-agent memory patterns with production code — hierarchical (shared semantic + private episodic) outperforms both centralized and distributed on coordination accuracy. 90%+ performance improvement over single-agent on research tasks, 41-87% of multi-agent systems still fail in production due to memory architecture gaps (2026).

## Gotchas

- **Vector retrieval is not free lunch.** Semantic search over agent memory has the same failure modes as RAG: noisy recall, lost structure, retrieval of tangentially relevant but contextually wrong facts. Zep's Graphiti addresses this with bitemporal knowledge graphs that preserve *when* a fact was true, not just *that* it was true — preventing the agent from acting on outdated preferences.
- **Memory compaction before the crisis, not during.** Running summarization only when the context window is 90% full introduces latency at the worst moment. Agent.ceo recommends compaction triggers at 70-80% capacity — proactively, not reactively.
- **Context drift is invisible.** The agent doesn't know it has forgotten the early context of a long task. It confidently makes decisions using only recent context, producing contradictory or incomplete outputs with no error signal. Monitor compaction events and context utilization rate, not just task success.
- **Multi-agent memory contamination.** When agents share semantic memory, one agent's confident-but-wrong fact can pollute the shared store. Hierarchical architectures need access controls and fact provenance — who added this, and can it be contradicted? Zep's temporal graph tracks this natively.
