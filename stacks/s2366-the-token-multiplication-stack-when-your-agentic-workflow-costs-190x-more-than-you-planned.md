# S-2366 · The Token Multiplication Stack

When your agentic workflow costs $5.40 per task — and you budgeted $0.03. Inference is 85% of your AI bill, and you still don't know which agent step is burning it.

## Forces

- A chatbot makes 1 LLM call. An agentic workflow makes 10–20 — planning, tool selection, execution, verification, error recovery, response synthesis. This arithmetic compounds at scale.
- Frontier reasoning models (Opus 4.8, GPT-5) cost **190× more** per task than fast small models (Haiku 4.5, GPT-4o-mini). The default agent scaffold routes everything to the top tier.
- Token waste in agentic loops is **structurally invisible**: retry storms, redundant tool calls, and context accumulation all look like legitimate work. Nothing errors. Everything bills.
- Enterprise teams report 3–5× cost overruns against initial projections — not from model price, but from volume. Model API prices dropped 80%; agentic token volume grew 20×.
- `[max_iterations]` caps prevent infinite loops but don't distinguish productive 20-step agents from broken ones burning tokens identically.

## The move

**Three layers of control: detect, route, throttle.**

### Layer 1 — Meter every step

Tag each agentic span with its own token count. If you can't see which step costs what, you can't fix anything.

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def agent_step(step_name: str, llm_callable, *args, **kwargs):
    span = tracer.start_span(f"agent.{step_name}")
    with span:
        span.set_attribute("step.type", step_name)
        span.set_attribute("step.attempt", 1)

        for attempt in range(1, MAX_RETRIES + 1):
            span.set_attribute("step.attempt", attempt)
            result = llm_callable(*args, **kwargs)

            # Semantic success check — HTTP 200 ≠ correct output
            if is_semantically_correct(result):
                span.set_attribute("step.outcome", "success")
                span.set_attribute("step.tokens", result.usage.total_tokens)
                return result

            span.set_attribute("step.outcome", "retry")
            span.add_event("retry", {"attempt": attempt})
            backoff(attempt)

        span.set_attribute("step.outcome", "exhausted")
        raise AgentStepError(f"{step_name} failed after {MAX_RETRIES} attempts")
```

### Layer 2 — Route by task complexity, not default

Replace "always use frontier model" with a three-tier router:

```python
from anthropic import Anthropic
client = Anthropic()

COMPLEXITY_PROMPT = """Classify this task as ROUTING_TIER: simple|medium|complex

Rules:
- simple: classification, extraction, formatting, routing logic
- medium: summarization, code review, multi-step reasoning under 5 steps
- complex: multi-tool orchestration, open-ended planning, adversarial inputs"""

def route_task(task_description: str, task_history: list[str]) -> str:
    prompt = f"{COMPLEXITY_PROMPT}\n\nTask: {task_description}\nHistory: {len(task_history)} prior steps"
    response = client.messages.create(
        model="haiku-4.5",
        max_tokens=10,
        system="Output exactly one word: simple, medium, or complex.",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip().lower()

# Example: planning step → Sonnet (medium); extraction → Haiku (simple)
MODEL_MAP = {
    "simple": "haiku-4.5",
    "medium": "sonnet-4.6",
    "complex": "opus-4.8",
}
```

This alone cuts costs 60–80% on well-scoped agents.

### Layer 3 — Throttle the amplifiers

Three silent cost amplifiers that nobody catches until the bill arrives:

**A. Retry storm control** — Not all retries are equal. Distinguish semantic failures (tool returned bad data) from transient failures (HTTP 429).

```python
import time

def agent_retry(task_fn, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            result = task_fn()
            # Semantic validation — don't retry on good output
            if is_successful(result):
                return result
            # Exponential backoff keyed to failure *type*, not just attempt number
            backoff = 2 ** attempt * 0.5  # 0.5s, 1s, 2s
            time.sleep(backoff)
        except TransientError as e:
            # HTTP 429, 500, timeout → retry with backoff
            time.sleep(backoff_from_retry_after(e))
        except SemanticError as e:
            # Tool returned wrong schema or empty result → don't retry the same way
            raise  # fail fast, escalate
    raise MaxRetriesExceeded(f"Failed after {max_attempts} attempts")
```

**B. Tool call deduplication** — Agents re-call tools with identical parameters when context refetches from memory or RAG.

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_tool_result(tool_name: str, params_hash: str) -> dict:
    """Deduplicate identical tool calls within a session window."""
    return call_tool(tool_name, params)

# In the agent loop, replace direct tool calls with cached version:
def agent_tool_call(tool_name: str, params: dict) -> dict:
    params_hash = hash(frozenset(params.items()))
    if cached := cache_get(tool_name, params_hash):
        span = get_current_span()
        span.add_event("tool.cache_hit", {"tool": tool_name})
        return cached
    result = call_tool(tool_name, params)
    cache_set(tool_name, params_hash, result, ttl_seconds=300)
    return result
```

**C. Context budget guard** — Roll off old context before it accumulates silently. S-1035 covers the capacity gap; this is the cost dimension of the same problem.

```python
MAX_CONTEXT_TOKENS = 150_000  # Stay below the degradation cliff
SUMMARY_PROMPT = "Summarize the following agent history in 500 tokens or fewer, preserving: goals, decisions made, errors encountered."

def trim_context(messages: list[dict], max_tokens: int = MAX_CONTEXT_TOKENS) -> list[dict]:
    total = sum(m(count_tokens(m["content"])) for m in messages)
    if total <= max_tokens:
        return messages
    # Keep first (system + tools) and last N turns; summarize the middle
    system_and_tools = [m for m in messages if m["role"] in ("system", "developer")]
    history = [m for m in messages if m["role"] not in ("system", "developer")]
    summary = summarize_history(history[-10:])  # Last 10 turns summarized
    return system_and_tools + [{"role": "user", "content": f"[Prior history summary]\n{summary}"}] + history[-2:]
```

### Putting it together

The full stack:

1. **Meter** — per-step token attribution via OpenTelemetry spans
2. **Route** — complexity-based model dispatch (Haiku for simple, Sonnet for medium, Opus for complex)
3. **Throttle** — retry storms (type-keyed backoff), tool call deduplication (LRU cache), context budget guard (rolling summarization)
4. **Alert** — set per-task cost thresholds; alert when any single task exceeds 3× the p50 for its complexity tier

> Receipt pending — 2026-08-09 (pipeline not yet instrumented)

## Forces (revisited)

- Token multiplication is a structural property of agentic loops, not a model quality issue. More capable models don't fix it; architectural controls do.
- The gap between what agents *should* cost and what they *do* cost is 3–5×. Most teams don't find out until the monthly bill.
- Prompt caching (S-08) helps with repeated prefixes but doesn't address the compounding call volume from loops. Model routing (S-06) helps with tier selection but doesn't address the 10–20× call count inflation. This entry covers the structural layer between them.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — tier selection strategy
- [S-08 · Prompt Caching](s08-prompt-caching.md) — repeated prefix cost reduction
- [S-1035 · The Context-Capacity Gap](s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — context degradation mechanics
- [S-2365 · The Bounded Recovery Ladder](s2365-the-bounded-recovery-ladder-when-your-agent-stops-making-progress-but-nobody-knows-why.md) — iteration and retry infrastructure
