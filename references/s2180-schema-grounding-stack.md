# S-2180 Evidence Bank — Schema Grounding Stack

## Sources

### 1. Tian Pan — "Why SQL Agents Fail in Production: Grounding LLMs Against Live Relational Databases"
**URL:** https://tianpan.co/blog/2026-04-16-sql-agent-database-grounding-schema
**Date:** April 16, 2026
**Author:** Tian Pan (Software Engineer, previously at Uber, Brex, IoTeX)

Key claims:
- Spider 1.0 (5–30 tables): GPT-4o scores 86.6%
- Spider 2.0 (enterprise-scale): drops to 10.1%
- Pinterest: ~20% first-shot acceptance in production; most rejections from table selection errors, not SQL syntax
- Three schema-boundary failure modes: wrong table, wrong business logic, wrong time semantics
- Production data warehouses: 200+ tables, 700+ columns, 3+ SQL dialects

### 2. Tian Pan — "Text-to-SQL in Production: Why Natural Language Queries Fail at the Schema Boundary"
**URL:** https://tianpan.co/blog/2026-04-20-text-to-sql-production-schema-boundary-failures
**Date:** April 20, 2026

Key claims:
- Full DDL dumps fail at enterprise scale (200+ tables)
- Schema context packaging problem: model gets column names but not FK semantics, join paths, downstream dependencies
- Two-stage pipeline recommended: table selection → query generation
- Schema boundary as unit of failure analysis

### 3. Pretensor — "Why your AI agent needs a schema graph, not just SQL access"
**URL:** https://pretensor.ai/blog/mcp-server-database-schema
**Date:** May 26, 2026

Key claims:
- Raw SQL MCP access breaks at ~30 tables; full breakdown at 200+
- Schema graph (FK relationships, join paths, impact analysis, table lineage) as grounding primitive
- Agents hallucinate joins because they lack structural knowledge of the schema
- Knowledge graph provides business-semantic labels beyond raw column names

### 4. Engineered Insight — "Schema Grounding: Why Your Agent Hallucinates SQL (and How to Stop It)"
**URL:** https://engineeredinsight.substack.com/p/schema-grounding-strategies-that
**Date:** 2026

Key claims:
- "Hallucination" labeled failures are grounding gaps, not reasoning failures
- Three-error case study: wrong table (`orders` vs `fact_revenue`), wrong business logic (`amount` includes tax/refunds), wrong time semantics (calendar Q4 vs fiscal Q4)
- Grounding artifacts: structured definitions that encode business semantics
- Evaluate retrieval quality independently from answer quality

### 5. Devinity Solutions — "Agentic RAG in 2026: Why Retrieval Is the New Bottleneck"
**URL:** https://www.devinitysolutions.com/blog/agentic-rag-2026
**Date:** May 18, 2026

Key claims:
- 73% of enterprise deployments fail in production due to retrieval failures, not model failures
- Agentic RAG replaces one-shot embed-and-retrieve with a loop: plan queries, pick sources, inspect results, search again
- Permission-aware retrieval as both security constraint and relevance signal
- Latency/cost tradeoff: agentic answers take multiple model calls, reserve for high-cost-of-being-wrong questions

### 6. Microsoft Command Line — "Grounding at Scale: Engineering the Retrieval System for the Agentic Web"
**URL:** https://commandline.microsoft.com/grounding-system-agentic-web-engineering-retrieval/
**Date:** June 2, 2026
**Author:** Knut Risvik, Distinguished Engineer, Microsoft

Key claims:
- Web IQ grounding system: <165ms P95 latency, 2.5x faster than nearest alternative
- Same infrastructure powers Copilot, ChatGPT, Nasdaq enterprise systems
- Three tightly coupled constraints in grounding: latency, quality, token efficiency
- MCP-native, model-agnostic platform

### 7. Microsoft SQL Server Blog — Schema Boundary Failures
**URL:** https://blogs.bing.com/search/february-2026/elevating-the-role-of-grounding-on-the-ai-web
**Date:** February 2026

Key claims:
- Grounding as foundational infrastructure for AI assistants
- Publisher preference respect in grounding layer
- AI search requires different optimization tradeoffs than classical search

## Related Stacks (cross-references)
- S-984: First-Attempt Architecture — overlaps on first-shot acceptance but different angle (grounding vs verification)
- S-100: Live Data Freshness Contracts — related on data quality hazards surfacing as model errors
- S-2128: Eval Set Decay — related on evaluation methodology for production systems
