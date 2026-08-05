# S-2174 · The Memory Amnesia Stack — When Your Agent Forgets Everything Between Sessions

You shipped a coding agent last month. Today it re-indexed your repository from scratch, re-learned your coding style, and made the same linting mistake it corrected three weeks ago. Your users notice. The agent doesn't. Every session starts from zero not because the model can't remember — but because you never gave it a memory layer that survives the session boundary.

## Forces

- **Plain files beat frameworks on the benchmarks that matter.** Letta's own evaluation data shows a flat filesystem scores 74% on memory tasks — without any dedicated memory infrastructure. Yet the memory platform market raised $40M+ in 2025 alone. Something is off in how the industry positioned this problem.
- **Provider lock-in is the dirty secret of "universal" memory.** OpenAI's Memory and Anthropic's memory stores work beautifully — inside their respective APIs. Mem0's explicit pitch ("stay neutral — we work across every model, every framework, every platform") is a direct reaction to this lock-in. The moment you use a model-native memory store, you own your data but not your portability.
- **The four memory types are real, and teams keep conflating them.** Working (within-session), episodic (what happened), semantic (what was learned), procedural (how to do things) — a repository re-index is episodic, not semantic. Most teams implement one and call it done.
- **Mem0's October 2025 Series A ($24M) confirmed demand, not correctness.** Basis Set Ventures, Peak XV, Kindred Ventures, GitHub Fund, and Y Combinator funded Mem0 because developers are desperate for memory. But the comparison charts all contradict each other — every vendor wins on their own benchmark. There is no shared scoring rubric, no third-party validation.
- **The reflect pattern (session-end extraction) is the highest-leverage low-complexity win.** Agents that run a structured extraction step at session end — "what facts did I establish, what preferences were expressed, what went wrong?" — dramatically outperform those that rely on raw conversation replay.

## The move

The memory stack isn't one decision — it's four layers, and you should choose them independently:

**Layer 1 — Storage backend (pick by scale):**
- Under 10K memories, single application: **PostgreSQL + pgvector** — $0 extra infra, one connection string, ACID guarantees. The `pg-agent-memory` project (TypeScript-first) and `agentic-memory` (OpenClaw plugin) both target this.
- Multi-agent, distributed, needs cross-platform retrieval: **Qdrant** (hot path), **Weaviate** (tool registries), or **Pinecone** (managed scale).
- Claude Code's approach: **flat filesystem** with `CLAUDE.md` hierarchy (user/project/local scopes), `MEMORY.md` as always-loaded index (first 200 lines or 25KB), and `~/.claude/projects/<project>/memory/` auto-written notes.

**Layer 2 — Memory type to implement (start with episodic, add semantic second):**
- Episodic: store what happened. Conversation logs, tool invocations, outcomes. Enables "why did we decide to do X last time?"
- Semantic: store what was extracted. Facts about the user, project conventions, preferences. Enables "the user prefers Y over Z."

**Layer 3 — Retrieval strategy:**
- Semantic search (vector similarity) is the default but insufficient alone — combine with keyword/FTS for precision.
- Time-decay scoring: memories should age out or get down-ranked. A fact from 18 months ago is less relevant than one from last week unless explicitly flagged.
- Reflection at session end: run an LLM call that extracts structured facts from the session. This is the single highest-ROI memory operation.

**Layer 4 — Tool interface (match your agent framework):**
- Mem0 approach: add a memory layer to an existing agent loop. 3 lines of code. Works across LangChain, CrewAI, AutoGen, custom loops. ~48K GitHub stars.
- Letta approach: treat memory as the runtime. Agents live inside Letta; the platform manages state. MemGPT evolved into Letta, now backed by $10M seed from Felicis.
- Claude Desktop / Anthropic agents: use the built-in Memory tool (`@code.claude.com/memory`) — creates/reads/updates/deletes memory files that persist across sessions.

## Evidence

- **Letta benchmarks (Feb 2026):** Plain filesystem scored 74% on memory tasks — competitive with or exceeding the overhead of dedicated memory libraries on simpler retrieval tasks. Published in Letta's Context Repositories announcement. — [Letta Blog](https://www.letta.com/blog/context-repositories)
- **Mem0 Series A confirmation (Oct 2025):** Mem0 raised $24M (Basis Set Ventures, Peak XV, Kindred, GitHub Fund, YC) on the thesis that "every agentic application needs memory, just as every application needs a database." The open-source repo has ~48K stars. The platform-agnostic pitch is explicit. — [Mem0 Series A](https://mem0.ai/series-a)
- **Product vs. production gap:** One developer's reputation SaaS auto-reply agent ran in production for over a year on a single Postgres table with pgvector — "$0 in extra infrastructure, memory has never been the bottleneck." Meanwhile, enterprise teams are evaluating four-memory-framework pipelines with 20+ primitives before shipping. — [Hamza Shabbir](https://hamzashabbir.dev/article/ai-agent-memory-layer-mem0-vs-letta-vs-zep)

## Gotchas

- **Don't implement vector search without time-decay.** Every retrieved memory is treated equally by default. A preference set 2 years ago will outrank a correct one from yesterday unless you actively score by recency.
- **Conflicting memories are the silent correctness bug.** Mem0, Zep, and Letta all surface "memory conflict resolution" as a feature. Without it, your agent will confidently cite facts that were later superseded. Audit your retrieval pipeline for staleness.
- **The benchmark comparison charts are unscientific.** Mem0 claims 91.6 LoCoMo, 93.4 LongMemEval. An independent evaluation measured Mem0 at 49.0% on LongMemEval. Zep published 84% then corrected to 58%. The scoring methodologies differ. Treat vendor benchmarks as directional, not absolute.
- **Session-end reflection requires a trigger.** Without a forced reflection step, agents accumulate raw conversation logs they never distill into usable facts. Build it as a required post-step, not an optional best-practice.
- **Cross-agent memory sharing is an unsolved design problem.** If two agents work on the same project, they currently maintain separate memories. Shared semantic facts (project conventions) would benefit both, but no standard protocol exists for inter-agent memory sync.
