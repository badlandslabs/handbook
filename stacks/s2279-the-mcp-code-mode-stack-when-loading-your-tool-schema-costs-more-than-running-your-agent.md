# S-2279 · The MCP Code Mode Stack — When Loading Your Tool Schema Costs More Than Running Your Agent

You connected five MCP servers to your agent. GitHub, PostgreSQL, Filesystem, Slack, Linear. Each server exposes 15-20 tools. Every single request injects all 90+ tool definitions — names, JSON schemas, descriptions, return types — into your model's context window before your prompt even begins. At 50 requests/day, this is noise. At 50,000 requests/day, this is your biggest line item, and nobody on your team planned for it. The traditional MCP client pattern was built for connectivity, not cost efficiency. Code Mode flips the model: instead of flooding the context with every tool definition, the agent gets four meta-tools and writes Starlark Python to orchestrate everything else in a sandbox.

## Forces

- **Schema bloat compounds at scale.** Five servers × 20 tools = 100 verbose JSON schemas loaded on every request. At 500 tools, Bifrost measured 1.15M input tokens per request — before a single real instruction ran. Context cost dwarfs compute cost.
- **Tool selection overhead burns model capacity.** The LLM must read, rank, and decide among 100 candidates it cannot meaningfully distinguish. The cognitive overhead degrades tool selection accuracy. More tools, worse choices.
- **Latency compounds token cost.** More tokens in = higher per-token latency + higher inference cost simultaneously. Both dimensions hit at once when you scale.
- **Schema compression feels dangerous.** Shrinking tool definitions sounds like losing capability. The fear of degraded accuracy prevents teams from making the obvious fix.

## The Move

**Replace tool flooding with on-demand tool orchestration via code execution.** Instead of 150 tool definitions in the prompt, expose exactly four generic meta-tools:

| Meta-Tool | What it does |
|-----------|-------------|
| `listToolFiles` | Discover available MCP servers and their capabilities |
| `readToolFile` | Load compact Python stub signatures only when needed |
| `getToolDocs` | Fetch detailed documentation for a specific tool on demand |
| `executeToolCode` | Run Starlark Python with full tool bindings in a sandbox |

The agent writes a small program that orchestrates the actual tools. The program, not the schema, goes in the context.

### Technique 1: Code Mode for Schema Compression

```
# Classic MCP: 150 tool definitions in prompt on EVERY request
# Code Mode: 4 meta-tools + 1 Starlark program

# Agent's Starlark program (what actually goes in the context):
def main():
    github = mcp.connect("github")
    pg = mcp.connect("postgresql")

    # Only the tools actually needed get loaded — on demand
    issues = github.list_issues(state="open", labels=["security"])
    vulns = pg.query(
        "SELECT id, severity, description FROM vulnerabilities WHERE status='open'"
    )

    return summarize(issues, vulns)
```

The Starlark sandbox has access to the MCP tool bindings but only instantiates the ones the code actually calls. Every other tool definition stays out of the prompt.

**Result at 500 tools (Bifrost benchmark):**
- Classic MCP: 1.15M input tokens/request
- Code Mode: ~85K input tokens/request
- Reduction: **92.8%**

### Technique 2: Semantic Caching for Tool Responses

Cache tool response payloads at the gateway level. The cache key is the tool name + a semantic hash of the parameters. Hits bypass both the LLM round-trip and the MCP call.

```
# Bifrost semantic cache TTL reference defaults:
filesystem.read      → 300s   # files change
git.diff             → 90s    # commits happen fast
git.log              → 600s   # history is stable
linear.list_issues   → 1800s  # board updates hourly
web.fetch            → 60s    # content changes constantly
```

Cross-agent cache sharing: one Claude Code session warms the cache that a Codex CLI session reads 15 minutes later. Hit rate stabilizes at 35–55% for typical development workloads.

### Technique 3: Scoped Tool Filtering

Gate tool exposure at the server level based on request context. A read-only GitHub server never exposes `delete_issue`. A data pipeline agent only sees `query` and `transform`.

```
# Gateway-level scope enforcement
scopes:
  - server: github
    role: reviewer
    allowed_tools: [list_issues, get_issue, create_comment]
    denied_tools: [close_issue, delete_issue, update_branch]

  - server: github
    role: maintainer
    allowed_tools: [list_issues, close_issue, merge_pr, create_release]
    denied_tools: [delete_repository, manage_settings]
```

Filtered tools don't appear in the schema dump, so the model never considers them. No prompt engineering required to suppress unwanted tools.

### Technique 4: Provider Routing

Route requests to the cheapest provider that meets quality thresholds. A simple `list_issues` call costs $0.001 on a cheap provider and $0.04 on a frontier model. Route at the gateway, not in your application code.

```
# Route decision at gateway layer
route_decision(tool="linear.list_issues", params={...}):
  if complexity(params) < threshold:
    return provider="claude-haiku", cost_model="cheap"
  else:
    return provider="claude-opus", cost_model="frontier"
```

## When to Use It

| Scenario | Recommendation |
|---------|---------------|
| 3+ MCP servers connected | Code Mode recommended |
| 10+ MCP servers / 200+ tools | Code Mode required |
| Cost > $10K/month on tool schema | Code Mode is cheaper than the compute bill |
| 1-2 servers, simple direct calls | Classic MCP is fine |
| Real-time latency critical (sub-200ms) | Profile first — Code Mode adds one round-trip for the code execution step |

## Receipt

> Verified 2026-08-07 — Bifrost benchmarks (Maxim AI, Jul 2026) reported 92.8% input token reduction at 500 tools. At 1.15M tokens/request (classic) vs ~85K (Code Mode) × 50K requests/day, the math is unambiguous. Semantic cache hit rate of 35-55% for development workloads confirmed across multiple teams (getmaxim.ai articles, Apr–Jul 2026). Production recommendation is to instrument tool schema token count per request before deploying — measure before cutting.

## See also

- [S-1108 · The MCP Tool-Gluttony Stack](/stacks/s1108-the-mcp-tool-gluttony-stack-when-your-agent-has-a-thousand-tools-and-nothing-to-wear.md) — the upstream problem (too many tools)
- [S-1084 · The Tool-Catalog Antipattern](/stacks/s1084-the-tool-catalog-antipattern-when-giving-your-agent-every-tool-hurts-reliability.md) — why tool proliferation hurts reliability
- [S-1056 · The Tool-Arsenal Stack](/stacks/s1056-the-tool-arsenal-stack-when-your-agent-has-400-tools-and-cant-pick-one.md) — tool selection degradation at scale
- [S-2186 · The Agent Budget Guard Stack](/stacks/s2186-the-agent-budget-guard-stack-when-your-agent-is-your-biggest-monthly-expense.md) — token budget enforcement for runaway agents
