# S-1892 · The Agent Runtime Middleware Stack — When Every Cross-Cutting Concern Scatters Across Your Agent Code

Every agent accumulates cross-cutting concerns: retry logic, PII redaction, cost caps, observability, policy gates, rate limiting. In practice these scatter — retry in tool A but not tool B, cost tracking in the main loop but not the sub-agent, PII redaction in one handler but silently absent from another. Adding a new concern means touching every tool. When something breaks, you chase it through a maze of partial implementations.

## Forces

- **Cross-cutting concerns don't belong in any single tool** — but the default move is to implement them there anyway, creating inconsistency
- **Every framework converged on the same shape** — LangChain callbacks, Semantic Kernel filters, Google ADK middleware, AutoGen hooks, Microsoft Agent Framework, Claude Code hooks, and LM-Kit all expose the same three interception points (before/during/after) independently
- **Ordering is load-bearing** — PII redaction must run before cost tracking, fail-closed policy gates must wrap everything, and post-handlers must run in reverse order to unwind cleanly
- **Three failure modes turn middleware into a liability** — silent-swallow (handler catches exception and returns empty), ordering bugs (reverse unwinding broken), and off-protocol egress (error bypasses the pipeline entirely)

## The move

Borrow the onion/middleware pattern from web frameworks. Every model call and tool invocation is wrapped in a composable chain of pre- and post-handlers.

**Pipeline shape:**

```
Pre-handlers (declared order) → [Model/Tool Call] → Post-handlers (reverse order)
```

Pre-handlers: rewrite request, inject context, deny on policy, apply rate limits
Around-call handlers: substitute model, transform parameters, add retry/fallback
Post-handlers: redact output, score/validate, log, track cost, retry on failure

**Placement matrix:**

| Concern | Hook | Why |
|---------|------|-----|
| PII redaction | `before_tool` | See raw args before they reach the tool |
| Cost tracking | `after_tool` | Count tokens after the call completes |
| Policy gate | `before_model` | Deny before any inference cost |
| Retry logic | `around_tool` | Intercept error, retry, unwind |
| Observability | `after_tool` | Emit span after outcome known |
| Rate limiting | `before_model` | Throttle before hitting API |
| Fail-closed | outermost pre-handler | No unwinding = no bypass |

**Three failure modes to test:**

1. **Silent-swallow** — handler catches exception and returns empty/null. Fix: always re-raise or emit a structured error result
2. **Ordering bug** — post-handlers run in wrong order, corrupting shared state. Fix: validate pipeline order in integration tests
3. **Off-protocol egress** — exception propagates outside the handler chain entirely. Fix: wrap the entire pipeline in a top-level try-catch that ensures post-handlers always fire

```python
from langchain.callbacks.base import BaseCallbackHandler
from typing import Any, Optional
import logging

class PIIRedactionHandler(BaseCallbackHandler):
    """Pre-tool: redact PII from arguments before the call."""
    SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "ssn"}

    def on_tool_start(self, serialized, input_str: str, **kwargs):
        # Redact sensitive fields — runs before tool executes
        for key in self.SENSITIVE_KEYS:
            if key in input_str.lower():
                raise ValueError(f"Tool arg contains sensitive field '{key}': blocked by policy gate")
        return input_str

    def on_tool_end(self, output: str, **kwargs):
        # Redact PII from output before returning
        import re
        return re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN-REDACTED]', output)


class CostCapHandler(BaseCallbackHandler):
    """Post-tool: track cumulative cost and abort on overage."""
    def __init__(self, cap_usd: float = 0.50):
        self.cap = cap_usd
        self.total_cost = 0.0

    def on_llm_end(self, response, **kwargs):
        # Rough token cost estimation
        usage = response.llm_output.get("token_usage", {})
        tokens = usage.get("total_tokens", 0)
        self.total_cost += tokens * 0.00001  # ~$10/1M tokens
        if self.total_cost > self.cap:
            raise RuntimeError(f"Cost cap exceeded: ${self.total_cost:.4f} > ${self.cap}")


class FailClosedPolicyHandler(BaseCallbackHandler):
    """Outermost pre-handler: deny on policy violations, always re-raises."""
    BLOCKED_TOPICS = {"weapon", "explosive", "biohazard"}

    def on_llm_start(self, serialized, prompts, **kwargs):
        prompt_text = str(prompts)
        for topic in self.BLOCKED_TOPICS:
            if topic in prompt_text.lower():
                raise PermissionError(f"Policy violation: topic '{topic}' blocked")
        return prompts


# Compose: outermost pre-handler runs first
# Chain: FailClosed → PIIRedaction → CostCap
handlers = [
    FailClosedPolicyHandler(),  # outermost — runs first in, last out
    PIIRedactionHandler(),
    CostCapHandler(cap_usd=0.50),
]
```

**Framework equivalents:**

| Framework | API |
|-----------|-----|
| LangChain | `BaseCallbackHandler` with `on_llm_start/end/error`, `on_tool_start/end` |
| Semantic Kernel | `IPromptFilter`, `ICompletionFilter`, `IToolInvocationFilter` |
| Google ADK | `Middleware`-style interceptors on the agent |
| AutoGen | `register_reply` hook + `on_tool_call` hooks |
| Microsoft Agent Framework | `add_agent_middleware()` — outermost = agent-level |
| Claude Code | `beforeToolCall`, `afterToolCall` hooks |
| LM-Kit | `IPromptFilter`, `ICompletionFilter`, `IToolInvocationFilter` |

## Receipt

> Verified 2026-07-30 — AgentPatterns.ai (2026-06-12) catalogs this as an established pattern. Zylos Research (2026-03-27) independently confirms cross-framework convergence on the same three-hook shape. Microsoft Agent Framework docs confirm middleware termination via `context.result` + `MiddlewareTermination`. Three documented failure modes (silent-swallow, ordering bugs, off-protocol egress) are attested in AgentPatterns GitHub. All six major frameworks (LangChain, Semantic Kernel, Google ADK, AutoGen, Microsoft Agent Framework, Claude Code) ship compatible APIs — the abstraction is framework-portable.

## See also

- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — retry and cost management at the harness level
- [S-1054 · The Agent Interrupt Stack](/stacks/s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — fail-closed termination as a runtime concern
- [S-1147 · The Hook-Injection Pattern](/stacks/s1147-the-hook-injection-pattern-when-your-agent-learns-from-every-failure-and-never-makes-the-same-mistake-twice.md) — cross-cutting persistence of failure-derived rules
