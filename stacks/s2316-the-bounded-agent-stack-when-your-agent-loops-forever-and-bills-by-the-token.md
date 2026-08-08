# S-2316 · The Bounded Agent Stack — When Your Agent Loops Forever and Bills by the Token

Your cron job was supposed to post one Slack message at 22:00. The network timed out on the first attempt, your retry logic fired, the retry hit rate limits, and by 22:05 you had 50 identical messages and a half-hour of token spend with nothing to show. That's the failure mode nobody talks about: agents don't crash loudly — they fail quietly, expensively, and sometimes indefinitely. This is the bounded agent stack: the engineering patterns that keep agents recoverable instead of catastrophic.

## Forces

- **Agents fail in compound shapes.** A single LLM call either succeeds or throws an exception. An agent running 300 steps accumulates state across every turn — a failure on step 287 doesn't just stop you, it wastes steps 1-286.
- **Silence is the worst failure mode.** Tool errors that return `None` look like success to the orchestrator. The agent says "done." The database has nothing. Nobody gets alerted.
- **The reliability math turns against you.** Five agents each at 95% reliability produce ~77% end-to-end success. Every inter-agent handoff is a trust boundary where failures compound.
- **Cascade failures are structural.** One tool goes down; the agent retries it in a loop; that burns tokens faster; rate limits trigger on other tools; the whole pipeline stalls silently.
- **Cost accumulates on the failure path.** Retry loops, loop detection + re-planning, and dead-end reasoning all cost tokens. An unbounded agent can burn a month's budget in minutes.

## The move

### 1. Hard step caps with escalation

The single most important guardrail. Set `MAX_STEPS` (commonly 12-20 for complex tasks) and enforce it structurally, not in the prompt:

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    checkpoint.save(state)
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS} steps")
```

When the cap fires: save checkpoint, document what was attempted, escalate — either to a simpler re-plan or a human reviewer.

### 2. Classify errors by recovery type before retrying

Not all errors should be retried. Four classes, four responses:

| Error class | Examples | Recovery |
|---|---|---|
| **Transient** | 429 rate limit, timeout, 503 | Exponential backoff + jitter + retry (≤3 attempts) |
| **Budget** | Cost ceiling hit, token limit approaching | Pause task, alert orchestrator, await top-up or context compression |
| **Capability** | Invalid tool args, context too large | Simplify task, reduce scope, escalate |
| **Silent** | Tool returned `None`, DB write failed silently | Validate outputs explicitly, don't assume success |

### 3. Circuit breakers per tool

Wrap each external tool in its own circuit breaker. Trip conditions prevent the agent from hammering a degraded endpoint:

- **Consecutive failures ≥ 5** → trip breaker for 30s, redirect to fallback
- **Error rate > 30% over 10 min** → stop agent, alert coordinator

Circuit breakers on external tools report **40-60% token savings** by preventing retry loops on dead endpoints. This pattern comes from Netflix Hystrix, adapted for agent tool calls.

### 4. Fallback chains, not single providers

A model gateway with a tiered fallback chain means graceful degradation instead of hard failure:

```
Claude Sonnet 4 (primary) → Claude Haiku 4 (cost fallback, ~80% quality, 5× cheaper) → cached partial result
```

During an outage, a customer support agent on a mid-tier fallback resolves ~70% of queries correctly. One that errors out resolves zero.

**Exception:** Do not gracefully degrade for safety-critical tasks — medical, financial, legal. A degraded wrong answer is worse than a hard failure.

### 5. Checkpointing for long-horizon agents

For any task running more than a few minutes, checkpoint state after every meaningful step:

| What to checkpoint | Frequency | Why |
|---|---|---|
| Completed task results | After every task | Losing this requires rerunning work |
| Task graph / step status | After every task | Determines what runs next |
| Tool call history | After every tool call | Audit trail + idempotency enforcement |
| Memory state | Every N tasks | Often reconstructible if needed |

An agent processing 500 research papers crashes on paper 347. Without checkpoints: start over, lose 2 hours and real money. With checkpoints: restart and resume from 347.

### 6. Idempotency everywhere

Any write operation must be idempotent. This prevents the retry-storm disaster:

> "Had a cron job that was supposed to post to Discord at 22:00. Network timeout + retry storm = 50 duplicate posts at 22:05. Now we use idempotency keys and 'already posted' guards." — production war story, GitHub Discussion #1341

`check-before-act` is the foundational pattern: read current state before writing. If the operation was already done, skip it.

### 7. Multi-agent isolation

In multi-agent systems, **shared resource deadlocks** are a primary failure mode — agents competing for database locks, rate limits, or GPU memory can gridlock the entire system. Design isolated agent sessions with independent sandboxes:

- **40% of multi-agent system failures** stem from concurrency and resource contention issues
- **Silent starvation**: documented production case — an autonomous software development system ran 452 identical task selections over 7 days, producing zero task executions, with no error signals generated
- Keep planning layers and execution layers decoupled; a metacognitive planner should not be able to starve execution indefinitely

## Evidence

- **GitHub Discussion (primary source):** Production team running 5 autonomous agents 24/7 for 95+ days shared real failure patterns — retry storms, idempotency failures, cascade failures, circuit breaker implementation details. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Engineering blog:** Agent crash on step 347 of 500-paper batch → checkpointing design. "Checkpointing is not optional for long-horizon agents — it is the difference between a viable system and a toy." — [engineersofai.com](https://engineersofai.com/docs/agentic-ai/long-horizon-planning/checkpointing-and-recovery)
- **Engineering firm (May 2026):** Five agents at 95% reliability → ~77% end-to-end. Multi-agent cascade failures, deadlocks, and cost runaway documented with containment patterns. — [conceptualise.de](https://www.conceptualise.de/en/blog/multi-agent-failure-modes)
- **GitHub pattern catalog:** Circuit breaker pattern with 40-60% token savings metric, based on Michael Nygard (*Release It!*, 2007) + Netflix Hystrix. — [github.com/nibzard/awesome-agentic-patterns](https://github.com/nibzard/awesome-agentic-patterns/blob/main/patterns/agent-circuit-breaker.md)
- **RunGuard fault tolerance guide:** LLM-specific retry taxonomy, fallback chain design (Sonnet 4 → Haiku → cached), compounding failure model for multi-turn stateful systems. — [runguard.dev](https://runguard.dev/seo/llm-agent-fault-tolerance-patterns.html)

## Gotchas

- **Don't retry non-transient errors.** Retrying a capability error (wrong tool arguments, context overflow) on exponential backoff just burns budget faster. Classify first.
- **Silent failures are invisible without output validation.** The agent's "done" message is not confirmation of successful outcome — validate what the tool was supposed to produce, not just that the tool was called.
- **Step caps without checkpointing waste work.** If you cap steps at 12 but don't save state, every retry starts from scratch. The cap is the circuit breaker; checkpointing is the recovery lane.
- **Graceful degradation is not free.** Falling back to a cheaper model works for some tasks — but a mid-tier model writing your legal contract draft will confidently produce a worse result. Know which domains accept degradation.
- **Idempotency requires schema support.** Not all APIs or tools expose idempotency keys. For tools that don't, implement check-before-act at the agent layer, not just the API layer.
