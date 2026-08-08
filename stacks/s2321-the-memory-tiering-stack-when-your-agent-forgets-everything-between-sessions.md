# S-2321 · The Memory Tiering Stack — When Your Agent Forgets Everything Between Sessions

When your agent completes a task today and returns next week knowing nothing — no preferences, no project conventions, no prior decisions. The moment you want continuity across sessions, you hit the gap between stateless inference and persistent intelligence.

## Forces

- **Context windows are finite but growing** — a 200K-token window sounds like memory, but sending full history every call is expensive and attention degrades regardless of size
- **Session state and long-term knowledge are different problems** — a single conversation's history is not the same as learned preferences across weeks
- **Forgetting is gradual, not catastrophic** — agents don't crash when they drift; they quietly get worse, which is harder to detect than hard failures
- **Context quality matters more than context volume** — the bottleneck is identifying which information the model needs, not having more of it
- **~65% of enterprise AI failures** in 2025 traced to context drift or memory loss, not token exhaustion (Forrester, 2025)

## The Move

Layer memory across three tiers, managed by the agent itself — not dumped into the context window wholesale.

### The Three-Tier Architecture

1. **HOT — Active Working Context** (8k–32k tokens)
   - What the agent sees right now: current task, recent tool calls, immediate scratchpad
   - Stored in context window; evicted on session end
   - This is what Claude or GPT acts on directly

2. **WARM — Session & Episodic Memory** (compressed but persistent within a project)
   - Conversation history compacted via summarization, not raw append
   - Project facts: tech stack, conventions, architectural decisions
   - Survives session restarts; managed by the agent writing/reading structured files
   - The "3-file pattern" (context.md, notes.md, history.md) is the lightweight version

3. **COLD — Semantic / Long-Term Memory** (vector store or knowledge graph)
   - Facts, preferences, and learned knowledge across all sessions
   - Retrieved via semantic search at session start and on relevant queries
   - Mem0's approach: single-pass extraction, entity linking, multi-signal retrieval (semantic + BM25 + entity), temporal reasoning
   - agentmemory (26.7k GitHub stars): SQLite + iii-engine, compresses session observations into structured memory — Session 1 sets up JWT auth → Session 2 already knows auth uses `jose` in `src/middleware/auth.ts`

### Session vs Memory Distinction (Google ADK pattern)

| | Session | Memory |
|---|---|---|
| **Scope** | Single conversation | Across all conversations |
| **Survives restart** | Yes (persisted) | Yes |
| **Content** | This chat's turns | Learned preferences, facts |
| **Lifecycle** | Compacted when too long | Accumulates, never overwritten |

### Compaction Strategies (before context drifts)

- **Anchored summarization**: compress old conversation turns into persistent summary notes, anchored to key facts that must survive
- **Tool-result clearing**: discard noisy intermediate tool outputs from context while keeping final results — now a [Claude Developer Platform feature](https://www.anthropic.com/news/context-management)
- **Structured note-taking**: agent writes notes to external files (`NOTES.md`, project memory) at natural breakpoints; reads them back at session start
- **LLM-as-memory-manager**: Mem0's approach — the LLM itself decides what to store, when to retrieve, and when to forget; not rule-based thresholds

### The "3-File Pattern" (Claude Code / lightweight approach)

Three Markdown files give coding agents persistent memory without infrastructure:
- **`CONTEXT.md`** — project scope, goals, constraints (loaded at session start)
- **`NOTES.md`** — mid-session working memory, decisions, todos (updated continuously)
- **`HISTORY.md`** — completed tasks, outcomes, key facts for future sessions

Critique from the community: CLAUDE.md caps at ~200 lines and goes stale. The 3-file pattern scales better because each file has a defined role and update cadence.

## Evidence

- **Engineering post — Anthropic:** "Structured note-taking, or agentic memory, is a technique where the agent regularly writes notes persisted to memory outside of the context window. These notes get pulled back into the context window at later times." Documents tool-result clearing as a production feature. — [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **GitHub repo — Mem0 (62.8k stars):** New memory algorithm (April 2026) achieves LoCoMo 92.5 (up from 71.4), LongMemEval 94.4 (up from 67.8), BEAM (1M) 64.1 using single-pass ADD-only extraction, entity linking, and multi-signal retrieval. "Memories accumulate; nothing is overwritten." — [mem0ai/mem0](https://github.com/mem0ai/mem0)
- **GitHub repo — agentmemory (26.7k stars):** Session 1 writes JWT auth code, runs tests, fixes bugs → observations compressed into structured SQLite memory. Session 2: "add rate limiting" → agent already knows auth uses `jose` over `jsonwebtoken`, tests in `test/auth.test.ts`. Built on SQLite + iii-engine, no Postgres/Redis required. — [rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)
- **Research survey — Sepah:** Four-tier architecture (Active → Session → Episodic → Semantic) across OpenAI, Anthropic, Azure AI Foundry, AWS EKS. "First wave had no memory hierarchy → token explosions, recursive hallucinations, no observability." — [Agentic Memory Architecture 2026](https://sepahsalar.org/research/agentic-memory-architecture-2026)
- **Blog post — Tian Pan:** "65% of enterprise AI failures in 2025 trace to context drift, not token exhaustion. GPT-4's accuracy drops from 98.1% to 64.1% based solely on position in context window." — [Context Engineering: Memory, Compaction, and Tool Clearing](https://tianpan.co/blog/2026-02-26-context-engineering-memory-compaction-tool-clearing)
- **GitHub gist — 0xK8oX:** The 3-file pattern (context.md, notes.md, history.md) for Claude Code persistent memory, published March 2026. — [AI Agent Context Management: Building Persistent Memory with File-Based Patterns](https://gist.github.com/0xK8oX/06ad3cd873828af4b331ce69eacdcf29)

## Gotchas

- **Don't dump everything into context** — full conversation history degrades attention quality faster than a shorter, curated context. The 3-file pattern exists precisely because brute-force context injection fails.
- **Session persistence ≠ memory persistence** — persisting a conversation's raw history across restarts is a different problem from learning a user's preferences across months. Confusing the two leads to brittle "super-context" prompts that still drift.
- **Context drift has no error signal** — the model keeps running; it just gets quietly wrong. Monitor quality, not just token counts.
- **ADD-only accumulation causes bloat** — Mem0's approach of never overwriting memories is powerful for recall but requires a forgetting/retention policy or the cold tier becomes unmanageable. The LLM-as-memory-manager must have explicit retention logic.
- **SQLite vs vector store is a real tradeoff** — agentmemory uses SQLite for simplicity (no infrastructure), but pure semantic retrieval at scale benefits from a dedicated vector store. The "right" answer depends on query pattern complexity and team infra tolerance.
