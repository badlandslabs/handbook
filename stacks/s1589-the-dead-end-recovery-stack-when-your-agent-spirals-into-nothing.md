# S-1589 · The Dead-End Recovery Stack — When Your Agent Spirals into Nothing

Your agent ran for 47 minutes. It made 312 API calls, edited 18 files, and returned a result. The result is wrong — not because of a bad model or a bad plan, but because the agent kept trying the same failing approach with escalating conviction, lost track of what it had already tried, and never stopped to ask whether it should stop. No error was raised. No exception was thrown. The agent completed successfully and failed silently. This is the dead-end recovery stack — how to detect when an agent has gone nowhere, distinguish stuck from slow, and get it back on track before it costs you.

## Forces

- **Silent failure is the norm, not the exception** — agents complete without raising errors while producing wrong or useless results; the absence of an exception is not evidence of success
- **Stuck and slow look identical from the outside** — activity metrics (API calls, edits, log volume) rise in both states; the clean separator is a progress metric that only increases when real work is done
- **Self-correction is a trap** — a 2024 ICLR paper (Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet") showed that the model that generated the wrong answer shares the same blind spots as the model asked to evaluate it; intrinsic self-correction compounds errors rather than fixing them
- **Recovery moves must match failure shape** — the nudge that breaks a Repeater fails on a Wanderer; the human handoff that resolves a Spiral is overkill for a bad-luck timeout; recovery ladder rungs must be proportionate to failure type
- **State loss is the hidden cost** — when an agent crashes mid-workflow, the cost is not just the failed run but the accumulated progress; without checkpointing, every failure is total loss

## The Move

### 1. Classify the failure shape before choosing a recovery move

The agentpatterns.ai loop-engineering taxonomy identifies three distinct stuck shapes, each demanding a different response:

| Shape | Symptom | First recovery move |
|-------|---------|---------------------|
| **Repeater** | Same action, same result, repeated N times | Inject a nudge: name the failed action, ask for a different approach |
| **Wanderer** | Activity continues but nothing converges | Force a replan: give the agent its current state and ask it to revise the approach before continuing |
| **Spiral** | Escalating approaches that all fail | Escalate to human handoff: this exceeds the agent's resolution capacity |

### 2. Use progress metrics, not activity metrics, to detect stuckness

Activity proxies — API call counts, file edit counts, log volume — rise during stuck loops just as they do during legitimate work. They cannot distinguish stuck from slow. The correct signal is a **progress metric that only increases when real work is done**: failing tests resolved, unique sources gathered, checklist items completed. If this metric is flat across N consecutive heartbeats while activity continues, the agent is stuck — not slow.

### 3. Layer retry strategy by failure type

Not all errors deserve the same response. A single `except Exception: retry` block is worse than no error handling because it retries everything, including failures where retrying wastes time and money.

| Failure Type | Examples | Response |
|-------------|----------|----------|
| **Transient** | Rate limits (429), server errors (503), timeouts | Retry with exponential backoff and jitter |
| **Persistent** | Provider outage, quota exhausted, invalid API key | Fallback chain or user communication |
| **Bad Input** | Content policy violations (400), context window exceeded | Modify request or reroute |
| **Partial** | Malformed JSON, wrong tool parameters | Correction prompt to a verifier model |
| **Timeout** | Request too complex | Simplify and retry once |

### 4. Implement a recovery ladder — escalate through bounded moves

After detection fires, climb a bounded ladder before escalating to human handoff:

1. **Nudge** — inject a message naming the failure pattern; ask the agent to try a different approach (effective for Repeaters)
2. **Replan** — give the agent its current state summary and ask it to revise the plan before continuing (effective for Wanderers)
3. **Reset** — checkpoint restore to last known good state; restart from there (effective for Spiral after nudge fails)
4. **Escalate** — human-in-the-loop handoff with full execution trace (last resort; correct for Spiral and unresolvable cases)

Each rung has a retry budget. If nudge fails after 2 attempts, move to replan. If replan fails after 2 attempts, move to reset. If reset fails, escalate. Never let the ladder run unbounded — each rung should have explicit attempt limits.

### 5. Checkpoint state before every major tool call

Long-running agents must serialize state to durable storage before executing consequential actions. The checkpoint should include: current plan, completed steps, accumulated results, and any side effects already committed. On failure, recovery resumes from the last checkpoint rather than from scratch.

## Evidence

- **Loop-engineering taxonomy:** The agentpatterns.ai stuck-loop-recovery pattern defines the three-shape taxonomy (Repeater/Wanderer/Spiral) and the bounded recovery ladder — [agentpatterns.ai/loop-engineering/stuck-loop-recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **YC startup monitoring real failures:** Sentrial (YC W26) documented concrete production failures from real deployments — a support agent that began misclassifying queries and routing them to the wrong team, agents that chose the wrong tools and blew cost budgets, agents that completed tasks successfully and returned wrong results without raising any error — [HN Launch: Sentrial](https://news.ycombinator.com/item?id=47337659)
- **Self-correction failure mode:** The ICLR 2024 paper "Large Language Models Cannot Self-Correct Reasoning Yet" (Huang et al.) established that intrinsic self-correction does not reliably improve LLM reasoning — the model and its critic share the same systematic gaps — [(Huang et al., 2024)](https://arxiv.org/abs/2312.03798)

## Gotchas

- **Using the same model for self-correction** — if the failure was due to a gap in the model's knowledge or a structural blind spot, the same model asked to evaluate its own output will not catch it; use a separate verifier model or structured output validation instead
- **Activity masquerading as progress** — API call counts and log volume increase in both stuck and converging states; if you only track activity, you will miss stuck agents until they burn budget or time
- **No checkpoint = total loss on crash** — long-running agents without state serialization lose all accumulated progress on crash; the first time you lose an hour of agent work is the last time you skip checkpointing
- **Retrying everything uniformly** — a blanket retry on all exceptions will hammer rate-limited APIs, amplify cascading failures, and waste tokens on persistent errors; classify errors and match retry strategy to failure type
- **Human handoff without context** — escalating to a human with only "the agent failed" gives the human nothing to work with; the escalation payload should include the full execution trace, last checkpoint, and the specific failure shape that triggered escalation
