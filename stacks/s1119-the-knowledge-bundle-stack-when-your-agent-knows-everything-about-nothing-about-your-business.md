# S-1119 · The Knowledge Bundle Stack — When Your Agent Knows Everything About Nothing About Your Business

Foundation models have read the internet. They have not read your data dictionary, your runbooks, or your internal API contracts. The moment you deploy an agent into a real business workflow, it hits a wall: the relevant knowledge is somewhere — in Confluence, in Notion, in Slack threads, in a spreadsheet that lives on someone's Desktop — but the agent has no standard way to find it, read it, or trust it. Teams solve this from scratch every time, building bespoke retrieval pipelines, scraping metadata catalogs, and hard-coding join paths that break when anything changes.

Google Cloud published the Open Knowledge Format (OKF) in June 2026 to give this problem a standard shape. OKF is a simple idea executed well: represent knowledge as a directory of markdown files, where every file carries YAML frontmatter declaring what it is, who owns it, and how it relates to the rest. Any agent can read it. Any tool can write it. It needs no registry, no SDK, and no account.

## Forces

- **The context-assembly problem is everyone's problem but nobody's standard.** Every team building a production agent faces the same gap: how do I give this model the business context it needs? They all solve it differently — RAG pipelines, hard-coded prompts, manual copy-paste — and they all pay the maintenance cost forever.
- **The agent-readable web has a gap between discovery and knowledge.** `robots.txt` and `sitemap.xml` tell agents what pages exist. `llms.txt` tells agents which pages are worth reading. But neither tells agents what the knowledge *means* — its structure, relationships, and provenance. OKF fills this gap.
- **Portable knowledge is governance-unready by default.** The promise of OKF — that you can bundle knowledge and ship it to any agent — cuts both ways. A malicious or stale bundle can misinform an agent just as easily as a good one can empower it. Portability and provenance are in tension.
- **Build-once vs. keep-it-fresh is the real operational challenge.** Generating an OKF bundle from existing docs is tractable. Keeping it current as the docs evolve, as the schema changes, as the API contract shifts — that's the ongoing commitment that determines whether the bundle is a living asset or a snapshot that rots.

## The move

### 1. Understand the five-layer agent-readable stack

OKF is the top layer of a hierarchy that tells agents progressively more:

| Layer | What it tells the agent | Example |
|-------|------------------------|---------|
| `robots.txt` / `sitemap.xml` | What pages exist | Discovery |
| `llms.txt` | Which pages are worth reading | Filtering |
| `AGENTS.md` / `CLAUDE.md` | How to behave in this codebase | Behavior |
| **OKF** | **What the knowledge means and how it relates** | **Context** |
| MCP | How to act on that knowledge | Tools |

OKF sits above MCP in the stack. MCP gives agents *capability* (I can query the database). OKF gives agents *meaning* (I know what this column means and why it matters).

### 2. Structure a knowledge bundle

A bundle is a directory. Each file is one concept. File types are declared in YAML frontmatter:

```markdown
---
type: Metric
title: Monthly Active Users
description: Count of distinct users who performed at least one action in the last 30 days.
owner: data-platform@company.com
version: "2026-06"
related:
  - path: ./tables/user_events.md
  - path: ./playbooks/maus-drops.md
schema:
  source: analytics.user_sessions
  column: user_id
  aggregation: distinct_count
  window: 30d
tags: [growth, engagement, sli]
---

## Monthly Active Users

Calculated from the `user_sessions` table as `COUNT(DISTINCT user_id)` where `session_start >= NOW() - INTERVAL 30 DAY`.

**Known quirks:**
- Bots are filtered via the `is_bot` flag in `user_events`
- Internal employee accounts (email ending in `@company.com`) are excluded
- A user who only views a static page does not count as "active"
```

File types include: `Article`, `Metric`, `Playbook`, `Table`, `Concept`, `API`, `Person`, `Event`. Any type the bundle author needs is valid — the format is open.

### 3. Generate bundles from existing sources

The value of OKF is not hand-authoring markdown. It's converting existing institutional knowledge into the format. Common generators:

```python
# Generate OKF from a database schema
import yaml
from sqlalchemy import inspect

def schema_to_okf_bundle(engine, schema_name: str, output_dir: str):
    """Convert a database schema into an OKF knowledge bundle."""
    from pathlib import Path
    import markdown

    bundle = Path(output_dir)
    bundle.mkdir(exist_ok=True)

    inspector = inspect(engine)
    for table in inspector.get_table_names(schema=schema_name):
        columns = inspector.get_columns(table, schema=schema_name)
        pkey = inspector.get_pk_constraint(table, schema=schema_name)
        fkeys = inspector.get_foreign_keys(table, schema=schema_name)

        doc = {
            "type": "Table",
            "title": table,
            "description": f"Database table in schema {schema_name}",
            "owner": "data-platform@company.com",
            "schema": {
                "source": f"{schema_name}.{table}",
                "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns],
                "primary_key": pkey["constrained_columns"] if pkey else [],
                "foreign_keys": [{"from": k["constrained_columns"], "to": k["referred_table"] + "." + k["referred_columns"][0]} for k in fkeys]
            },
            "tags": [schema_name]
        }
        (bundle / f"{table}.md").write_text("---\n" + yaml.dump(doc) + "---\n\n## " + table + "\n\n" + markdown.markdown(inspector.comment if hasattr(inspector, 'comment') else ''))

# Generate an llms.txt index pointing to the bundle
index = ""
for f in sorted(bundle.glob("*.md")):
    with open(f) as fh:
        doc = yaml.safe_load(fh.read().split("---")[2])
        index += f"- [{f.stem}]({f.name}): {doc.get('description','')}\n"

(bundle / "llms.txt").write_text(index)
```

### 4. Consume the bundle in an agent

An agent reads the bundle directory as a knowledge graph:

```python
import yaml
from pathlib import Path

class OKFBundle:
    def __init__(self, bundle_path: str):
        self.bundle = Path(bundle_path)
        self._index = None

    def index(self) -> dict[str, dict]:
        """Parse all files and build a flat index by title."""
        if self._index:
            return self._index
        self._index = {}
        for md_file in self.bundle.glob("*.md"):
            parts = md_file.read_text().split("---")
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1])
            body = parts[2].strip()
            self._index[meta["title"]] = {
                "meta": meta,
                "body": body,
                "path": str(md_file)
            }
        return self._index

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Simple keyword retrieval. Replace with vector search for production."""
        idx = self.index()
        scores = []
        for title, entry in idx.items():
            score = sum(1 for kw in query.split() if kw.lower() in (title + " " + entry["body"]).lower())
            scores.append((score, title))
        scores.sort(reverse=True)
        return [idx[title] for _, title in scores[:top_k]]

    def inject_context(self, query: str, max_chars: int = 4000) -> str:
        """Build a context string for an agent prompt from retrieved entries."""
        results = self.retrieve(query)
        context = ""
        for r in results:
            context += f"\n\n## {r['meta']['title']} ({r['meta']['type']})\n"
            context += r["body"][:max_chars // len(results)]
        return context
```

### 5. Govern the bundle lifecycle

Portable knowledge is only as good as its freshness:

- **Generate on change**: Wire the bundle build to CI — regenerate OKF files when a schema PR lands, when a runbook is updated, when an API spec changes.
- **Track provenance**: Each file's frontmatter should carry `source` and `version`. When the source changes, the bundle should reflect it within one build cycle.
- **Audit the bundle**: Add a schema validation step (`okf-lint`) to your CI that checks required fields, detects circular links, and flags stale `version` fields.
- **Version-control the bundle**: OKF bundles belong in Git. This gives you diffs, rollbacks, and PR-based review for knowledge changes — the same discipline you apply to code.

## Receipt

> Verified 2026-07-15 — Researched OKF spec from GoogleCloudPlatform/knowledge-catalog (github.com, June 2026), OKF guides from tinycommand.com, witscode.com, and suganthan.com. Confirmed: zero coverage in existing handbook (366 stacks entries, zero OKF references). Confirmed: AGENTS.md covered in S-1084, llms.txt indirectly referenced, MCP covered in S-10. OKF fills the top layer of the agent-readable web stack — above MCP in abstraction, below AGENTS.md in purpose. Core spec verified: directory of markdown files, YAML frontmatter with required fields (type, title, description) + optional (owner, version, related, schema, tags), markdown body, inter-file links via standard markdown.

## See also

- [S-07 · RAG](s07-rag.md) — OKF is a structured alternative to naive vector retrieval; both solve context deficits but OKF is curated, not probabilistic
- [S-10 · MCP](s10-mcp.md) — MCP gives agents tools; OKF gives agents meaning; use both
- [S-100 · Agentic RAG](s100-agentic-rag.md) — Agentic RAG decides what to retrieve; OKF standardizes what the retrieved content means
- [S-244 · Semantic Caching at the Vector Layer](s244-semantic-caching-at-the-vector-layer.md) — Both reduce redundant agent context assembly; semantic caching at the inference layer, OKF at the knowledge-authoring layer
