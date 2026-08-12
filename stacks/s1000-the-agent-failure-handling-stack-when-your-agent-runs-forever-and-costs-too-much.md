# S-1000 · The Agent Failure Handling Stack — When Your Agent Runs Forever and Costs Too Much

Your agent completes the demo. It handles the first ten requests. Then it hits a rate limit, retries with the same bad parameters, loops for forty steps, and bills you $200 for a task worth $2. The problem isn't intelligence. It's the absence of a recovery architecture around every tool call and every reasoning step. Agents fail in shapes single LLM calls don't — and most agent code handles those failures catastrophically.

## Forces

- **Loops are the default failure mode.** When a tool returns an error, the model retries with the same arguments. The error repeats. The model apologizes. The session ends. The user gets nothing.
- **Semantic correctness is invisible to HTTP codes.** A tool can return HTTP 200 with results that are technically valid but contextually wrong — the agent keeps going, compounding the error downstream.
- **Retry logic applied uniformly is worse than no retry logic.** Retrying a 401 (bad auth) burns latency and quota. Retrying a 429 (rate limit) is correct only if you back off. Retrying a semantically wrong response never helps.
- **Agents optimize for completion, not quality.** Without explicit success criteria and checkpoints, a broken agent will run to step 50 and return "done" because it reached its cap — not because it succeeded.

## The Move

Build a layered failure architecture where every error type routes to a specific recovery strategy. The layers from innermost to outermost:

**1. Classify before acting.** Every tool response — HTTP call, retriever, model output — goes through an error classifier before retry logic fires. Classify into: transient (retry), permanent (escalate), semantic (validate), or unknown (cap and escalate).

**2. Hard step caps with state checkpointing.** Set a maximum step count (12 is the common recommendation; Rajpoot found this sufficient for most agentic tasks). Checkpoint state at each step so that when the cap is hit, you can resume from the last good state rather than restart from scratch.

```
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
    checkpoint(state)  # save mid-run state
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

**3. Tool-level retries with exponential backoff for transients.** Only retry on 429 (rate limit), 500/503 (server error), and timeout. For 429, respect the `Retry-After` header if present. Use exponential backoff (base 2, jitter) for other transients. Never retry 401 or 404 — these require re-auth or a different tool.

**4. Semantic output validation before continuing.** After any tool call, run the output through a small, fast verifier model (or structured schema check) before passing it to the next reasoning step. Rastogi's Modelia.ai image pipeline would have caught flawed approvals with a pre-routing quality gate. AIMADetools encodes this as explicit tool call validation:

```python
VALID_TOOLS = {"read_file", "write_file", "run_tests", "search_code"}
async def validate_tool_call(tool_name: str, args: dict) -> bool:
    if tool_name not in VALID_TOOLS:
        return False
    # Tool-specific argument validation
    if tool_name == "read_file":
        path = args.get("path", "")
        if ".." in path or path.startswith("/etc"):
            return False  # Path traversal attempt
    return True
```

**5. Fallback chains for persistent failures.** When the primary tool fails after retries, route to a fallback tool rather than failing the whole agent. A weather agent that can't reach OpenWeatherMap falls back to visual weather APIs; a code interpreter that times out falls back to a simpler sandbox. Debnath (Crusoe) emphasizes that "reliability cannot be retrofitted" — plan for fallback before the agent runs.

**6. Loop detection.** Track consecutive identical tool calls and identical tool arguments. If the same tool fires 3 times in a row with the same args, something is wrong — stop and escalate. Harshrastogi at Asynq.ai found their candidate evaluation agent "got stuck in loops" without this guard. Additionally track when the agent's response shrinks (it's re-saying the same thing) vs. when it grows (it's genuinely reasoning).

**7. Cost circuit breakers.** At Asynq.ai, the candidate evaluation agent "cost 3x what we budgeted." Set a cost ceiling per task and per session. When the ceiling is hit, stop, record the partial result, and escalate to human review. This is distinct from step caps because a single step can cost $50 if the model call is large.

**8. Partial success + human escalation.** When the agent hits a cap or unresolvable error, return what it accomplished plus a structured failure report (last step, reason, what it tried). Don't return silence. Let the human or downstream system decide whether to retry, complete manually, or escalate.

## Evidence

- **Engineering blog:** Rastogi (Modelia.ai / Asynq.ai) describes five concrete failure modes with real production consequences: tool parameter hallucination, loop traps, contradictory reasoning chains, quality-vs-completion inversion, and cost spirals — all observed at scale with paying users. Recommends output validation gates, cost circuit breakers, and escalation checkpoints. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Engineering blog:** Rajpoot (May 2026) provides a concrete working playbook with code for hard step caps, tool error semantics (transient vs. permanent), fallback paths, whole-agent retries, and cost circuit breakers. Finds 12 steps sufficient as a default cap for most agentic tasks. — [blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)

- **Technical guide:** Mukunda Rao Katta (DEV Community, May 2025) frames tool failures as "the normal operating condition, not edge cases" and provides a three-pattern taxonomy — Retry (for transients), Fallback chains (for persistent failures), Graceful Degradation (for partial capability). Emphasizes error classification before routing to a strategy. — [dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl](https://dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl)

- **Engineering post:** Debnath (Crusoe, August 2026) argues the demo-to-production gap is architectural, not about model intelligence, and identifies six production failure modes: inconsistent decisions, tool call timeouts, retrieval quality degradation, context window pollution, latency spikes, and multi-agent workflow deadlocks. Advocates for designing reliability in from the start rather than retrofitting it. — [hackernoon.com/why-agentic-ai-systems-fail-in-production](https://hackernoon.com/why-agentic-ai-systems-fail-in-production-and-what-reliable-architecture-actually-requires)

- **Technical guide:** AIMADetools (2026) provides concrete Python validation code for tool call argument validation and loop detection patterns (MAX_CONSECUTIVE_SAME_TOOL = 3, MAX_TOTAL_STEPS). Frames semantic error detection as a separate category from HTTP error handling. — [aimadetools.com/blog/ai-agent-error-handling](https://www.aimadetools.com/blog/ai-agent-error-handling)

## Gotchas

- **Don't retry all errors uniformly.** Applying retry to 401, 404, and validation failures wastes quota and compounds latency. Classify first.
- **Step caps alone don't ensure quality.** An agent that hits its step cap returns "done" — not "failed." Couple step caps with explicit success criteria checks and partial-result reporting.
- **Validation can't be delegated to the same model that produced the output.** A model that generates wrong code won't reliably catch that same wrong code. Use a smaller, faster verifier or structured output schemas for validation.
- **Cost circuit breakers are often forgotten until the first invoice shock.** Set them before production, not after. Per-task ceilings are more useful than per-session ceilings for multi-tenant systems.
