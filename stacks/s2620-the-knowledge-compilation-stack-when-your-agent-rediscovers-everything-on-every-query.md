# S-2620 · The Knowledge Compilation Stack — When Your Agent Rediscovers Everything on Every Query

Your agent re-reads the same 15 documents on every user question. It contradicts itself from one session to the next. It spends 40% of its first-response tokens on re-orienting to raw source material instead of answering the question. This is not a model problem. It is a knowledge architecture problem.

## Situation

You run a RAG pipeline. Every user question triggers a vector search across raw documents. The agent gets back chunk fragments, re-reads them, and produces an answer. On the second question, it re-does the search. On the third question from a different angle, it re-reads the same chunks again. The knowledge was there. The agent did not retain it.

## Forces

- **Raw sources are human artifacts, not agent-native.** Documents are written for people who can read around ambiguity, fill in context, and cross-reference. Agents retrieve fragments that assume all this background. Each fragment is only interpretable with the others — so the agent must retrieve and re-synthesize a cluster on every query.
- **RAG re-runs discovery on every question.** The vector similarity search re-weights the same documents every time. The agent re-derives the same synthesized understanding. At 100 queries/day across a 500-document corpus, the LLM re-reads and re-digests the same material thousands of times. This is the token cost of not compiling.
- **Context window waste compounds silently.** A typical RAG retrieval round-trip consumes 8–15K tokens per query. The synthesis step adds another 4–8K. At 1,000 queries/day, that is 12–23M input tokens/day on retrieval overhead alone — before any actual task is done.
- **Compiled knowledge changes the tradeoffs entirely.** Karpathy's LLM Wiki pattern (widely adopted by mid-2026 agent builders) inverts this: compile once, query many. The first ingestion pass is expensive. Every subsequent query is fast and consistent — because the wiki already contains the synthesized understanding, cross-references, and contradiction flags.

## The Move

**Replace raw-source RAG with a two-phase knowledge compilation layer.**

### Phase 1: Compile — build the knowledge artifact once

```
Raw sources (PDFs, Markdown, code) → Ingest agent → Structured wiki
```

The compilation agent:
1. Reads all raw sources for a domain or project
2. Extracts entities, facts, and relationships
3. Synthesizes topic pages — each one a coherent narrative, not a fragment
4. Resolves contradictions between sources (flags them, picks the newer/more authoritative, notes the discrepancy)
5. Builds cross-links — `[[Entity]]` references between related topic pages
6. Writes to an append-only knowledge directory (`.wiki/` or similar)

This is a one-time or infrequent cost. On a 500-document corpus, expect 2–6 hours of compilation time and significant token spend — but it happens once, not per query.

### Phase 2: Query — retrieve from the compiled artifact

```
User question → Query the wiki → Compiled topic pages → Agent answer
```

The agent now retrieves fully synthesized pages, not raw chunks. A question about "our deployment process" returns a curated page with the steps, exceptions, and cross-references — not 12 chunk fragments that the agent must mentally reassemble.

### Incremental update: re-compile only what changed

The critical engineering challenge is keeping the compiled knowledge fresh without full recompilation. The approach:

1. **Watch raw sources** for modification timestamps
2. **Diff against the wiki** — which wiki pages mention changed sources?
3. **Re-compile affected pages** only — re-run the synthesis agent on the changed sources + their related pages
4. **Re-synthesize linked pages** if the relationships changed

This keeps compilation cost proportional to change surface, not corpus size.

## Receipt

> Verified 2026-08-14 — Pattern validated against: Karpathy's LLM Wiki gist (widely implemented via agent-wiki npm package, openclaw_llm-wiki-compiler with 54 commits); SuperML.dev "MCP Bloat Tax" analysis (Atlassian MCP Teamwork Graph: 48% token reduction via structured query vs raw chunk retrieval, May 2026); VentureBeat "Context Architecture Replacing RAG" (Redis Iris, May 2026); The New Stack "Context Layer Bottleneck" (Karpathy cited on compile step dominance, July 2026). Implementation references: agent-wiki npm (compile-once-query-many), openclaw_llm-wiki-compiler (markdown wiki output), llm-wiki-hermes skill (Hermes-native).

## See also

[S-2607](s2607-the-agentic-memory-stack-beyond-the-context-window.md) · [S-2600](s2600-the-agentic-rag-failure-taxonomy-stack-when-your-agent-retrieves-forever-calls-every-tool-and-answers-nothing.md) · [S-2619](s2619-the-agent-memory-architecture-stack-when-your-agent-knows-not-who-it-is.md)
