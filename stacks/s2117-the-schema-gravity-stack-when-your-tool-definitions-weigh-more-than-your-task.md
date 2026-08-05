# [S-2117] · The Schema Gravity Stack — When Your Tool Definitions Weigh More Than Your Task

You connect your agent to five MCP servers, each with ten tools. You send a simple request: "create a ticket." The model spends 72% of its available context window reading tool schemas before it reads your actual request. By the time the model processes what you asked, it has already consumed most of its reasoning room on metadata about what it *could* do — not what it *should* do.

This is **schema gravity**: tool definitions pull the context window inward, bending available reasoning space around themselves. It is invisible because the overhead is structural, not conversational. Nothing is "said" that reveals the waste.

## Forces

- **Schema loads on every turn.** Unlike RAG where you control what's retrieved, MCP servers push their entire tool schema into the context on every request. A modest 5-server × 10-tool setup consumes 15,000–20,000 tokens per turn before the agent processes any user input.

- **The 72% collapse.** Perplexity's internal measurements found tool schemas consuming 72% of available context space in multi-server MCP configurations. The agent is then reasoning in a 28% context window.

- **Adding servers makes it worse, not better.** Every new MCP server increases schema overhead. The natural growth pattern (add tools → add servers) makes the problem worse over time, not better.

- **Naive tool exposure is the default.** MCP tooling defaults to listing all available tools. Teams don't think about what the model needs to *know* — they think about what the model *can* do.

- **The MCP stateful server paradox.** MCP supports stateful sessions, but horizontal scaling requires sticky sessions. Scaling out breaks state; keeping state single-node breaks scaling. No clean answer exists yet.

## The move

**Treat your MCP tool catalog as a context budget, not an asset list.**

```
Anti-pattern: connect all MCP servers, expose all tools
  → 50 tools across 5 servers = 20K+ schema tokens per turn
  → Model reasons in a fraction of the available window
  → Subtle quality degradation that doesn't look like an error

Pattern 1: Lazy schema loading (server-side)
  → Don't call tools/list until the agent selects a domain
  → Only load the schema for the selected tool, not all tools
  → MCP sampling lets the server intercept and guide tool selection

Pattern 2: Tool domain grouping (client-side)
  → Separate MCP servers per domain, not per service
  → Agent connects to "ticketing" server (10 tools) not "hubspot + jira + zendesk"
  → Context cost: O(domains) not O(total_tools)

Pattern 3: Schema compression
  → Strip parameter descriptions to essentials before sending
  → Use short, semantically rich tool names
  → Keep descriptions at keyword density, not prose density

Pattern 4: Context-first schema triage
  → Measure your token budget: context_window × 0.4 (留给任务的) = schema_max
  → If schema tokens exceed budget, triage: remove tools, compress, or split servers
```

```
python
# Schema gravity detector (conceptual)
def measure_schema_gravity(mcp_config, context_window):
    total_schema_tokens = sum(
        estimate_schema_size(tool)
        for server in mcp_config.servers
        for tool in server.tools
    )
    effective_window = context_window - total_schema_tokens
    overhead_pct = total_schema_tokens / context_window * 100
    
    if overhead_pct > 50:
        return {
            "alert": "SCHEMA_GRAVITY_CRITICAL",
            "overhead_pct": overhead_pct,
            "effective_window": effective_window,
            "recommendation": "triage_schemas",
            "breakdown": {
                server.name: sum(estimate_schema_size(t) for t in server.tools)
                for server in mcp_config.servers
            }
        }
    return {"status": "OK", "overhead_pct": overhead_pct}

def estimate_schema_size(tool):
    """Rough token estimate for a tool's MCP schema."""
    return (
        len(tool.name) +
        sum(len(p.name) + len(str(p.description)) for p in tool.parameters) +
        200  # baseline per-tool overhead
    )
```

**For the stateful server scaling problem:**

```
# Don't: single stateless server with no session affinity
# Do: session tokens (MCP protocol feature) + external state store
#     Sessions survive server restarts. Agents reconnect, not restart.
```

## Receipt
> Verified 2026-08-04 — MCP context overhead data sourced from: n1n.ai "Model Context Protocol in Production: Lessons from 97 Million Downloads" (June 30, 2026), Comet.com article on MCP limitations (2026), and web search confirming 72% figure. Sticky session / stateful server scaling challenge confirmed across multiple production reports. The MCP 2026 roadmap (published March 2026) addresses some of these but the production reality lags behind the spec.

## See also
- [S-10 · MCP](s10-mcp.md) — foundational MCP reference; does not cover token overhead
- [S-1177 · The Semantic Tool Router](s1177-the-semantic-tool-router-when-your-agent-sends-200-tool-schemas-to-call-one-function.md) — routing tools vs. loading all schemas; related but complementary
- [S-1035 · The Context Capacity Gap](s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — context window management; overlaps on the "more context doesn't mean better reasoning" theme
- [S-1056 · The MCP Tool Contract Gate](s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — MCP schema versioning and contract testing; different angle
