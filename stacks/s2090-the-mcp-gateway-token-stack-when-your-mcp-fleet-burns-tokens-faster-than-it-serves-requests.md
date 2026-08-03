# S-2090 · The MCP Gateway Token Stack — When Your MCP Fleet Burns Tokens Faster Than It Serves Requests

Your MCP ecosystem worked beautifully with five agents and twelve servers. Then you scaled to fifty agents across eight servers. Your token bill tripled in a month. Your tool selection latency spiked. Your schema cache hit rate dropped to 31%. And when you audited where the tokens went, you found something uncomfortable: the MCP protocol was designed for developer experience, not production throughput. The mismatch is structural.

The Model Context Protocol solved the integration problem. It did not solve the scale problem. The protocol's core design assumption — that every agent client fetches, caches, and sends full tool schemas on every session — breaks at fleet scale. This is the MCP gateway token stack: the architectural pattern that bridges MCP's developer-experience-first design and production scale requirements.

## Forces

- **The MCP tool-discovery paradigm is O(N×M).** Every session start fetches the full tool catalog from every server. With 10 servers averaging 30 tools each, that's 300 tool definitions per cold start — before the agent has done anything useful. At 1000 sessions/day, this compounds fast.
- **Schema staleness creates a catch-22.** MCP's `tools/list` is a runtime call, not a static artifact. Gate it aggressively and you get stale schemas. Refresh it aggressively and you pay the full round-trip on every session. Neither is acceptable at scale.
- **The token bill lives in tool descriptions, not tool logic.** A well-documented tool runs 200–800 tokens of description. At 50 tools/server × 8 servers, that's 80K–320K tokens per session initialization — before task reasoning begins.
- **Session-aware routing requires centralized state.** MCP's stateless design assumes every agent-replica pair handles its own sessions. In production, you have N replicas behind a load balancer. Without shared routing state, identical requests route to different servers, creating session inconsistency.

## The move

Layer a gateway between MCP clients and servers. The gateway is not a proxy — it is an active translation and optimization layer with four key functions:

### 1. Tool Recommendation (hybrid retrieval)
Rather than dumping all tool schemas into the prompt, the gateway intercepts the tool-list request and returns only the top-K relevant tools for the current task context. Li et al. (arxiv:2607.15593) achieve **98% Top-15 recall** using a hybrid retrieval system (keyword + embedding) over a 1,000-tool corpus, reducing tool selection time by **8.9×**.

```python
# Gateway-side: tool recommendation at session init
async def recommend_tools(session_context: dict, catalog: list[Tool]) -> list[Tool]:
    query_embedding = await embed(session_context["task_description"])
    keyword_scores = bm25_score(session_context["task_description"], catalog)
    embed_scores = cosine_scores(query_embedding, [t.embedding for t in catalog])
    hybrid = 0.4 * normalize(keyword_scores) + 0.6 * normalize(embed_scores)
    return sorted(zip(catalog, hybrid), key=lambda x: x[1], reverse=True)[:15]
```

### 2. Schema Version Registry
Cache tool schemas with a version tag. On `tools/list`, return the cached schema unless the server signals a version change via ETag or explicit version header. A schema version registry with 5-minute TTL covers 98% of drift scenarios while cutting per-session fetch overhead by 80%.

```python
schema_cache: dict[str, CachedSchema] = {}

async def get_schema(server: str, force_refresh: bool = False) -> list[Tool]:
    cached = schema_cache.get(server)
    if cached and not force_refresh and not cached.is_stale(ttl=300):
        return cached.tools
    fresh = await fetch_from_server(server)
    schema_cache[server] = CachedSchema(fresh, version=fresh.etag)
    return fresh.tools
```

### 3. Protocol Adaptation
Legacy servers not built for MCP get wrapped at the gateway. The gateway handles protocol translation (REST → MCP JSON-RPC) with sub-millisecond overhead (P50 ≤ 143μs per Li et al.), enabling MCP access to existing services without modifying them.

### 4. Token Budgeting via Code Mode
Strip verbose tool descriptions at the gateway. Replace with minimal `name` + `code` pairs (the actual parameter signatures). Send full descriptions only on-demand when the agent requests a specific tool's detail. MCPGateway reports **95% token reduction** (500K → 25K tokens) using this technique.

```python
def minimal_tool_card(tool: Tool) -> dict:
    """Code Mode: strip description, keep signature."""
    return {
        "name": tool.name,
        "code": tool.signature,   # minimal: "file_path: str, content: str"
        # full description fetched only when agent explicitly requests it
    }
```

## Receipt

> Verified 2026-08-03 — arxiv:2607.15593 (Li et al., Jul 2026) deployed across 5 cloud regions for 8 months: 98% Top-15 tool recall, 8.9× tool selection speedup, 23.8× token reduction, P50 protocol conversion ≤ 143μs. MCPGateway (open source, MIT) reports 95% token reduction (500K → 25K) via Code Mode on production workloads. Numbers from primary sources.

## See also

- [S-989 · The Tool Surface Stack](s989-the-tool-surface-stack-when-your-agent-has-50-tools-and-picks-the-wrong-one.md) — tool selection is the problem; gateway recommendation is one solution
- [S-999 · The Silent Tool Catalog](s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-your-agent-breaks.md) — schema drift is the failure mode this architecture prevents
- [S-2087 · The MCP Fleet Resilience Stack](s2087-the-mcp-fleet-resilience-stack-when-your-mcp-server-works-for-one-agent-and-breaks-for-one-hundred.md) — retry, circuit-breaking, and chaos testing at fleet scale
