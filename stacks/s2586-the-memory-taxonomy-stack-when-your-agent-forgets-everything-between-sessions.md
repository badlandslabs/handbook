# S-2586 · The Memory Taxonomy Stack: When Your Agent Forgets Everything Between Sessions

Every Claude Code session ends and takes with it hours of accumulated context about your codebase, conventions, and preferences. The agent learned your patterns. The session closed. Everything destroyed. Industry-wide, this burns thousands of developer-hours daily re-teaching agents what they already knew.

## Forces

- **Amnesia is the default architecture.** The entire AI agent ecosystem is built on stateless foundations. Every session starts cold. This is treated as normal rather than a defect.
- **Specialization doesn't beat simplicity.** Letta's benchmarks show a plain filesystem scoring 74% on memory tasks — beating specialized vector-store libraries. Complexity doesn't automatically win.
- **Async is non-negotiable in production.** Memory writes that block the response pipeline add latency users feel. Making async memory writes the default took Mem0 until v1.0.0 to learn as the most common production footgun.
- **Memory staleness is invisible.** Agents retrieve old memories that are no longer accurate. No system flags when stored context has degraded.
- **Cross-session identity is unsolved.** How an agent identifies "this user is the same person across sessions" remains one of the three hardest open problems in agent memory.

## The move

Map agent memory to human memory taxonomy — then implement each layer with the simplest tool that works.

**Semantic memory (facts, knowledge, learned rules):**
- Store as structured documents (CLAUDE.md, .cursorrules, rules.md)
- Version-controlled, human-readable, zero infrastructure
- For agents: write learned facts back to project-level files after each session
- The filesystem is the underrated baseline — it's search-accessible, diff-able, and survives sessions

**Episodic memory (events, experiences, past interactions):**
- Embed conversations or action logs into a vector store (Mem0, Zep, Letta)
- Tag episodes with temporal metadata (date, session_id, user_id)
- Implement a "reflection" loop: agent reviews recent actions, extracts what matters, writes a compressed summary back to memory before session end
- The reflection pattern (Shiny-inspired, now standard across 21 frameworks) is the bridge between raw logs and usable knowledge

**Procedural memory (how to do things, workflows, skills):**
- Store as callable skill files or MCP tools
- Zep and Graphiti model this as temporal knowledge graphs — edges encode "when X happened, the agent did Y"
- Skills should be composable: a "fix bugs" skill that chains "read error logs" + "search codebase" + "apply fix" is a procedure, not a fact

**Working memory (current session context):**
- The conversation window — trimmed to stay within context limits
- Implement semantic trimming: when context fills, compress low-relevance turns using an LLM summarizer rather than simple truncation
- Keep a "session state" object that tracks what the agent has already tried

**The production memory stack (2026 consensus):**
- Async writes by default — never block the response pipeline
- Reranking on retrieval — vector similarity returns candidates but often in the wrong order; a cross-encoder reranker fixes this
- State that survives interruptions — Redis or a durable log for crash recovery
- Periodic reflection checkpoints — configurable interval (e.g., every N turns or every N minutes) that dumps working state to episodic store

## Evidence

- **Benchmark study:** Letta's memory benchmarks show plain filesystem at 74% on memory tasks, beating specialized vector-store libraries. Cost: zero infrastructure. Source — *A Memory Architecture for Agentic Systems* (GitHub Gist, spikelab, 45+ sources, 2026-02-06) — [https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)
- **Production requirements survey:** Mem0's 2026 report identifies async mode, reranking, and staleness detection as the three non-negotiable features for production memory. 21 frameworks and 20 vector stores now integrate with Mem0. LoCoMo benchmark (1,540 questions) and LongMemEval (500 questions) are the standard evaluation suites. Source — *AI Agent Memory 2026: Progress Benchmark Report*, Mem0 Engineering (2026-07-18) — [https://mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Real deployment:** Archetypal AI runs 14 AI agents as Cloudflare Durable Objects, each with persistent memory and a constitutional framework ("Seven Laws"). Built specifically to solve agent amnesia for Claude Code, Cursor, and Copilot users. Source — *14 AI Agents Built Persistent Memory for All AI Agents* (Reddit r/ClaudeAI, r/LocalLLaMA cross-post, 2026) — [https://gist.github.com/bsharvey/7cb4d57600408ba4f1bd9745bd688816](https://gist.github.com/bsharvey/7cb4d57600408ba4f1bd9745bd688816)

## Gotchas

- **Memory that never gets retrieved is dead weight.** Storing everything is easy. Retrieving the right thing at the right time is the hard problem — reranking is where most retrieval pipelines lose their edge.
- **Staleness is invisible without instrumentation.** Add a `last_updated` timestamp and a freshness check before injecting memories. An agent acting on a 6-month-old memory about your project structure is a silent failure mode.
- **The filesystem baseline is real but bounded.** It doesn't scale across distributed agents or multi-user systems. Use it for single-agent coding contexts; graduate to a proper episodic store when sessions need to compound across users or tools.
