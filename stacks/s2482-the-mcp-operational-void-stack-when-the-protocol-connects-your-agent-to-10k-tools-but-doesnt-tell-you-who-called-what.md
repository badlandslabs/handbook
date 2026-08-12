# S-2482 · The MCP Operational Void Stack: When the Protocol Connects Your Agent to 10K Tools but Doesn't Tell You Who Called What, How Long It Should Take, or Why It Failed

Your MCP integration works in the demo. In production, you have no idea which tenant triggered which tool call, whether a 45-second tool execution is hung or working, or why one of six MCP server instances silently returned an error. MCP connects agents to over 10,000 active servers with 97M monthly SDK downloads — but the protocol stops at the connection layer. Three production-critical primitives are absent by design: identity propagation, adaptive tool budgeting, and structured error semantics. This is the MCP operational void, and it doesn't show up in benchmarks.

## Forces

- **MCP standardized discovery and invocation — not operation.** The protocol handles "what tools exist" and "call this tool with these args." It has no mechanism for passing user identity, request context, or budget metadata through the tool call chain. Every production gap that requires this information must be solved by each team independently.
- **Tool timeouts are a guess.** There is no protocol-level guidance for how long a tool should take. Agents either hard-code timeouts per tool or use a global default. When a tool that usually takes 2s starts taking 45s (legitimate deep search), the agent doesn't know whether to wait, retry, or escalate. A 500ms timeout on a legitimate slow tool and a 30s timeout on a hung tool both look like "good defaults."
- **Error responses are opaque.** MCP defines an `isError` boolean. Production errors have causes, severities, retryability, and downstream implications. Returning `isError: true` tells the agent "something went wrong" but nothing about whether to retry, wait, fall back, escalate, or abort. Agents treat all errors as equivalent and apply the same retry policy to a transient network blip and a quota-exhausted permanent failure.
- **Cross-tenant isolation is a deployment problem, not a protocol one.** When one agent makes a tool call on behalf of a user, the MCP request carries no identity metadata. The tool server must independently verify the caller's identity from out-of-band context. If the deployment doesn't implement this — and most custom servers don't — tenant A's data can leak into tenant B's results. NIST NVD CVE-2026-5374 is a documented cross-tenant authorization flaw in MCP server deployments.

## The move

**Three gaps, three mitigations:**

### 1. Identity Propagation — CABP (Context-Aware Broker Protocol)

Extend MCP JSON-RPC calls with a `context` block carrying identity-scoped routing metadata:

```json
// Before (standard MCP)
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": { "name": "customer_db", "arguments": {"query": "SELECT ..."} }
}

// After (with CABP identity propagation)
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "customer_db",
    "arguments": {"query": "SELECT ..."},
    "_meta": {
      "context": {
        "user_id": "usr_abc123",
        "tenant_id": "tenant_xyz",
        "session_id": "sess_def456",
        "authorization_scope": ["customer_db:read"],
        "trace_id": "trace_ghi789"
      }
    }
  }
}
```

The MCP server validates `tenant_id` and `authorization_scope` before executing. If `context.tenant_id` doesn't match the caller's provisioned scope, reject with a structured error. This prevents the cross-tenant leakage that CVE-2026-5374 exploits — the vulnerability exists because there's no standard slot for this information, so teams either omit it or implement it inconsistently.

### 2. Adaptive Tool Budgeting — ATBA (Adaptive Timeout Budget Allocation)

Replace static timeouts with a budget-aware allocation system. Each tool call chain has a total token/time budget. Budgets are allocated per hop based on remaining tokens, estimated tool complexity, and historical latency:

```python
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ToolBudget:
    remaining_ms: int
    remaining_tokens: int
    hop_index: int
    total_hops: int

    @classmethod
    def initial(cls, total_ms: int = 30_000, total_tokens: int = 4096, hops: int = 5):
        return cls(
            remaining_ms=total_ms,
            remaining_tokens=total_tokens,
            hop_index=0,
            total_hops=hops
        )

    def allocate_next(self, estimated_cost_ms: int, estimated_tokens: int) -> 'ToolBudget':
        """Allocate budget for the next hop, proportionally from remaining."""
        ms_per_hop = self.remaining_ms // max(1, self.total_hops - self.hop_index)
        tokens_per_hop = self.remaining_tokens // max(1, self.total_hops - self.hop_index)

        allocated_ms = min(ms_per_hop, estimated_cost_ms)
        allocated_tokens = min(tokens_per_hop, estimated_tokens)

        return ToolBudget(
            remaining_ms=self.remaining_ms - allocated_ms,
            remaining_tokens=self.remaining_tokens - allocated_tokens,
            hop_index=self.hop_index + 1,
            total_hops=self.total_hops
        )

    def is_exhausted(self) -> bool:
        return self.remaining_ms <= 0 or self.remaining_tokens <= 0

def call_with_budget(
    mcp_server, tool_name: str, args: dict,
    budget: ToolBudget, depth: int = 0
) -> dict:
    """Call an MCP tool with adaptive budget enforcement."""
    start = time.time()
    estimated_ms = _estimate_latency(tool_name, args)  # from historical p50/p95
    estimated_tokens = _estimate_tokens(tool_name, args)

    next_budget = budget.allocate_next(estimated_ms, estimated_tokens)

    if next_budget.is_exhausted():
        return {
            "status": "budget_exhausted",
            "hop": depth,
            "remaining_ms": budget.remaining_ms,
            "remaining_tokens": budget.remaining_tokens,
            "suggestion": "cascade_or_abort"
        }

    try:
        result = mcp_server.call(tool_name, args, timeout_ms=min(estimated_ms * 1.5, next_budget.remaining_ms))
        elapsed_ms = (time.time() - start) * 1000
        return {"status": "ok", "result": result, "elapsed_ms": elapsed_ms}
    except TimeoutError:
        return {
            "status": "timeout",
            "elapsed_ms": time.time() - start,
            "next_action": "retry_with_fallback" if depth < budget.total_hops else "escalate_to_human"
        }
    except Exception as e:
        return {"status": "error", "error_type": type(e).__name__, "action": _classify_error(e)}

def _classify_error(e: Exception) -> str:
    """Map error to recovery action — key part of SERF."""
    error_signatures = {
        "RateLimitError": "backoff_and_retry",
        "AuthError": "do_not_retry",
        "TimeoutError": "retry_with_exponential_backoff",
        "QuotaExceeded": "backoff_and_notify",
        "TransientError": "retry_with_jitter",
        "ValidationError": "do_not_retry_fix_args",
    }
    return error_signatures.get(type(e).__name__, "log_and_escalate")
```

ATBA solves two problems: it prevents a single slow tool from consuming the entire chain budget (leaving nothing for downstream tools), and it provides deterministic fallback decisions when budget is exhausted instead of letting the agent guess.

### 3. Structured Error Semantics — SERF

Replace `isError: true` with typed, actionable error responses:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": 42901,
    "message": "Rate limit exceeded on API endpoint",
    "data": {
      "error_type": "rate_limit",
      "retryable": true,
      "retry_after_ms": 2500,
      "fallback_available": ["cache_lookup", "degraded_mode"],
      "circuit_breaker_state": "half_open"
    }
  }
}
```

Error taxonomy for MCP tool servers (SERF core codes):

| Code Range | Category | Retry Policy | Example |
|------------|----------|--------------|---------|
| 4xxxx | Transient (network, timeout) | Retry with backoff | 40101 Timeout |
| 429xx | Quota/Rate limit | Backoff + notify | 42901 Rate limit exceeded |
| 403xx | Auth/Authorization | Do not retry | 40301 Invalid scope |
| 422xx | Validation/Input | Do not retry, fix args | 42201 Invalid parameter |
| 500xx | Server internal | Retry with jitter | 50001 Upstream unavailable |
| 6xxxx | Circuit breaker | Fail fast | 60101 CB open for dependency |

## Receipt

> Verified 2026-08-11 — Research synthesis: arXiv:2603.13417 (Srinivasan, March 2026) — "Bridging Protocol and Production: Design Patterns for Deploying AI Agents with Model Context Protocol." Three protocol gaps identified through enterprise deployment: identity propagation (CABP), adaptive tool budgeting (ATBA), structured error semantics (SERF). CVE-2026-5374 cross-tenant authorization flaw from NIST NVD. AgentSeal audit: 1,808 MCP servers, 66% security findings. Pinterest production MCP deployment (ZenML case study, March 2026) demonstrates JWT-based authorization on top of MCP (workaround for missing identity propagation). CABP/ATBA/SERF are proposed mechanisms — not yet in MCP spec, so the entry covers the operational patterns teams must implement themselves until the protocol matures.

## See also

- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — the publishing/infrastructure side of MCP risk; this entry covers the operational side
- [S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — MCP as the universal plugin substrate beneath orchestration choice
- [S-2408 · The Measurement Gaming Stack](s2408-the-measurement-gaming-stack-when-your-eval-infrastructure-is-part-of-the-attack-surface.md) — benchmark infrastructure exploits; the MCP operational void is the production equivalent for tool infrastructure
