# S-2206 · The Context Compilation Stack — When Your Agent Re-Reads the Same Raw Materials Every Single Turn

Your agent is given access to 50 internal documents, a Slack archive, and a codebase with 20,000 lines. You give it a query. The agent spends its first 40 turns reading files — the same files every agent in your organization reads, over and over, every session. The knowledge is there. The agent just hasn't compiled it yet.

This is not a RAG problem. RAG solves retrieval. This is a **compilation** problem — the gap between raw, heterogeneous context and structured, pre-digested knowledge that the agent can query without re-parsing.

## Forces

- **Raw context outlasts its welcome.** The same codebase, documents, and data that your agent reads today will be read by every future agent session, every future agent, for every user who asks a related question. The parsing cost is paid once and then repeatedly wasted.

- **Context quality ≠ context quantity.** A 200,000-token corpus of raw files does not make the agent smarter. It makes the model work harder to find the signal inside the noise. The New Stack (July 2026) reports that the dominant AI agent infrastructure bottleneck is now context quality, not model capability — and that quality is an infrastructure problem, not a model problem.

- **Compilation is a first-class operation.** Andrej Karpathy's pattern (widely discussed in 2026): index raw sources → LLM compiles them incrementally into a structured wiki with summaries, backlinks, and concept articles → agent queries the wiki, not the raw files. This amortizes the parsing cost across all future sessions.

- **The context window is not memory.** Adding a larger context window does not solve the problem — it just delays it. A 1M-token window that contains unprocessed raw files is still expensive to traverse and still delivers worse results than a 50K-token window of structured, compiled knowledge.

## The move

Treat context compilation as a separate, schedulable operation — not a per-session on-demand task.

**Phase 1 — Index.** Ingest raw sources (codebases, documents, logs, API specs, Slack threads) into a compilation pipeline. This runs offline, triggered by CI/CD, cron, or webhook on code/doc changes.

**Phase 2 — Compile.** Run a compilation LLM over the indexed corpus to produce:
- **Entity summaries** — what each file/module/document actually does
- **Cross-references** — backlinks between related concepts
- **Concept articles** — synthesized explanations of patterns, decisions, and conventions
- **Query index** — a structured mapping from question types to relevant sources

**Phase 3 — Query.** Agent sessions query the compiled wiki instead of raw files. The compiled knowledge is orders of magnitude denser than raw context.

```
# Phase 1: Index raw sources (run on CI webhook or cron)
# Phase 2: Compile into structured knowledge wiki
COMPILE_PROMPT = """
You are a knowledge engineer. Read the following raw sources and produce:
1. Entity summaries (what each thing is, in 2 sentences)
2. Cross-references (related entities and why)
3. Concept articles (synthesized explanations of patterns/decisions)
Output as structured JSON with keys: entities, references, concepts.
"""

# Phase 3: Agent queries the compiled wiki, not raw files
# (The compiled wiki is pre-loaded into context or served via tool)
def query_compiled_wiki(question: str, compiled_kb: dict) -> str:
    """Query pre-compiled knowledge instead of re-reading raw sources."""
    relevant = search_compiled(compiled_kb, question)  # fast structured lookup
    # relevant is a curated 2-5KB summary, not 200KB of raw files
    return relevant

# vs. the anti-pattern:
# def query_raw_sources(question: str, raw_files: list) -> str:
#     context = "\n".join(read_all(raw_files))  # pays full parsing cost every turn
#     return ask_llm(question, context)
```

The compilation step is expensive once — but it replaces an expensive-per-session cost with an expensive-once cost. For an organization running 1,000 agent sessions per day against the same codebase, the break-even point is typically hours.

## Key implementation details

- **Compilation triggers:** Hook compilation to CI/CD for code, webhook for docs, cron for Slack/communication archives. Compile on change, not on demand.
- **Staleness:** Compiled knowledge has a TTL. Use document modification timestamps or version hashes to invalidate and recompile stale entries.
- **Scope:** Start with the highest-churn, highest-read-count resources (internal docs, API specs, codebase README files). Compile incrementally.
- **Compiled wiki storage:** Use a simple document store (Markdown files, SQLite with full-text search, or a lightweight vector DB keyed by entity/concept) — not the full raw corpus.
- **Verification:** The compiled wiki must pass a "can a new engineer understand this?" test. If the summary is wrong, the agent will confidently follow the wrong path.

## Receipt

> Receipt pending — 2026-08-06

## See also

- [S-100 · Agentic RAG](s100-agentic-rag.md) — RAG handles on-demand retrieval; this stack handles pre-compilation. Both are complementary layers of the context architecture.
- [S-2185 · The Context Vaporization Stack](s2185-the-context-vaporization-stack-when-your-agent-forgets-everything-the-moment-the-session-ends.md) — Both address the context lifecycle. Vaporization is about memory persistence across sessions; compilation is about proactively structuring context before the session starts.
- [S-1759 · The Context Pollution Stack](s1759-the-context-pollution-stack-when-your-window-is-only-half-full-and-your-agent-is-already-losing-its-mind.md) — Pollution is about signal dilution within a session; compilation prevents pollution by pre-filtering what enters context.
