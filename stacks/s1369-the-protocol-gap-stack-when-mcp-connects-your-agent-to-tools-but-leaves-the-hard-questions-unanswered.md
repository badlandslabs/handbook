# S-1369 · The Protocol Gap Stack — When MCP Connects Your Agent to Tools but Leaves the Hard Questions Unanswered

MCP (Model Context Protocol) gives you a universal socket between agents and tools — 10,000+ servers, 97M monthly SDK downloads, adopted by every major platform by 2026. But the protocol answers one question and leaves three critical ones hanging: *who is making this request*, *how long should this tool call be allowed to run*, and *what exactly does "error" mean when a language model is the caller?* These aren't implementation details. They're the difference between an agent that recovers gracefully and one that compounds failures into budget events.

## Forces

- **MCP standardizes the wire format but not the operational contract.** The protocol handles tool discovery, schema negotiation, and transport — but says nothing about identity propagation, per-call time budgets, or error semantics. Every team answers these questions differently, and most don't realize they're questions.
- **Agents amplify ambiguity.** A tool that returns HTTP 500 means one thing to a human developer and something different to an LLM that has no concept of HTTP semantics. The agent interprets the error through the lens of its training, retries optimistically, or — worse — hallucinates that the call succeeded. MCP's JSON-RPC error codes were designed for developers, not LLMs.
- **Enterprise requirements collide with protocol silence.** Identity-scoped access control, audit trails, least-privilege enforcement, and data residency all demand knowing *who* the request is for. But the MCP handshake doesn't carry a principal identifier. Every agent-to-tool call looks identical at the protocol layer.
- **Token budgets collapse under sequential tool chains.** A 12-step workflow with unbounded per-step timeouts can exhaust a session budget on a slow tool early in the chain, leaving nothing for critical downstream steps. MCP has no mechanism for distributing a finite time budget across sequential tool calls.

## The move

Build a three-layer protocol gap bridge — one layer for each missing primitive. Each layer lives in an MCP gateway or broker that intercepts requests between client and server and enriches them with what the protocol omits.

### Layer 1: Identity Propagation

MCP's `initialize` handshake carries capability negotiation but no principal identifier. Add it via a gateway that injects identity headers into every tool call:

```
# Gateway intercepts: adds X-MCP-Principal-ID, X-MCP-Principal-Roles, X-MCP-Tenant-ID
# to every JSON-RPC request before forwarding to the MCP server
```

Key design points:
- **Token-bound sessions, not connection-bound** (MCP spec, July 2026 toward stateless transport makes this mandatory)
- Each request carries its own auth context — bolt-on headers at the gateway layer, not per-server SDK changes
- The `principal_id` is the *user on whose behalf* the agent acts, not the agent's own ID — enabling audit trails and least-privilege enforcement downstream
- Server-side: validate the `X-MCP-*` headers at the tool layer, not just at the gateway perimeter

```
# Example: MCP server tool validates identity before executing
def execute_tool(request, context):
    principal = context.headers['X-MCP-Principal-ID']
    allowed_roles = context.headers['X-MCP-Principal-Roles']
    if 'write' not in allowed_roles:
        raise MCPError(code=-32001, message="Insufficient principal scope")
    return do_the_thing(request.params)
```

The CABP (Context-Aware Broker Protocol) pattern from Srinivasan (arXiv:2603.13417, 2026) extends JSON-RPC with a six-stage broker pipeline that routes identity-scoped requests — use this if you need formal routing semantics, or implement the header-injection pattern directly for a lighter touch.

### Layer 2: Adaptive Tool Budgeting (ATBA)

MCP tool calls have no inherent timeout semantics. A slow database query or rate-limited API call can consume the agent's entire session budget, leaving subsequent critical calls to fail with context exhaustion. The ATBA (Adaptive Timeout Budget Allocation) pattern treats sequential tool invocation as a budget allocation problem over heterogeneous latency distributions:

```
# ATBA logic in the MCP gateway
remaining_budget = session_token_budget - tokens_spent
step_number = count_previous_tool_calls
steps_remaining = estimated_total_steps - step_number
per_step_budget = remaining_budget / steps_remaining

# Enforce per-call budget as a hard cutoff
tool_response = call_with_timeout(server, tool, params, timeout=min(per_step_budget, server_sla))
```

Key design points:
- **Estimate total steps** from the agent's system prompt or a lightweight planning call — don't guess; ask the agent to estimate its own plan length
- **Heterogeneous timeout profiles** — a vector DB query might legitimately take 3 seconds; a code execution tool might take 30; treat them differently
- **Budget reservation** for critical-path calls — if a step is labeled high-priority in the tool manifest, reserve proportionally more budget
- **Graceful partial completion** — if budget runs out mid-workflow, capture state and surface it as a structured "paused" signal, not a silent failure

### Layer 3: Structured Error Semantics (SERF)

MCP's JSON-RPC error codes (`-32600` to `-32603`) and freeform `data` fields were designed for programmatic consumption. LLMs cannot reliably map a `KeyError` to a recovery action. SERF (Structured Error Recovery Framework) adds machine-readable failure semantics:

```json
// SERF-enriched error response from MCP server
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32005,
    "message": "Database query returned zero rows",
    "data": {
      "serf": {
        "category": "MISSING_DATA",
        "recoverable": true,
        "retry_after_ms": null,
        "suggested_action": "EXPAND_QUERY",
        "fallback_tools": ["search_similar", "browse_catalog"],
        "escalate_after_attempts": 2
      }
    }
  }
}
```

Key design points:
- **Six SERF categories** cover the error space: `TRANSIENT` (retry immediately), `MISSING_DATA` (expand scope or use fallback), `AUTH_FAILURE` (re-authenticate, don't retry), `SCHEMA_MISMATCH` (refresh tool manifest, don't retry), `RATE_LIMIT` (backoff), `FATAL` (halt, surface to user)
- The agent's system prompt gets a one-page SERF instruction card — "when you see `category: MISSING_DATA`, do X; when you see `category: SCHEMA_MISMATCH`, do Y"
- **Escalation counters** prevent retry storms — SERF carries `escalate_after_attempts`, and the gateway enforces a hard cap regardless of what the agent decides to do
- **Fallback tool registry** — each server maintains a manifest of semantically similar tools, so the gateway can suggest alternatives before the agent invents its own

## Synthesis

These three layers compose into a protocol gap bridge that sits between your MCP clients and servers. The gateway intercepts every request and response, injecting identity, enforcing budgets, and enriching errors. No changes to the MCP servers themselves (mostly), and no changes to the agent framework.

The result: an agent that makes auditable requests with known identity, respects its own resource constraints, and recovers from errors deterministically instead of hallucinating success or retrying into a budget event.

---

## References

- Srinivasan, V. (2026). *Bridging Protocol and Production: Design Patterns for Deploying AI Agents with Model Context Protocol*. arXiv:2603.13417. Three missing protocol primitives: CABP, ATBA, SERF.
- MCP Specification (July 2026): Stateless transport model, token-bound sessions.
- OWASP ASI06: Memory and Context Poisoning — identity isolation relevance.
- GitGuardian (2026): MCP Governance Framework — enterprise auth scope.
- MintMCP (2026): MCP Config Drift — security surface expansion between review cycles.
