# S-2080 · The Bounded Agent — Step Caps, Error Taxonomy, and Fallback Chains

Agents that work in demos fail in production not because they can't reason — but because they don't know when to stop trying. The compounding reliability problem is mathematical: a 95% per-step success rate means an 81% success rate across four steps. Teams that ship agents without explicit failure boundaries end up with runaway loops, silent wrong answers, and budget spirals. The solution is a layered safety architecture built on step caps, error classification, and fallback chains.

## Forces

- **The compounding reliability problem** — every tool call, API hop, and LLM invocation is an independent failure point. "95% sounds impressive until you run it through a real workflow and watch it compound to useless in days." The math is unforgiving: 0.95^4 = 81%. More complex agents hit more steps.
- **Agents don't know when to stop** — unlike traditional software, agents retry the same action with more conviction when it fails. A Reddit thread from late 2025 documented an agent retrying the exact same action with increasing confidence and identical failure. Infinite retry loops happen when agents misinterpret error messages or conflate success with failure states.
- **Safety mechanisms create dead ends** — naive step caps and error handlers can create states with no outbound transitions. The pipeline freezes not because the agent failed, but because the error handler did. LLM-generated patches tend to be locally correct but globally broken — they fix the immediate problem while creating terminal non-final states that violate state graph closure.
- **Confident failure is worse than obvious failure** — an agent that crashes is visible. An agent that hallucinates success and keeps going will destroy more data, waste more budget, and be harder to debug. "The most dangerous AI agent behavior isn't failure. It's confident failure."

## The move

**Build a layered failure architecture — not a single guardrail, but three layers that each handle a different failure class.**

### Layer 1: Hard step caps as the outermost gate

```python
MAX_STEPS = 12  # or recursion_limit=12 in LangGraph
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

The step cap is the single most important guardrail. It is not a throttle — it is a commitment to document and escalate when the agent cannot complete in a bounded number of attempts. If an agent doesn't finish in 12 steps, it should stop, log the full state, and escalate.

### Layer 2: Four-type error taxonomy — classify before you react

| Error Type | Cause | Recovery |
|---|---|---|
| **Transient** | Rate limits (429), timeouts, 503, DNS | Retry after delay with backoff |
| **Semantic** | Malformed JSON, invalid tool args, schema violations | Re-prompt with corrective context |
| **Resource** | Token budget exceeded, context overflow, spending cap | Reduce payload (summarize, drop results, switch model) |
| **Fatal** | Auth failures, revoked API keys, policy violations | **Abort immediately**, log, alert |

The critical distinction: transient and semantic errors are recoverable. Fatal errors are not. Mixing them up — retrying on an auth failure — wastes budget and can mask the real problem.

### Layer 3: Fallback chains, not fallback singletons

A fallback is not a retry. A real fallback chain answers: "When the agent cannot safely complete the task, what should happen next?" Options in order of aggressiveness:

1. **Retry later** — transient errors, rate limits, brief outages
2. **Use a simpler model or narrower path** — resource exhaustion on a complex task
3. **Skip the optional step and continue** — non-critical sub-tasks
4. **Return a safe default output** — degraded but functional
5. **Create a review task for a human** — ambiguous or high-stakes cases
6. **Pause and escalate** — when the agent hits policy boundaries
7. **Fail closed and do nothing** — risky destructive actions

### Layer 4: Structural guards

- **Circuit breakers** — if a dependency fails repeatedly, stop calling it. Monitor circuit breaker state transitions; rapid OPEN→HALF_OPEN→CLOSED cycles indicate an unstable dependency.
- **Cost circuit breakers** — if fallback usage exceeds ~20% of requests, the primary strategy has a systemic issue. If costs are spiraling, stop immediately.
- **Two-layer timeout architecture** — an inner safety timeout (e.g., 2s via `SafetyClient`) and an outer guard timeout (e.g., 3s at scheduler level) catch runaway calls at different levels.
- **State checkpointing** — before any multi-step operation, persist state so a failure can resume from the last checkpoint rather than from scratch.

### Layer 5: Semantic error recovery (the hardest part)

TOOLMAZE, a benchmark from researchers at Shanghai AI Laboratory and Baidu (June 2026), revealed that current LLM agents degrade significantly more under **implicit semantic errors** — structurally valid but wrong outputs (e.g., negative stock counts, garbled data) — than under explicit failures like 404 or 429. Agents' fault-tolerance scales slower than basic task completion as model size increases. The winning strategy is not better retries but **alternative tool routing**: when one tool fails, switch to a functionally equivalent one rather than retrying the same call.

## Evidence

- **Benchmark: TOOLMAZE** — DAG-based evaluation framework from Baidu/Shanghai AI Lab testing LLM agents on C1–C4 tool-use tasks under P0–P4 perturbation modes. Finds fault-tolerance scales slower than task completion; implicit semantic errors cause more degradation than explicit API errors; dynamic replanning is 66× slower than basic task execution. — [TOOLMAZE GitHub / arXiv:2606.05806](https://arxiv.org/abs/2606.05806)
- **Industry data: 88% failure rate** — Analysis of enterprise AI agent deployments across 2024–2025 found fewer than 1 in 8 agent initiatives reach production operation. The 7 identifiable failure patterns account for 94% of all project stalls. Average cost of failed project: $340K direct. Teams that invest ~$50K upfront in failure architecture see significantly better outcomes. — [Digital Applied: Why 88% of AI Agents Fail Production](https://www.digitalapplied.com/blog/88-percent-ai-agents-never-reach-production-failure-framework)
- **Engineering guide: LLM Agent Error Recovery in 2026** — Practitioner playbook covering hard step caps (MAX_STEPS=12), tool-level retries, fallback paths, whole-agent retries, cost circuit breakers, and state checkpointing. Emphasizes that agents fail in shapes single-LLM calls don't: loops, runaway tool calls, infinite "let me try one more thing." — [Manvendra Rajpoot: LLM Agent Error Recovery in 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **Production guide: Retry budget math** — Retry policy is budget policy. Teams that tune retries first and deadlines later get it backwards. The 50-attempt cap with 1s–30s exponential backoff can stretch worst-case failure to ~25 minutes. Fail-closed safety mode protects risky actions but increases queue pressure during outages. — [Cordum: AI Agent Timeouts, Retries, and Backoff](https://cordum.io/blog/ai-agent-timeouts-retries-backoff)

## Gotchas

- **Setting step caps too low** — a MAX_STEPS of 3 will abort legitimate multi-step workflows. 10–15 is a reasonable starting range; tune based on observed step distributions in your traces.
- **Retrying on fatal errors** — retrying an auth failure or policy violation is wasteful and can mask the real problem. Classify errors before choosing recovery strategy. Fatal errors mean abort.
- **Safety mechanisms creating dead-end states** — when adding guards (step caps, circuit breakers, error handlers), verify the new state has outbound transitions. A pipeline that halts on error is often better than one that loops forever, but a pipeline that silently produces wrong output is the worst outcome.
- **Confident failure going undetected** — agents that hallucinate success don't trigger error handlers. Monitor for output plausibility (negative quantities, future dates on past queries, response latency anomalies) in addition to error rates.
- **Fallback usage rate ignored** — if >20% of requests are hitting fallback strategies, the primary strategy has a systemic issue. Don't just absorb the fallbacks; investigate.
