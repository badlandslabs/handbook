# S-1858 · The Agent Runtime Middleware Stack — When Every Cross-Cutting Concern Scatters Across Your Agent Code

You add retry logic to the LLM call. Then cost capping to the LLM call. Then PII redaction before the LLM call. Then logging after the LLM call. Then the same four things for every tool call. Six months later, your agent is 3,000 lines of interleaved business logic and infrastructure glue — and every new cross-cutting concern requires touching every call site. The Agent Runtime Middleware Stack fixes this: compose cross-cutting concerns as ordered pre/post handler chains that intercept every model invocation and tool call, without a single line of change to agent logic.

## Forces

- **Every framework converged on the same pattern independently.** Claude Code (conditional hooks), OpenAI Codex CLI (plugin hooks), LangChain/LangGraph (callbacks), Google ADK (interceptors), AutoGen (hook system), and Semantic Kernel (filters) all built functionally identical middleware — because the problem is structural, not incidental.
- **Call-site pollution is irreversible once it's in.** Adding one concern at a call site seems harmless. By the tenth concern, you have a wall of infrastructure code obscuring every line of actual agent logic. The cost of reorganizing grows faster than the cost of adding.
- **Ordering matters and is invisible.** A retry middleware that re-sends a request with modified parameters must run before a cost-cap middleware that counts tokens. Post-handlers must unwind in reverse order. Getting this wrong produces silent bugs — requests that succeed but weren't logged, retries that bypass policy.
- **Async and streaming break the naive chain.** When a model call streams tokens, `after_model` fires per token. A naive cost-cap that reads the full response in `after_model` will deadlock. Middleware must be async-aware.
- **Middleware failure is not a binary.** A post-handler that throws doesn't mean the operation failed — the user got their answer. Decide: fail-closed (abort the operation) or fail-open (log and continue).

## The move

**Build an ordered handler chain.** Pre-handlers run declared-order before the call; post-handlers run reverse-order after, so wrappers nest correctly. Every model invocation and tool call passes through this chain uniformly.

**Five interception points, two phases:**

| Point | Phase | Use for |
|-------|-------|---------|
| `before_model` | pre | inject context, check policy, deny early |
| `modify_model_request` | wrap | substitute model, transform params, add retry/fallback |
| `after_model` | post | cost tracking, PII redaction, logging, response rewrite |
| `before_tool` | pre | argument validation, credential injection, permission check |
| `after_tool` | post | result sanitization, error classification, state sync |

**Composite middleware from concerns, not call sites:**

```python
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage
from typing import Any, Dict, Optional
import logging, time, json

# --- Pre-handler: policy gate ---
class PolicyGateHandler(BaseCallbackHandler):
    """Deny requests that violate known policy rules before they reach the model."""

    def __init__(self, blocked_topics: list[str], blocked_patterns: list[str]):
        self.blocked_topics = blocked_topics
        self.blocked_patterns = blocked_patterns

    def on_chat_model_start(self, serialized: Dict, messages: list, **kwargs):
        prompt = str(messages)
        for topic in self.blocked_topics:
            if topic.lower() in prompt.lower():
                raise PermissionError(f"Policy gate: topic '{topic}' is blocked")
        for pattern in self.blocked_patterns:
            if pattern.lower() in prompt.lower():
                raise PermissionError(f"Policy gate: pattern '{pattern}' is blocked")

# --- Wrap handler: retry with exponential backoff ---
class RetryOnTimeoutHandler(BaseCallbackHandler):
    """Wrap the model call with retry logic, substituting a fallback on persistent failure."""

    def __init__(self, max_retries: int = 2, backoff_base: float = 1.0):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._attempt = 0

    def on_chat_model_start(self, serialized: Dict, messages: list, **kwargs):
        self._attempt = 0

    def on_retry(self, retry_state: Dict, **kwargs):
        self._attempt += 1
        if self._attempt > self.max_retries:
            # Substitute a smaller fallback model after exhausting retries
            serialized["name"] = "gpt-4o-mini"
            logging.warning(f"Retry exhausted, substituting fallback model")

# --- Post-handler: cost and token tracking ---
class CostTrackerHandler(BaseCallbackHandler):
    """Track per-call and cumulative token usage for budget enforcement."""

    def __init__(self, budget_limit: int = 1_000_000):
        self.budget_limit = budget_limit
        self.total_tokens = 0

    def on_llm_end(self, response: Any, **kwargs):
        usage = response.llm_output.get("token_usage", {}) if hasattr(response, "llm_output") else {}
        tokens = usage.get("total_tokens", 0)
        self.total_tokens += tokens
        logging.info(f"Tokens this call: {tokens}, cumulative: {self.total_tokens}")
        if self.total_tokens > self.budget_limit:
            logging.error(f"Budget exceeded: {self.total_tokens}/{self.budget_limit}")

    def on_tool_end(self, output: str, **kwargs):
        # Estimate tool-call cost and accumulate
        estimated_cost = len(str(output)) / 1000 * 0.0001
        logging.info(f"Tool output ~${estimated_cost:.4f}")

# --- Post-handler: PII redaction ---
class PIIRedactionHandler(BaseCallbackHandler):
    """Strip PII from model outputs before they're passed to tools or returned."""

    def __init__(self, patterns: Dict[str, str]):
        # patterns: {"email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"}
        self.patterns = patterns

    def _redact(self, text: str) -> str:
        import re
        for label, pattern in self.patterns.items():
            text = re.sub(pattern, f"[{label} REDACTED]", text)
        return text

    def on_llm_end(self, response: Any, **kwargs):
        if hasattr(response, "lc_serializable"):
            # Walk and redact message content
            for message in (response.generation_info or {}).get("messages", []):
                if hasattr(message, "content"):
                    message.content = self._redact(str(message.content))

# --- Composite the chain ---
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")
llm.with_config(
    callbacks=[
        PolicyGateHandler(
            blocked_topics=["medical", "legal_advice"],
            blocked_patterns=["SSN", "credit_card"]
        ),
        RetryOnTimeoutHandler(max_retries=2),
        CostTrackerHandler(budget_limit=2_000_000),
        PIIRedactionHandler(patterns={
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        }),
    ]
)

response = llm.invoke([HumanMessage(content="Summarize the Q3 report for user john@example.com")])
print(response.content)
# Policy gate passes. Retry handler active. Cost tracked. john@example.com → [email REDACTED].
```

**Key ordering rules:**
1. `PolicyGateHandler` first — deny before any cost is incurred.
2. `RetryOnTimeoutHandler` next — retry logic wraps the call itself.
3. `CostTrackerHandler` and `PIIRedactionHandler` last among pre/post — they observe without modifying behavior.

**Streaming-aware cost cap:**

```python
class StreamingCostCapHandler(BaseCallbackHandler):
    """Streaming-safe: caps token count incrementally, never buffers the full response."""

    def __init__(self, max_tokens: int = 5000):
        self.max_tokens = max_tokens
        self._token_count = 0

    def on_llm_new_token(self, token: str, **kwargs):
        self._token_count += 1
        if self._token_count > self.max_tokens:
            raise StopIteration(f"Token cap {self.max_tokens} reached after {self._token_count}")
```

**Failure-mode decisions — document them:**

| Concern | Failure behavior | Rationale |
|---------|-----------------|-----------|
| Policy gate | Fail-closed | Policy violations must not propagate |
| Retry | Fail-closed after N retries | Persistent failure indicates a real problem |
| Cost tracking | Fail-open | Observability should not block delivery |
| PII redaction | Fail-closed | PII exposure is a compliance event |

**Test the chain in isolation:**

```python
def test_policy_gate_order():
    """Policy gate must run before retry — not after spending tokens on a blocked request."""
    handler = PolicyGateHandler(blocked_topics=["medical"])
    callbacks = [handler, RetryOnTimeoutHandler()]
    llm = ChatOpenAI(model="gpt-4o").with_config(callbacks=callbacks)
    try:
        llm.invoke([HumanMessage(content="Give me medical advice about antibiotics")])
    except PermissionError as e:
        assert "Policy gate" in str(e)
        assert handler._attempt == 0  # retry never fired
```

**Anti-patterns:**
- Adding one-off logging to specific tool handlers instead of a post-handler — it won't apply to new tools.
- Throwing in `after_model` — the response already reached the user; prefer logging + alerting.
- Middleware that reads the full response to count tokens in streaming mode — use `on_llm_new_token`.
- Forgetting reverse-order unwinding when nesting composable middleware groups.
