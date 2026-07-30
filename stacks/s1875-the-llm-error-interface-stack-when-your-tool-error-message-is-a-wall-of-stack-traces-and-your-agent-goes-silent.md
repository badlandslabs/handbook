# S-1875 · The LLM-Error Interface Stack — When Your Tool Error Message Is a Wall of Stack Traces and Your Agent Goes Silent

Your MCP server throws a `KeyError: 'id'` on a malformed request. The developer sees a Python traceback and fixes the schema. The agent sees the same traceback in its context window and either retries blindly, apologizes for its failure, or silently returns the error as a user-facing result. The problem is not the error — it is the interface across which the error travels: from a machine-readable format to a language model that has no stack trace intuition.

## Forces

- **An LLM is not a developer.** JSON-RPC 2.0 error responses assume a human or a retry loop reads them. An LLM that receives `500 Internal Server Error` with a Python traceback has two options: retry with identical arguments (guaranteed failure) or give up and report the error to the user. Both are wrong in different cases.
- **The MCP spec gives agents `isError: true` and nothing else.** The Model Context Protocol specification provides a standard error format — `code`, `message`, `data` — but these fields were designed for developer-facing APIs, not for autonomous agents that need recovery semantics. A rate limit error and a permission error both return `isError: true`. The agent cannot distinguish them without structured metadata.
- **Retry logic without retryability semantics is a cost sink.** Agents without structured error guidance retry rate-limited calls, permission-denied calls, and schema-mismatch calls equally. Each retry costs tokens and latency, and non-retryable errors accumulate cost without ever resolving.
- **The failure is not the tool — it is the contract.** When a human API consumer gets a `401 Unauthorized`, they look at the response body and fix their credentials. When an agent gets the same response, it needs the same information delivered in a form its context window can act on: a machine-readable code, a retryability flag, and a natural-language next step.

## The Move

The pattern is the **LLM-Error Interface**: designing every tool error response as if the consumer is a language model that needs to make an autonomous recovery decision. This has three layers.

### Layer 1 — Classify the Error by Recovery Category

Not all errors are equal. Before deciding how to format the response, map the failure to one of three error categories:

| Category | Definition | Example | Agent Response |
|----------|-----------|---------|----------------|
| **Transient** | The failure is temporary and the same request may succeed on retry | Rate limit (429), temporary network timeout, lock contention | Retry with backoff |
| **Blamable** | The failure has a correctable cause in the request itself | Schema validation failure, missing required field, wrong tool argument type | Fix the arguments and retry |
| **Fatal** | The failure cannot be resolved by retrying with the same or corrected arguments | Insufficient permissions, quota exhausted, upstream service permanently unavailable | Stop, report to user, escalate |

This taxonomy comes from the Structured Error Recovery Framework (SERF) documented in production MCP patterns (arxiv:2603.13417, Vasundras et al., 2026).

### Layer 2 — Encode the SERF Response

Return every error as a structured JSON object that an LLM can parse and act on. The canonical shape:

```json
{
  "isError": true,
  "error": {
    "code": "QUOTA_EXCEEDED",
    "retryable": false,
    "suggested_action": "Reduce the batch size to 50 records or fewer, then retry. Each record must be under 10 KB."
  }
}
```

The `code` field is a machine-readable string from a controlled vocabulary. The `retryable` boolean is a direct instruction. The `suggested_action` is natural language — not a stack trace — written as if instructing a junior developer who just received this error. The model reads `suggested_action` and incorporates it into its next reasoning step.

For transport-layer failures (connection refused, TLS handshake failure), wrap the underlying error in the same structure:

```json
{
  "isError": true,
  "error": {
    "code": "TRANSPORT_CONNECTION_FAILED",
    "retryable": true,
    "suggested_action": "Retry in 2 seconds. If the connection fails three times, switch to the fallback endpoint at https://api.example.com/v2/fallback"
  }
}
```

The agent reads this and tries again, not because the model figured out the backoff — because you told it to wait two seconds.

### Layer 3 — Wire SERF at the MCP Server Boundary

Implement error wrapping at the transport boundary, not per-tool. This ensures every tool on a server gets consistent error semantics without per-tool boilerplate:

```javascript
// MCP server middleware — wrap every error in SERF shape
async function serfMiddleware(request, next) {
  try {
    return await next(request);
  } catch (err) {
    const isRetryable = err.code === 'ETIMEDOUT' ||
                        err.code === 'ECONNRESET'   ||
                        err.status === 429;
    return {
      isError: true,
      error: {
        code: err.code || 'INTERNAL_ERROR',
        retryable: isRetryable,
        suggested_action: isRetryable
          ? `Retry in ${getBackoffSeconds(err)} seconds.`
          : fixInstruction(err) // human-authored per error type
      }
    };
  }
}
```

For per-tool errors, map the tool's native error codes to SERF codes at the tool handler boundary. A database tool that throws `SQLITE_BUSY` maps to `code: "DB_LOCKED"`, `retryable: true`, `suggested_action: "Retry this query in 3 seconds. If it fails again, wait 10 seconds before a final attempt."` A permission error maps to `code: "PERMISSION_DENIED"`, `retryable: false`, `suggested_action: "The API key does not have the 'read:orders' scope. Add this scope to your credentials and try again."`

### The Contrarian Angle

This pattern is counterintuitive because error handling is treated as an engineering concern, not an agent-design concern. Teams spend weeks optimizing prompts and tool schemas, then ship their MCP servers with default error handlers that return raw exceptions. The error response is part of your agent's interface — it determines what the model can actually do when things break. Designing it is prompt engineering at 3 AM when the API is down.

## See also

- [S-1369 · The Protocol Gap Stack](stacks/s1369-the-protocol-gap-stack-three-missing-mcp-primitives-identity-budget-and-error-semantics.md) — the three MCP primitives that production deployments are missing (identity, budget, error semantics)
- [S-1872 · The Self-Healing Stack](stacks/s1872-the-self-healing-stack-when-your-agent-keeps-running-after-it-shouldve-stopped.md) — semantic guards and recovery circuits for agent failure modes
- [S-1699 · The Framework-RCE Stack](stacks/s1699-the-framework-rce-stack-when-your-agent-framework-becomes-a-code-execution-gateway.md) — tool boundary security; the error interface is the same boundary

## Receipt

> Verified 2026-07-30 — SERF pattern from arxiv:2603.13417 (Vasundras et al., "Bridging Protocol and Production: MCP at Scale") and MCP Server Patterns repository (vasundras/mcp-server-patterns). Error taxonomy (Transient / Blamable / Fatal) consistent with ChatForest MCP Error Handling Guide (March 2026). Transport-layer SERF wrapper pattern adapted from published examples. Receipt pending — run a production MCP server with SERF middleware and observe agent recovery behavior vs. raw error baseline.
