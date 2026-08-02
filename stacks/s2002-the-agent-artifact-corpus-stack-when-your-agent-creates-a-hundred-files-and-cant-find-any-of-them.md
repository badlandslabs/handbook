# S-2002 · The Agent Artifact Corpus Stack — When Your Agent Creates a Hundred Files and Can't Find Any of Them

[An AI agent operating continuously accumulates a growing corpus of files — code, reports, research, configs, logs, artifacts. Left unmanaged, the corpus becomes technically present but practically inaccessible. Each new session effectively starts from scratch.]

## Forces

- **The accumulation gap.** Agents create files constantly: session outputs, generated code, research dumps, reports, logs. After 3 months of daily use, a single research agent may have 400+ files with no consistent naming, structure, or indexing scheme.
- **Human retrieval patterns vs. agent file reality.** Humans organize files by anticipating future retrieval: folders, naming conventions, dates. Agents write files based on task context at write-time — names like `output.txt`, `result.json`, `report.md` are common and destructive when the corpus grows.
- **Context window as a hard ceiling.** The only way an agent can "see" its files is by reading them into the context window. A 300-file corpus with 50MB of content cannot be fully loaded. Agents default to only reading the most recent files — making older artifacts effectively invisible.
- **The naming-is-retrieval illusion.** When there are 10 files, `ls` suffices. When there are 400, naive listing produces noise. Without a manifest, finding a specific analysis from 6 weeks ago requires O(n) scanning that exhausts context before the agent starts the actual task.
- **Cross-session continuity vs. session-local amnesia.** A well-organized artifact corpus bridges the gap between sessions. An unorganized one means every new session re-discovers what the previous session already knew.

## The Move

**Layer 1 — The Artifact Manifest**

Maintain a machine-readable manifest at the corpus root (`~/.agent/manifest.jsonl`) that every agent write appends to. Each entry:

```
{"path": "reports/q3-analysis-2026-07-15.md", "type": "report", "session_id": "s-2026-07-15-3a7f", "created": "2026-07-15T14:22:00Z", "summary": "Q3 revenue analysis for Acme Corp, includes charts", "tags": ["finance", "acme", "q3-2026"], "parent_task": "acme-quarterly-review"}
```

The manifest is append-only on write and updated on delete. The agent reads the manifest (not the full corpus) at session start to understand what's available.

**Layer 2 — Corpus Structure with Conventions**

Enforce a directory hierarchy by artifact type:

```
.agent/
  manifest.jsonl        # Master index
  corpus/
    reports/            # Structured documents
    code/               # Generated source files
    data/               # JSON, CSV, extracted data
    logs/               # Session traces, execution logs
    research/           # Web scrapes, article dumps
    configs/            # Agent configuration, prompts
```

File naming follows `{type}-{topic}-{date}-{hash}.{ext}`. The type prefix enables glob-based retrieval without reading the manifest: `ls corpus/reports/`.

**Layer 3 — Semantic Index (RAG-adjacent)**

For corpora over ~100 files, add a lightweight semantic index. A simple approach: embed the `summary` field of each manifest entry into a vector store (or even a BM25 index). The retrieval step:

1. Agent receives a query (e.g., "what did we decide about the Acme pricing model?")
2. Query the index → returns top-5 manifest entries
3. Agent reads only those files, not the full corpus

> Receipt pending — implementation walkthrough pending live test

**Layer 4 — Lifecycle Policies**

Not everything should live forever. Implement a tiered lifecycle:

| Tier | Retention | Policy |
|------|-----------|--------|
| Hot | 7 days | Full content in context |
| Warm | 30 days | Manifest entry + summary only |
| Cold | 90 days | Manifest entry only |
| Archive | 90+ days | Compressed, offloaded to cold storage |

A `CORPUS_SIZE_THRESHOLD` env var triggers eviction: when the warm tier exceeds N files, the coldest entries compress. The manifest entry is never deleted — it serves as a pointer to archived content.

**Layer 5 — Write-Time Hygiene Gates**

Don't wait for retrieval to discover the problem. Enforce hygiene at write time:

```
Before write:
1. Does a similar file exist? (check manifest by tag/summary similarity)
2. Does this file need a manifest entry? (yes, always)
3. Does this file match the naming convention? (reject or auto-fix)
4. Will this exceed the corpus size budget? (warn, don't block)
```

A lightweight agent tool (e.g., `corpus-check`) wraps these gates. It's not a hard blocker — the agent can override with `--force` — but the friction makes hygiene the path of least resistance.

## The Contrarian Angle

Most agent memory literature focuses on *LLM memory* (semantic, episodic, procedural stores inside the model). The artifact corpus is a separate, harder problem: files the agent creates exist on the filesystem, outside the model's context window. You can have perfect memory architecture and still lose every file the agent ever wrote if the corpus is unorganized. The two problems require different solutions.

## Receipt

> Verified — Zylos Research, "Agent Artifact Organization and Content Management Patterns" (2026-06-14): 300 files + good organization → 2 operations max to retrieve. 300 files without organization → full corpus scan required. Pattern confirmed by Google ADK `ArtifactService` (GCS-backed persistent artifact storage), Fordel Studios corpus management findings, and agent workspace design patterns in LangGraph and CrewAI.

## See also

- [S-365 · MCP Supply Chain](s365-mcp-supply-chain-from-npx-to-production-catalog.md) — SBOM and provenance for the tools layer; artifact management is the output-side complement
- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys.md) — idempotency keys ensure artifact writes are safe to retry; both patterns deal with "did this actually succeed?"
- [S-1954 · The Agent Session Continuity Stack](s1954-the-agent-session-continuity-stack-when-your-agent-forgets-everything-at-midnight.md) — session continuity is the temporal problem; artifact corpus is the spatial problem
