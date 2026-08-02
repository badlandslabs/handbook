# S-2001 · The Agent Recovery Stack — When Your Agent Loops Forever and Nobody Notices

Your agent runs. It calls tools. It loops. It burns $400 in API calls over a weekend before anyone checks the logs. The failure wasn't a crash — it was silence, and your monitoring measured "runs completed" not "runs that actually worked." Recovery is the part of agent engineering that nobody demos and everyone needs.

## Forces

- **Failure is probabilistic, not deterministic:** Traditional software throws exceptions; agents return a bad response and keep going. The system doesn't know it failed unless you teach it to check.
- **Compounding failure over steps:** UC Berkeley's MAST study found multi-agent failure rates of 41–86.7% across seven frameworks. A single 20-step agent with 95% per-step reliability completes end-to-end only 36% of the time.
- **The loop paradox:** The agent loops because it thinks it's making progress. No exception is raised. Monitoring sees a running process. Only the invoice reveals the damage — one production trace burned 27 million tokens over 4.6 hours undetected.
- **Idempotency vs. autonomy tension:** Retry logic is safe only if actions are idempotent. But agents that take real-world actions (sending emails, charging cards) cannot safely retry without a safety layer.
- **Escalation vs. autonomy tradeoff:** The more autonomous your agent, the more dangerous a failure state. Every additional capability is an additional blast radius.

## The Move

Build a layered failure architecture: stop loops early, checkpoint state for recovery, and degrade gracefully when you can't complete.

### 1. Hard step caps + loop detection (shut it down before it burns out)

The single most important guardrail. Stop execution after a fixed number of steps regardless of whether the agent thinks it's making progress.

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

LangGraph exposes this as `recursion_limit`. LangChain uses `max_iterations`. Set it low — 12–20 steps covers most real tasks; anything beyond that is almost always a loop.

Loop detection goes further: hash the last N tool-call signatures and detect repetition. If the same tool with the same arguments fires 3 times in a row, force a strategy change or stop.

```python
# agentguard library pattern
from agentguard import LoopDetector
detector = LoopDetector(max_repeats=3, window=5)
# Raises LoopDetectedError after 3 repeated actions in a 5-step window
```

### 2. Checkpoint + resume (don't restart from scratch)

Long-running agents must snapshot state at natural transaction boundaries — after a step completes, before a tool call fires. On failure, resume from the last checkpoint rather than replaying everything.

Take checkpoints only at clean boundaries: after step completion, after all side effects are recorded, after in-memory state is synchronized. Never checkpoint mid-tool-call — partial state is worse than no state.

```
Checkpoint strategy:
  - Milestone: full conversation at decision points (task start, major step, error recovery)
  - Intermediate: discard intermediate messages, keep only milestone + replay marker
  - On failure: load most recent milestone, replay only post-milestone messages
```

Recovery from a document analysis agent hitting a Cloud Run timeout at minute 58 of a 60-minute job: checkpointing meant it resumed from minute 58 instead of starting over.

### 3. Tiered fallback chain (degrade, don't die)

When the primary model or tool fails, fall through to the next tier — not to an error. A five-tier degradation pyramid:

| Tier | Capability | Trigger |
|------|-----------|---------|
| 0 | Full (frontier model) | Normal operation |
| 1 | High (cheaper frontier) | Primary rate limit |
| 2 | Mid (specialized model) | Primary unavailable |
| 3 | Minimal (simple heuristics) | All models down |
| 4 | Human escalation | Task cannot be automated |

The 70% solution via a degraded model beats 0% from erroring out — for non-safety-critical tasks. Medical, financial, and legal tasks should NOT degrade; a clear "unavailable" is better than a wrong answer.

Circuit breakers complement this: per-provider circuit breakers (Closed/Open/Half-Open states) fail fast on unhealthy providers and probe for recovery, transparently routing around outages.

### 4. Idempotent actions + safe retry (retry without side effects)

Every tool call that has side effects must be idempotent before you can safely retry it. Idempotency keys on API calls prevent double-charges, double-sends, and duplicate database writes.

```python
# Idempotency key pattern
def send_email(to, subject, body, idempotency_key=None):
    if idempotency_key and redis.exists(f"idempotency:{idempotency_key}"):
        return redis.get(f"idempotency:{idempotency_key}")
    result = email_provider.send(to, subject, body)
    if idempotency_key:
        redis.setex(f"idempotency:{idempotency_key}", 86400, result)
    return result
```

The key insight: retry logic and idempotency are co-designed. You can't add one without the other for side-effect-producing tools.

### 5. Dead letter queue + human escalation (escape hatch for the unrecoverable)

When an agent exhausts retries, step caps, and fallbacks, route the task to a dead letter queue for human review rather than dropping it silently. This is the difference between "failed gracefully" and "failed invisibly."

Track: task state at failure, last tool call, error type, number of retries, cost consumed. The reviewer needs enough context to resume or manually complete.

Cost circuit breakers add a spend cap — stop the agent and escalate if cumulative cost exceeds a threshold. A looping agent that burns $400 in tokens should hit your budget limit before it burns $4,000.

## Evidence

- **Research paper (UC Berkeley, NeurIPS 2025):** MAST taxonomy of 14 failure modes across 1,600 annotated traces in 7 multi-agent frameworks. Failure rates of 41–86.7%. Single undetected loop burned 27 million tokens over 4.6 hours. — [arXiv:2503.13657](https://arxiv.org/abs/2503.13657), [MAST project page](https://sky.cs.berkeley.edu/project/mast/)
- **Engineering blog (Octopoda, April 2026):** Analysis of 1,600 production traces. Found structured validation improved accuracy from 10% to 70% (7x). Most failures went undetected by the systems running them. — [AI Agent Failure Modes: What 1,600 Traces Reveal](https://octopodas.com/blog/ai-agent-failure-modes)
- **Production library (agentguard):** Open-source Python library adding circuit breakers, LLM-aware retry, idempotency keys, and loop detection to LangChain, AutoGen, CrewAI, and custom pipelines. Published to PyPI May 2026. — [GitHub: maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm), [PyPI: agentguard-llm](https://pypi.org/project/agentguard-llm/)
- **Engineering guide (Manvendra Rajpoot, May 2026):** Hard step caps as first line of defense; tool-level vs. whole-agent retry distinction; cost circuit breakers; escalation paths. — [LLM Agent Error Recovery in 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **Industry analysis (The Operator Collective, May 2026):** 86% of agent failures are recoverable with proper error handling. Key insight: every failure is predictable and therefore handleable. — [AI Agent Error Handling: When Your Bot Breaks Production](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Research (AgentixForce, May 2026):** Five-tier degradation pyramid with model fallback chains. Circuit breakers for LLM providers. Human-in-the-loop escalation patterns. — [Graceful Degradation Strategies for Production AI Agents](https://agentixforce.ai/blog/graceful-degradation-strategies-agents)

## Gotchas

- **Hard step caps are not sufficient alone:** A cap of 50 still burns tokens before stopping. Set caps to what the task actually needs — 12–20 steps covers most real workflows. If you need more, the task decomposition is wrong.
- **Naive retry-on-exception is not LLM-aware:** Tenacity-style retries treat all exceptions the same. LLM failures include rate-limit 429s, malformed JSON tool calls, hallucinated function signatures, and timeout-after-90s — each needs different handling. Use LLM-aware retry that distinguishes error types.
- **Checkpointing partial state creates subtle bugs:** Never checkpoint mid-tool-call. The agent resumes into an inconsistent state where the tool fired but the result wasn't recorded. Use copy-on-write semantics for concurrent multi-agent checkpointing.
- **Graceful degradation is not universally appropriate:** Medical, legal, financial, and safety-critical decisions should fail fast rather than degrade. A wrong answer from a degraded model may be worse than no answer.
- **Monitoring "runs completed" is not monitoring for failure:** The 27M-token loop ran for 4.6 hours and logged as a running process. Measure: steps completed, tokens consumed, cost per run, task outcome. A green dashboard means nothing without outcome instrumentation.
