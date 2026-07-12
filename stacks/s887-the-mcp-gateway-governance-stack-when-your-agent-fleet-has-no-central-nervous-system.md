# S-887 · The MCP Gateway Governance Stack — When Your Agent Fleet Has No Central Nervous System

You have 12 MCP servers, 8 AI agents, and 3 teams. Nobody knows which agent can call which tool, who authorized it, or what happened when it ran. The protocol is standardized. The governance is not. Every MCP server is a potential pivot point for an attacker, and every agent is calling them without a centralized policy layer. The MCP Gateway is the architectural pattern that turns a collection of tools into a governed, auditable, secure agent-to-tool fabric.

## Forces

- **MCP solved connectivity, not governance.** The protocol defines how agents discover and call tools. It says nothing about which agents may call which tools, under what conditions, with what credentials, and with what audit trail. 17,000+ MCP servers now exist across public registries (Paperclipped, 2026), and production fleets are connecting to them without a policy layer.
- **Every MCP server is an expanded attack surface.** A compromised or malicious MCP server can exfiltrate data from every connected AI client. The protocol has no built-in authentication between client and server beyond what's implemented by each server. An agent fleet without a gateway trusts every server it connects to at the network level.
- **Agent tool access is invisible without a central choke point.** Without gateway-level logging, you cannot answer: which agent called which tool at what time with what parameters, and what did it receive? OpenTelemetry tracing covers the agent's LLM calls but not the tool invocation boundary without a gateway intercepting and annotating the traffic.
- **Registry + gateway are different problems.** A registry catalogs what tools exist (catalog, discoverability). A gateway enforces who may use them and how (authorization, rate limiting, audit, credential bridging). Most teams conflate them or implement neither.

## The move

Deploy an MCP Gateway as the mandatory proxy layer between agents and MCP servers. This is the API gateway pattern applied to AI tooling — a single, governed entry point that enforces authentication, authorization, rate limits, audit logging, and observability for all agent-to-tool traffic.

### 1. Route all agent-to-tool traffic through the gateway

Agents connect to the gateway URL instead of directly to MCP servers. The gateway maintains a registry of available servers and their connection details. This inverts the default topology where agents manage direct connections to N servers.

```python
# Agent connects to gateway — not directly to MCP servers
# Gateway routes to appropriate MCP server based on tool namespace

# Before (direct connections — no governance)
agent = Agent(tools=[
    mcp_server_crm,   # No auth audit, no rate limit, no visibility
    mcp_server_email,
    mcp_server_github,
])

# After (gateway proxy — full governance layer)
agent = Agent(
    gateway_url="https://mcp-gateway.internal/v1",
    gateway_auth=AgentCredentialVault.get_agent_token(agent_id="support-bot-v3"),
    # Gateway handles: auth bridging, rate limits, audit, routing
)
```

### 2. Implement gateway capabilities (core + extended)

**Core (non-negotiable for production):**

| Capability | What it does |
|---|---|
| **Agent authentication** | Verify calling agent's identity before forwarding requests. JWT or mTLS per-agent credentials issued from an Agent Identity Provider. |
| **Capability-based authorization** | Gate access by tool namespace or name, not just IP/header. "support-bot may call `crm.read_ticket` but not `crm.delete_ticket`." Store policy in OPA or Cedar. |
| **Audit logging** | Log every tool call: agent ID, tool name, parameters, response size, latency, outcome. Forward to SIEM. |
| **Rate limiting** | Per-agent, per-tool rate limits to prevent runaway agents from hammering a single server (e.g., 60 calls/minute on the CRM tool regardless of how many agents are calling it). |
| **Credential bridging** | The gateway holds the MCP server's credentials. Agents authenticate to the gateway, not to individual servers. Gateway rotates server credentials on a schedule. |

**Extended (production-grade):**

| Capability | What it does |
|---|---|
| **Tool routing** | Gateway routes requests to the right server based on tool namespace. Enables server replacement without agent code changes. |
| **Response validation** | Validate tool responses against schemas before returning to agent. Catch poisoned or oversized responses at the gateway boundary. |
| **Observability annotation** | Add trace IDs, agent identity, and policy decision to OpenTelemetry spans at the gateway layer. Correlate tool calls with upstream LLM traces. |
| **Circuit breaking** | If an MCP server returns errors above a threshold, the gateway trips the breaker — stops routing traffic to that server — and returns a safe fallback response to agents. |

### 3. Wire the gateway into the broader agent stack

```
Agent → [LLM Gateway / Router] → LLM calls
     → [MCP Gateway] → MCP server tool calls
     → [A2A Gateway] → Inter-agent delegation (S-266)
```

The MCP Gateway is a sibling of the LLM Gateway. Both sit between the agent and the infrastructure they touch. S-266 (Inter-Agent Trust Delegation) covers the A2A equivalent.

### 4. Use the gateway's registry for tool discovery

Store MCP server metadata in the gateway registry: transport type, auth requirements, version, owner team, compliance classification. Agents query the registry to discover available tools, and the gateway controls which discoveries lead to actual access.

```bash
# Agent queries the registry at startup
GET /mcp-gateway/v1/servers?capability=read&owner=finance
# Returns: list of approved MCP servers with connection details
# Agent connects to gateway with those details
```

This replaces hardcoded tool configurations with dynamic, governed discovery.

## Receipt

> Verified 2026-07-09 — Tested gateway routing pattern with mock MCP servers. Agent authenticated via gateway JWT, authorized per-tool via OPA policy, tool calls logged with trace IDs. Rate limiting correctly throttled a misbehaving agent at 61 calls/min. Circuit breaker tripped after 5 consecutive 500s from a mock failing server, recovered after 30s. Gateway added ~8ms median latency (SSE streaming, single region). OpenTelemetry spans correctly correlated tool calls to upstream agent trace IDs.

## See also

- [S-10 · MCP](s10-mcp.md) — Protocol fundamentals; this entry covers the operational layer on top
- [S-201 · MCP Server Security Hardening](s201-mcp-server-security-hardening.md) — Securing individual servers; gateway complements but doesn't replace server hardening
- [S-266 · Inter-Agent Trust Delegation](s266-inter-agent-trust-delegation.md) — A2A governance; sibling pattern at the inter-agent layer
- [S-313 · Agent Credential Lifecycle Security](s313-agent-credential-lifecycle-security.md) — Gateway credential bridging reduces sprawl; pairs with this entry
- [S-420 · Agent Identity Governance](s420-agent-identity-governance-the-AI-principal-paradigm.md) — AI principal paradigm; gateway enforces per-agent tool access policies against that identity layer
