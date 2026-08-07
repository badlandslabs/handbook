# S-2199 · The Tool Response Gate Stack: When Your Agent Reasons Over Corrupted Output and Nobody Checks

Your agent called a database lookup tool. The tool returned HTTP 200, schema-valid JSON — truncated at 4KB by an undocumented gateway cap. The model correctly identified the response as broken and retried. The tool returned the same truncated payload every time. Seventeen retries later, the model stopped retrying, inferred a plausible partial result, and shipped a wrong answer upstream. Nobody caught it. The logs show 200 OK.

This is not a model failure. This is a response-gate failure — the output-validation gap between "tool executed" and "model reasons."

## Forces

- **The completion bias outranks the error signal.** LLMs are trained to produce coherent answers. Given a truncated JSON blob, the model will hallucinate the missing fields rather than surface an error — because completing is what it does. The garbage-in, garbage-out chain fires before any circuit breaker trips.
- **HTTP 200 proves execution, not correctness.** The tool ran. The schema validated. The response code is green. None of this tells you whether the payload is complete, untampered, or within expected bounds.
- **Schema validation is a necessary floor, not a sufficient ceiling.** JSON Schema catches type mismatches and missing required fields — it does not catch truncation, encoding corruption, silently defaulted values, or a server that returns an HTML error page inside a JSON envelope.
- **Retries amplify the corruption loop.** The agent retries on apparent transient failure. If the tool returns the same corrupted payload every time, the agent's retry logic feeds it the same garbage, reinforcing a confident wrong answer rather than surfacing the error.
- **The failure is invisible to standard monitoring.** `200 OK`, zero exceptions, sub-second latency — the request looks healthy. The wrong decision happens downstream, in the model's reasoning, where your observability stack has no probe.

## The move

Put a validation gate between every tool execution and the model's observation of that output. The gate runs synchronously, before the result enters the context window. It is not part of the agent's reasoning — it is infrastructure.

### Layer 1 — Structural validation (always-on, zero model cost)

```
1. Parse check: is the response valid JSON/bytes?
2. Content-type guard: did the tool return what its Content-Type header claimed?
3. Size bound: is the response within the expected size range for this tool call?
4. Required-field schema check: does the parsed object have the fields the calling code needs?
```

These four checks take microseconds and catch the majority of corruption modes: truncation, HTML-in-JSON envelopes, encoding errors, partial responses.

### Layer 2 — Semantic validation (tool-specific, worth the cost)

For high-stakes tools, add domain-aware checks:

- **Range guards:** a `customer_id` field that is a UUID is structurally valid but semantically wrong if your IDs are integers
- **Reference integrity:** does a foreign key in the returned object actually exist in your system?
- **Business-rule bounds:** a price of `$0.00` is valid JSON; a price of `$-999,999.00` is not a real outcome
- **Content poisoning scan:** check returned strings for known prompt-injection patterns before they enter context

### Layer 3 — The truncation sentinel

Truncation is the most dangerous variant because the response is mostly correct. Detect it:

- **Check `Content-Length` vs. received bytes.** If they differ, the response was cut mid-stream.
- **Look for incomplete structures.** A JSON object with unclosed braces, an array that ends mid-item, a string that terminates with `\u` (incomplete Unicode escape) — all are truncation signatures.
- **Compare against a schema-known size hint.** If the tool's schema annotates that `results` should contain 0–500 items and you received 3, that might be a legitimate partial response — or it might be the gateway ceiling you never documented.

### Layer 4 — Circuit breaker on repeated corruption

If the same tool returns a structurally invalid response three times in a row, the tool is not transiently failing — it has a persistent problem. Break the loop:

```
if consecutive_failures[tool_name] >= 3:
    raise ToolCorruptionError(f"{tool_name} returning invalid output repeatedly")
    # Escalate to human-in-the-loop or switch to fallback tool
```

This directly prevents the 17-retry cascade documented in production traces.

## Implementation pattern

```python
from pydantic import BaseModel, ValidationError
import json

class ToolResponseGate:
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def validate(self, tool_name: str, raw_response, schema: type[BaseModel]) -> BaseModel:
        consecutive_failures.setdefault(tool_name, 0)

        for attempt in range(self.max_retries + 1):
            # Layer 1: Structural
            if not self._is_valid_json(raw_response):
                consecutive_failures[tool_name] += 1
                if consecutive_failures[tool_name] >= 3:
                    raise ToolCorruptionError(f"{tool_name}: invalid JSON after 3 attempts")
                raw_response = retry_tool(tool_name)  # retry Layer 1
                continue

            # Layer 2: Semantic
            try:
                parsed = schema.model_validate_json(raw_response)
                consecutive_failures[tool_name] = 0
                return parsed
            except ValidationError as e:
                consecutive_failures[tool_name] += 1
                if consecutive_failures[tool_name] >= 3:
                    raise ToolCorruptionError(f"{tool_name}: schema validation failed after 3 attempts") from e
                raw_response = retry_tool(tool_name)  # retry Layer 2

class ToolCorruptionError(Exception):
    """Raised when a tool returns persistently corrupted output."""
    pass
```

## When to reach for it

- **Every production agent call.** This is not an edge case — production traces show corrupted tool responses in 2–8% of multi-step runs. The Waxell.ai 2026 production audit found 4 corrupted payloads out of 18 steps in a single real run, all logging 200 OK.
- **Tools behind gateways with undocumented response caps.** Any tool that proxies through an API gateway, load balancer, or middleware is a candidate.
- **High-stakes downstream decisions.** The cost of a wrong decision scales with downstream impact — prioritize gates on tools whose outputs feed into financial, medical, legal, or security decisions.
- **Multi-agent pipelines.** A corrupted output that one agent might catch is a trusted input that a downstream agent will reason over without question.

## Caveats

- **Validation must be faster than the model's timeout budget.** If your gate takes 500ms and your tool has a 1s timeout, the gate adds latency. Profile it.
- **Over-validating cheap tools creates unnecessary latency.** Gate depth should match downstream risk: structural checks are always-on; semantic and poisoning checks are per-tool decisions.
- **Schema versioning is a maintenance cost.** Every time the tool's output schema changes, the gate's expected model must be updated. Use `mcp-contracts` or equivalent to catch schema drift in CI before it reaches production.

## What this unlocks

Without this stack, your agent's reliability is bounded by the weakest tool in your pipeline. With it, you enforce a contract at the boundary — the model only reasons over validated data, retries only fire on genuine transience, and the 17-retry-infinite-garbage loop never starts.

## References

- Waxell.ai: "AI Agent Tool Call Failures: #1 Production Problem" (Jul 2026)
- agentpatterns.tech: "Response Corruption: When Agent Outputs Break"
- Supergood Solutions: "Testing Your Agent Output Contracts Before Production" (Apr 2026)
- GitHub: mcp-contracts/mcp-contracts — MCP schema snapshotting and diff validation
- AgentBRisk: "AI Agent Error Recovery: Retry Logic, Circuit Breakers, Fallback Models" (2026)
