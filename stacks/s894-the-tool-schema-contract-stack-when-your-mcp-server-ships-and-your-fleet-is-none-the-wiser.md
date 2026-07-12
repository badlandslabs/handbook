# S-894 · The Tool Schema Contract Stack — When Your MCP Server Ships and Your Fleet Is None the Wiser

Your CI pipeline passes. Your unit tests green. Your MCP server ships v2.1.0. Within hours, three agents across two teams start failing silently — not crashing, just producing wrong results. The tool `query_customers` still returns results; the agent still calls it. The parameter `tier` was renamed `segment` and the server now ignores the unrecognized field. No error. No alert. Just quietly wrong answers propagating downstream. This is the tool schema contract gap: the protocol has no mechanism to pin, diff, or enforce the schema contract between an agent and its tools. You have a fleet of agents running against a moving target.

## Forces

- [S-883 MCP Schema Drift](s883-the-mcp-schema-drift-stack-when-your-agent-uses-a-tool-that-no-longer-exists.md) detects when tool shapes diverge from cached definitions — but it doesn't prevent the divergence or version the contract. Detection is not the same as governance.
- [S-887 MCP Gateway Governance](s887-the-mcp-gateway-governance-stack-when-your-agent-fleet-has-no-central-nervous-system.md) controls *who calls which tool* — but not *what the tool's interface actually is*. A governed agent can still call a drifted tool correctly by protocol, incorrectly by semantics.
- MCP servers expose tools via JSON schemas — but unlike OpenAPI for REST, there is no built-in contract versioning. When a server updates, every agent that cached the old tool definition is now running against an implicit new contract.
- Tool descriptions are the primary signal agents use to decide *how* to call a tool. When those descriptions change — even slightly — agent behavior changes invisibly. There is no review gate, no diff notification, no rollback.
- With 12,000+ public MCP servers and fleets running 30+ agents, the surface area for schema-level failures is enormous. A breaking change in one shared server can silently degrade an entire agent fleet.

## The move

### 1. Snapshot the contract at load time

Every time an agent connects to an MCP server, record a schema fingerprint — not just the tool names, but the full JSON schema of every parameter, return type, and description. Tools like `mcp-contracts` (github.com/mcp-contracts/mcp-contracts) automate this: run `mcp-contracts snapshot` on first connect, store the result as `v1`, and tag it with the server version. This gives you a ground-truth record of what the agent was actually given.

```
mcp-contracts snapshot --server my-server --output ./contracts/my-server-v1.json
```

### 2. Classify changes into three distinct failure modes

Standard schema diffing misses the most dangerous failures. MCP tool changes fall into three categories requiring different defenses:

**Schema breaks** (loud): A required parameter is added, a return field is removed, a type changes. `mcp-contracts diff` catches these. Block deployment until agents re-discover the updated schema.

**Semantic breaks** (silent): The schema is unchanged but the behavior shifted. `query_customers` still accepts `tier`, but it now filters by a different internal logic. No parameter changed. No error fired. Detecting this requires behavioral tests — run the tool with known inputs and assert the outputs match expected shape and content. This is the hardest category because it lives entirely below the protocol surface.

**Language breaks** (AI-specific): The tool description changes, subtly reshaping how the model decides to call it. A description that read "returns up to 100 matching records" now reads "returns the top 5 most relevant records." The agent still calls the tool — but the result set is now catastrophically smaller. Catch this by pinning tool descriptions in the agent's system prompt or tool registry, and alerting on any description delta that exceeds a semantic similarity threshold (e.g., cosine similarity < 0.85 on embedding vectors).

### 3. Pin the contract in the agent's tool registry

Don't let agents discover tools at runtime without a version anchor. The tool registry (or MCP gateway) should store:

- Server version + schema fingerprint at time of registration
- Minimum acceptable schema version (pinned contract)
- TTL: how long before re-discovery is forced (48h is a reasonable default; lower for volatile servers)

When an agent connects, the registry serves the pinned schema — not the live server's current schema. The agent works against a known-good contract. Schema updates are promoted through the registry only after CI validation.

### 4. Gate schema updates through a contract review pipeline

Before a server change propagates to agents:

1. **Snapshot** the new server schema (`mcp-contracts snapshot --server my-server --output new.json`)
2. **Diff** against the pinned contract (`mcp-contracts diff --old old.json --new new.json`)
3. **Classify** each change (schema break / semantic break / language break)
4. **Run behavioral tests** against the new schema with a test agent
5. **Alert** on any change in a production-serving tool — requires human sign-off for schema breaks and language breaks
6. **Push** the new contract to the registry only after all gates pass

### 5. Detect the silent failures you can't prevent

For semantic breaks that slip through: instrument tool calls at the gateway layer. Log input parameters + returned shape for every tool call. Run periodic regression: replay recent tool call inputs against the current server and compare return shapes. A divergence in expected field count, value distribution, or response structure triggers an alert — even if the call "succeeded" by protocol standards.

```
# Example regression check
tool_regression_check("query_customers", last_100_inputs, expected_schema_v12)
# Alert if: returned_field_count drops > 20%, or expected_fields missing in > 5% of responses
```

## See also

- [S-883 · MCP Schema Drift](s883-the-mcp-schema-drift-stack-when-your-agent-uses-a-tool-that-no-longer-exists.md) — the detection half of this problem
- [S-887 · MCP Gateway Governance](s887-the-mcp-gateway-governance-stack-when-your-agent-fleet-has-no-central-nervous-system.md) — the policy layer that wraps the contract
- [S-141 · Source Schema Contract Versioning](s141-source-schema-contract-versioning.md) — the same pattern applied to external API sources
- [F-182 · MCP Server CVE Supply Chain Exploits](f182-mcp-server-cve-supply-chain-exploits.md) — the security surface that compounds with ungoverned schema changes
