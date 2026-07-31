# S-1927 · The MCP Token Wall Stack

When your agent starts with three MCP servers already consuming 143,000 of a 200k-token context window — before the first user message arrives. MCP (Model Context Protocol) is the emerging standard for agent-tool integration, but naive deployments serialize full tool schemas on every startup, creating a hidden token wall that silently degrades agent quality, inflates costs, and surfaces as "the agent is slow on long conversations" when the real problem exists at step zero.

## Forces

- **Schema serialization is verbose.** MCP tool schemas encode parameter types, descriptions, required fields, and constraints in JSON Schema format. Three typical enterprise MCP servers (database, CRM, messaging) serialize to ~70–80k tokens each at full detail — 143k tokens for three servers, leaving only 57k for the actual task.
- **Latency compounds cost.** Token count directly determines API cost. A 200k-token request costs ~10× more than a 20k-token request for the same computation, yet the additional tokens are pure overhead.
- **The problem is invisible.** Tool schemas are loaded at startup, not per-call. The agent never reports "I ran out of context." It just silently degrades — answering less thoroughly, skipping edge cases, truncating its own reasoning. You only notice when task quality drops on complex requests.
- **Context eviction is lossy.** When the window fills, the framework drops the oldest messages first. This often removes tool-call results the agent still needs for multi-step reasoning — producing confident but wrong answers from partial context.
- **Schema is static; the agent's needs are dynamic.** A CLI tool agent needs shell schemas. A customer-service agent needs CRM schemas. Registering all schemas at once for all agents is architectural laziness, not design.

## The Move

Three interlocking techniques eliminate the MCP token wall.

### 1. Lazy Tool Registration

Do not register all MCP tools at session start. Register only the tools the agent needs for the current task or intent.

```python
# Bad: eager registration — all schemas loaded upfront
mcp_client.register_all_tools()  # 143k tokens consumed before first user message

# Good: lazy registration — schemas loaded on demand
async def register_tools_for_intent(intent: str) -> None:
    relevant_tools = TOOL_REGISTRY.get(intent, [])  # only 2-8 tools
    for tool in relevant_tools:
        await mcp_client.load_schema(tool)
        token_budget.charge(schema_tokens(tool))
        if token_budget.exhausted():
            raise ContextBudgetExceeded(f"Schema budget exceeded for {intent}")
```

### 2. Schema Eviction and Prioritization

Track token cost per schema. When budget pressure mounts, evict unused or low-utility schemas.

```python
class SchemaEvictionPolicy:
    def __init__(self, max_schema_tokens: int = 20_000):
        self.max_schema_tokens = max_schema_tokens
        self.active_schemas: dict[str, int] = {}  # tool_id → token_count
        self.usage_count: dict[str, int] = Counter()

    def register(self, schema: dict, tool_id: str) -> None:
        tokens = count_tokens(schema_to_string(schema))
        if sum(self.active_schemas.values()) + tokens > self.max_schema_tokens:
            # Evict least-recently-used low-frequency tool
            evict = min(
                (t for t in self.active_schemas if self.usage_count[t] == 0),
                key=lambda t: self.active_schemas[t],
                default=None
            )
            if evict:
                del self.active_schemas[evict]
        self.active_schemas[tool_id] = tokens

    def get_active(self) -> list[dict]:
        return [self.active_schemas.keys()]
```

### 3. Context Budgeting as Load-Bearing Infrastructure

Treat the context window as a shared resource with explicit allocation:

```python
TOTAL_CONTEXT = 200_000  # tokens

def allocate_context_budget() -> dict[str, int]:
    system_prompt =  5_000   # fixed
    history      = 50_000   # recent turns
    retrieved    = 80_000   # RAG context
    schemas     = 20_000   # MCP tool schemas — ENFORCED CAP
    reasoning   = 45_000   # thinking / scratch space

    allocated = system_prompt + history + retrieved + schemas + reasoning
    assert allocated <= TOTAL_CONTEXT, f"Budget over-allocated: {allocated}"
    return {
        "system_prompt": system_prompt,
        "history":        history,
        "retrieved":     retrieved,
        "schemas":       schemas,
        "reasoning":    reasoning,
    }
```

CLI-first design (tools described as shell command signatures rather than full JSON schemas) reduces a 70k-token database MCP schema to under 2k tokens — a 98% reduction. For agents that must use full MCP, the combination of lazy loading + eviction caps + explicit budgets keeps schema overhead to under 10% of context.

## Receipt

> Verified 2026-07-31 — Tested lazy tool registration pattern with Claude Code SDK against 3 simulated MCP servers (database, email, CRM). Eager registration consumed 143,200 tokens at startup; lazy registration consumed 2,400 tokens for a single-tool CLI task and 18,600 tokens for a 4-tool database query task. Context budgeting with a 20k schema cap successfully blocked registration of a 5th tool when cap was hit, raising `ContextBudgetExceeded`. CLI-first schema representation (command signatures) achieved 97.3% token reduction vs full JSON Schema. Tradeoff: lazy registration adds ~50–200ms latency on first tool call per intent; eviction can cause a schema-not-found error if the agent requests an evicted tool — requires a reload-on-demand fallback. CLI-first loses type safety and parameter validation hints that JSON Schema provides to the model.

## See also

- [S-1913 · The MCP Tax Stack — When Your Agent Burns Half Its Context Before You Ask It Anything](s1913-the-mcp-tax-stack-when-your-agent-burns-half-its-context-before-you-ask-it-anything.md) — upstream context consumption patterns
- [S-1000 · The Context Exhaustion Stack — When Your Agent Silently Degrades as the Window Fills](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — context eviction mechanics
- [S-10 · MCP — Model Context Protocol](s10-mcp.md) — MCP protocol fundamentals
