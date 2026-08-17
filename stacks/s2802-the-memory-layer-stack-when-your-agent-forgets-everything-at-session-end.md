# S-2802 · The Memory Layer Stack · When Your Agent Forgets Everything at Session End

Every conversation starts from zero. Every user is a stranger. Every past interaction erased. Stateless agents are fine for one-shot tasks — catastrophic for anything that involves ongoing relationships, projects, or work.

## Forces

- **Brevity vs. continuity** — short context is cheap and fast; agents that remember are expensive and complex to build
- **Generality vs. precision** — generic memory systems store too much noise; precise systems require schema migrations as requirements evolve
- **Privacy vs. personalization** — cross-session memory means sensitive data persists, multiplying the blast radius of any breach
- **Token budget vs. recall fidelity** — context windows are finite; naive summarization loses important details; vector retrieval introduces its own failure modes
- **What teams build vs. what ships** — demos impress with fresh context; production fails when the agent re-learns the same thing 47 times

## The Move

Implement a **three-layer persistent memory architecture** that survives session boundaries and scales without linear context growth.

### Layer 1 — Episodic Memory
Raw records of what happened: tool calls made, responses received, decisions taken. Stored as structured events with timestamps. The agent's "journal."

- Store each interaction as an event log: `{timestamp, agent_id, action, outcome, user_feedback}`
- Prune aggressively: summarize old episodes into semantic memory after N sessions or tokens
- Keep the last K episodes uncompressed for recent context retrieval

### Layer 2 — Semantic Memory
Compressed, queryable summaries of past episodes. The agent's "knowledge." Built via periodic consolidation from episodic records.

- Convert episodic event logs to natural-language summaries at session boundaries
- Embed summaries and store in a vector database for similarity search
- Update in place when new information supersedes old facts (critical: handle schema migrations)
- Monitor **memory hit rate** in production — the percentage of queries that retrieve useful context

### Layer 3 — Procedural Memory
How the agent should behave. System prompts, tool definitions, policy rules, learned patterns. The agent's "muscle memory."

- Store learned agent behaviors as callable procedures, not just text in the system prompt
- Version agent procedures alongside code — changes to procedures are reviewed like code changes
- Separate "what I know" (semantic) from "how I act" (procedural) — conflating them causes policy drift

### Memory Retrieval at Session Start
```
1. Load procedural memory → initialize agent configuration
2. Load most recent episodic summaries → seed working context
3. Query semantic memory with current task → retrieve relevant past context
4. Merge into session context (respecting token budget)
```

## Evidence

- **Anthropic engineering post:** Claude's Research feature uses an orchestrator-worker multi-agent system where the lead agent coordinates parallel subagents, each maintaining separate context windows. Key insight: "once intelligence reaches a threshold, multi-agent coordination enables exponentially greater capability — but the bottleneck shifts from model intelligence to infrastructure: routing, guardrails, tracing, and cost controls." — [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system), Jun 2025
- **Mem0 benchmark study:** Three standard benchmarks now evaluate memory architectures: LoCoMo (1,540 questions, multi-session recall), LongMemEval (500 questions, broader scenarios including knowledge updates), and BEAM (up to 10M memories). Mem0's April 2026 algorithm scored 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query. Hardest open problems: cross-session identity, temporal abstraction at scale, memory staleness. — [Mem0 State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026), Jul 2026
- **Metacto production failure:** A Series B fintech deployed a customer-facing agent that sent a message to 3,400 users promising a promotional rate that did not exist. The agent had no cross-session memory of previous rate queries, no state consistency check, and no human checkpoint before a high-stakes broadcast action. The company faced a $2.1M choice by morning. Root cause: stateless architecture applied to a stateful business relationship. — [Metacto: AI Agent Failures and How to Avoid Them](https://www.metacto.com/blogs/ai-agent-failures-and-how-to-avoid-them), Apr 2026

## Gotchas

- **Memory hit rate collapses silently.** If you don't measure retrieval accuracy in production, you won't know when the vector store is returning noise instead of signal. Add a hit-rate metric alongside latency and cost.
- **Schema migrations are painful.** Facts stored as embeddings become stale when underlying facts change. A user changes their name, a product is discontinued, a policy is updated — your vector store doesn't know. Implement explicit update propagation, not just new-episode appending.
- **Context window optimization is a moving target.** What you can fit in a session changes with model upgrades. Keep working memory **structured** (JSON scratchpad the LLM reads and writes) rather than free-text — structured state survives prompt engineering changes; free-text state drifts.
- **Procedural memory drifts from semantic memory.** If the agent learns "users prefer short responses" from semantic memory but the system prompt says "be thorough," the agent oscillates. Version procedural memory as code and review changes through the same PR process.
- **Privacy blast radius multiplies with persistence.** Every memory store is a new target. Deny-list patterns for `.env`, `.ssh`, PII fields at the tool execution layer (as AZMX AI implements) must apply to memory storage too, not just tool calls.
