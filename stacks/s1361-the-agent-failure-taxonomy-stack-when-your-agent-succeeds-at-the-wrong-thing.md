# S-1361 · The Agent Failure Taxonomy Stack — When Your Agent Succeeds at the Wrong Thing

When you reach for it: Your agent returned HTTP 200, every tool call succeeded, and the output was wrong. Or it ran 47 tool calls in a loop and billed you $23 before crashing. Or it called the wrong API with valid parameters and deleted the wrong table. Standard error handling — try/catch, HTTP status codes — missed all of these. You need a failure taxonomy built for probabilistic software.

## Forces

- **Agents fail in ways traditional software doesn't.** A standard APM marks a run healthy if HTTP responses are 200 and no exceptions are raised. An agent can return 200 while selecting the wrong tool, violating a tenant boundary, or hallucinating evidence — because the deterministic execution layer did exactly what the probabilistic output told it to do.
- **Failure propagation is the central bottleneck.** An error in step 2 of a 12-step run silently corrupts steps 3–12. By the time the agent surfaces a result, the original cause is buried under 10 layers of compounding inference.
- **LLM API errors are only one failure mode.** Rate limits, invalid output schemas, tool-call hallucinations, context window exhaustion, and loop runaway are all distinct failure types requiring distinct responses. Treating them the same leads to either over-retrying (wasting budget) or under-recovering (missing failures).
- **Recovery is not the same as retry.** A rate limit is transient — retry with backoff works. A semantic error (wrong tool selected) is not transient — retrying the same prompt just produces the same wrong answer faster.

## The move

**Layer your error handling across four distinct failure types**, each with a tailored response:

### 1. Transient failures → retry with exponential backoff + jitter
Rate limits (HTTP 429), server errors (500/503), and timeouts are transient. Exponential backoff prevents hammering a struggling provider. Jitter prevents the "thundering herd" problem where hundreds of agents retry at the exact same second.

```python
import time, random

async def call_with_backoff(agent, task, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            return await agent.run(task)
        except RateLimitError as e:
            if attempt == max_attempts - 1:
                raise
            sleep = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(sleep)
        except Timeout as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(2 ** attempt)
```

### 2. Provider outages → circuit breaker per provider
When a provider fails 5 times in a row, open the circuit and skip that provider for 60 seconds. Without a circuit breaker, your agent wastes time and tokens on a provider that is clearly down while other steps in the pipeline wait.

```python
breakers = {
    "openai": CircuitBreaker(threshold=5, timeout=60),
    "anthropic": CircuitBreaker(threshold=5, timeout=60),
}

def call_with_breaker(provider, agent, task):
    if breakers[provider].state == "open":
        raise CircuitOpenError(provider)
    try:
        return agent.run(task)
    except (RateLimitError, APIError) as e:
        breakers[provider].record_failure()
        raise
```

### 3. Semantic failures → output validation before execution
Agents sometimes hallucinate tool calls — calling functions that don't exist or passing invalid arguments. These are not network errors; they're LLM output errors. Validate before execution.

```python
VALID_TOOLS = {"read_file", "write_file", "run_tests", "search_code"}

def validate_tool_call(tool_name: str, args: dict) -> bool:
    if tool_name not in VALID_TOOLS:
        return False
    # Validate path traversal attempts
    if tool_name == "read_file":
        path = args.get("path", "")
        if ".." in path or path.startswith("/etc"):
            return False
    return True

def execute_tool(tool_name, args):
    if not validate_tool_call(tool_name, args):
        raise InvalidToolCallError(f"Rejected: {tool_name}")
    # safe to execute
```

### 4. Loop runaway → token budget + step cap
Agents can enter tool-call loops where they call the same tool with minor variations indefinitely. Set a hard step cap and token budget per task. When exceeded, halt and surface a partial result with a flag.

```python
MAX_TOOL_CALLS = 50
MAX_TOKENS = 8000
step_count = 0
total_tokens = 0

def run_with_guardrails(agent, task):
    while step_count < MAX_TOOL_CALLS:
        result = agent.next_step(task)
        total_tokens += result.token_count
        if total_tokens > MAX_TOKENS:
            return PartialResult(result, truncated=True)
        if agent.is_complete(result):
            return result
        step_count += 1
    return PartialResult(result, hit_step_cap=True)
```

## Evidence

- **Technical blog — failure taxonomy table:** AI Agent Error Handling article defines four failure types (rate limit, server error, timeout, invalid output) with frequency and fix for each. Rate limits and invalid output are labeled "common"; server errors and timeouts are "occasional." — [aimadetools.com](https://www.aimadetools.com/blog/ai-agent-error-handling)
- **Technical documentation — validation before execution:** Agent Patterns docs recommend explicit validation of tool names and arguments against an allowlist before execution, catching path traversal attempts like `../etc/passwd` before they reach the filesystem. — [agent-patterns.readthedocs.io](https://agent-patterns.readthedocs.io/en/stable/guides/error-handling.html)
- **Research — error propagation as bottleneck:** Zylos Research (Jan 2026) analysis finds that "error propagation is the central bottleneck to robust agentic systems" — failures at step 2 silently corrupt all subsequent steps in the trajectory, and standard monitoring (HTTP 200 checks) fails to surface the root cause. — [zylos.ai](https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery)
- **Industry report — framework recommendation:** Gheware DevOps blog (Jun 2026) recommends LangGraph for production-grade workflows specifically because it enables fine-grained step-level error handling and state inspection at each node boundary — the other frameworks lack comparable control. — [devops.gheware.com](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Don't retry semantic failures.** If the agent selected the wrong tool, retrying the same prompt just produces the same wrong answer faster. Route to a different recovery path (re-prompt with constraints, escalate to human, return partial result).
- **Circuit breakers must be per-provider, not global.** If you have one circuit breaker for all LLM calls and OpenAI fails, you also stop routing to Anthropic — even though the fallback provider is healthy.
- **Output validation runs after the LLM call, not instead of it.** Don't let validation become a gate that requires a second LLM call to decide what went wrong. Validate schemas, not semantics.
- **Partial results are better than silence.** When you hit a step cap or token budget, return what you have with an explicit `truncated` flag. The caller can decide whether to continue. Silent failure hides the incomplete state from the orchestrator.
