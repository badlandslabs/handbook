# S-1242 · The Grounded Self-Correction Stack: When Intrinsic Self-Critique Lets Your Agent Retry Its Way to Success

Your agent fails at step 7 of a 20-step pipeline. The tool returned bad JSON. The model calls the same tool again with the same malformed parameters. Then again. Then a third time. This is not a bug in your agent — it is a structural gap between how agents fail and how you designed them to recover.

## Forces

- **LLM self-correction is real but fragile.** Reflexion (NeurIPS 2023) showed verbal self-critique achieves 91% pass@1 on HumanEval — but subsequent research confirmed LLMs cannot reliably catch reasoning errors without external grounding signals. Intrinsic correction (model judging itself) outperforms nothing but degrades unpredictably.
- **Errors cascade.** A single failure in a multi-step agent propagates through planning, memory, and action modules. Error propagation — not individual component failures — is the central bottleneck to robust agents. Modern layered defenses achieve 24%+ improvement in task success rates.
- **Not all errors are equal.** The same recovery mechanism applied to every failure class is wasteful and sometimes counterproductive. Retrying a user-fixable error wastes 3 attempts before failing anyway. Interrupting for a transient rate-limit pages a human to click "retry" on something that would have self-resolved.
- **Loops are expensive.** An agent stuck in an infinite loop can burn $10–50 in tokens before a human notices. A 15-minute loop at standard rates hits $15–30. Unlike a crashed agent that stops billing, a looping agent generates continuously.

## The Move

The field has converged on a four-class error taxonomy with distinct recovery strategies, combined with grounded self-correction loops that anchor retries in execution signals rather than pure self-trust.

### Step 1 — Classify errors before acting

Route every failure into one of four buckets, each with a predetermined owner:

| Error Class | Who Fixes It | Recovery |
|---|---|---|
| **Transient** | System (automatic) | Retry with exponential backoff + jitter |
| **Semantic** | The LLM | Inject error context + re-prompt with correction |
| **Resource** | The system or user | Context compaction, re-prioritization, or escalation |
| **Unexpected** | The developer | Let it bubble up, log, alert |

*Source: Focused.io / CallSphere / Zylos Research, 2026*

### Step 2 — Retry with exponential backoff + jitter (never raw retry)

```python
RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay": 1.0,      # seconds
    "max_delay": 60.0,
    "exponential_base": 2,
    "jitter": True             # CRITICAL: prevents thundering herd
}
# Formula: delay = min(max_delay, initial_delay * (2 ** attempt)) + random(0, delay/2)
```

Jitter is not optional. Without it, all clients retry simultaneously on recovery, creating a coordinated second wave of failures.

*Source: Zylos Research, 2026-01-12*

### Step 3 — Ground self-correction in execution signals

The critical distinction: **intrinsic** self-correction (model judges itself) vs **grounded** self-correction (model judges against external signals).

| Type | Signal | Reliability |
|---|---|---|
| Intrinsic | LLM judges own output | Fragile — model cannot reliably catch reasoning errors |
| Grounded | Anchored in execution results, structured critics, or PRMs | Reliable — external evidence constrains the judgment |

Practical grounded approach: append the raw execution result (not your interpretation) to the next prompt. "The tool returned: `{raw_output}`. This failed to parse because: `{parse_error}`. Revise your parameters." The model revises against evidence, not against its own confidence.

*Source: Zylos Research, 2026-05-12 / AgentsRoom, 2026*

### Step 4 — Break stuck-in-loop failure modes

Agents loop for three root causes. Each has a specific fix:

1. **Retry without backoff** → Implement exponential backoff (see Step 2)
2. **Undetected task completion** → Define explicit success conditions; inject a termination check after each milestone
3. **Dependency deadlock** → Implement checkpointing; serialize state after each major milestone to durable storage

For LangGraph agents, checkpointing is native via `MemorySaver` or `PostgresSaver`. For custom agents, a checkpoint is a serialized JSON blob in Redis or a database keyed by task ID.

*Source: SynapseAI Guide, SynapseAI / LangGraph docs, 2026*

### Step 5 — Deploy circuit breakers for cascading failures

Apply distributed systems patterns adapted for LLM-backed systems:

- **Bulkhead isolation**: partition tools and model calls so one failing component (e.g., a rate-limited search API) doesn't block unrelated agent paths
- **Circuit breaker**: after N consecutive failures against a dependency, open the circuit and route to fallback immediately — stop wasting time on a degraded service
- **Fallback chain**: for every critical capability, define a ranked fallback stack (primary → secondary → tertiary → graceful error)

Example fallback stack from a production autonomous agent:

| Function | Primary | Fallback 1 | Fallback 2 | Final |
|---|---|---|---|---|
| Search | Primary API | Backup provider | Web fetch | Graceful error |
| Memory | Vector search | Keyword fallback | — | Return empty |
| Notifications | Push | Queue for retry | Email | Silent drop |

*Source: kangclaw.github.io, 2026-02 / Zylos Research, 2026-05*

### Step 6 — Deliver value progressively

For long-running tasks, stream partial results to the client as milestones complete. If the agent times out at 80%, the user has 80% of the value rather than nothing. Implement checkpointing per milestone so recovery resumes from the last completed step, not from scratch.

*Source: Zylos Research, 2026-05*

## Evidence

- **AI Codex / Engineering Blog:** Production Claude applications fail predictably — API downtime, rate limits, unexpected output formats, context overflow. Each failure class demands a different handling path. Emphasizes output format errors as the most common semantic failure mode. — [aicodex.to/articles/claude-production-error-handling](https://www.aicodex.to/articles/claude-production-error-handling)
- **Show HN — agent-triage:** Tool for diagnosing agent failures in production by extracting policies from system prompts, evaluating conversation traces, and generating diagnostic reports with root-cause analysis. Designed for single-agent and multi-agent systems. Runs locally. — [github.com/converra/agent-triage](https://github.com/converra/agent-triage) / [HN discussion](https://news.ycombinator.com/item?id=47334775)
- **Show HN — Agent Postmortem Skill:** Forces AI coding agents to prove their work before completing tasks — structured verification before handoff to reduce silent failures. — [HN discussion](https://news.ycombinator.com/item?id=48085516)
- **OpenHelm Blog:** Documented error handling patterns that increased agent reliability from 87% → 99.2% (14× fewer failures) using retries, circuit breakers, fallback mechanisms, timeout management, and graceful degradation. — [openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **Zylos Research (Jan 2026):** Error propagation cascades through planning, memory, and action. Layered defense strategy (retry → fallback → circuit breaker) achieves 24%+ improvement in task success rates. — [zylos.ai/zh/research/2026-01-12-ai-agent-error-handling-recovery](https://zylos.ai/zh/research/2026-01-12-ai-agent-error-handling-recovery)
- **Zylos Research (May 2026):** 7-layer resilience model for LLM-backed systems. Key insight: LLM failures are probabilistic, not deterministic — HTTP 200 with hallucinated JSON is a valid failure mode that traditional try-catch misses entirely. — [zylos.ai/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems](https://zylos.ai/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems/)
- **Focused.io / LangGraph Production:** Error classification matrix is the first design decision. Wrong classification costs real time — retrying user-fixable errors, interrupting for transients. — [focused.io/lab/langgraph-agent-error-handling-production](https://focused.io/lab/langgraph-agent-error-handling-production)
- **AgentsRoom Blog:** Self-correcting coding loops transform the prompt-ping-pong pattern into autonomous cycles. Key pattern: agent writes its own checklist, reviews own work against the plan, self-corrects until done — user steps in only at review. — [agentsroom.dev/blog/ai-agent-loops-self-correcting-coding](https://agentsroom.dev/blog/ai-agent-loops-self-correcting-coding)
- **AI System Design Guide (ombharatiya):** Hallucinated tools (calling non-existent functions), semantic failures (malformed tool calls), and infinite loops are the three dominant agent failure categories. Stateful rollback via LangGraph checkpointing addresses the loop category structurally. — [github.com/ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Raw retry on semantic errors amplifies cost.** If a tool call fails because the model generated bad parameters, retrying without injecting the parse error will generate the same bad parameters. Always append the error signal before retrying.
- **HTTP 200 is not success.** The most insidious failure mode: LLM APIs return HTTP 200 with hallucinated JSON, malformed tool calls, or confident nonsense. You need semantic validation (does the output conform to the expected schema?) not just transport-level checks.
- **Self-correction loops need hard bounds.** Without a max-iteration cap, a grounded self-correction loop can still spin indefinitely if the grounding signal keeps pointing the wrong direction. Set `max_self_corrections = 3` and escalate on exhaustion.
- **Checkpoint granularity matters.** Checkpointing every token is expensive. Checkpointing only at task boundaries means a 20-step task restarts from scratch on failure at step 19. Checkpoint after each major milestone — tool call completed, sub-task finished, document section written.
- **Circuit breaker state must be durable.** If your circuit breaker lives in memory, a restart resets it. The breaker opens, the service recovers, but your agent doesn't know — it keeps routing to fallback for another hour.
