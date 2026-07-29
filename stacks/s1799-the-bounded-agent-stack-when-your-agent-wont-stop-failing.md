# S-1799 · The Bounded Agent Stack — When Your Agent Won't Stop Failing

Your agent has no off switch. It got a 429 error, so it retried. Got another 429, so it retried again. It's now 90 minutes into a loop that has burned $400, produced nothing, and nobody noticed because nothing logged an error. Agents are built to keep going — that's the feature. In production, it's the thing that kills you.

You need to build bounded failure into every agent from day one.

## Forces

- **Frameworks optimize for completion, not stopping.** LangGraph, CrewAI, AutoGen, and the rest all default to "try harder" when something fails. Retries are the path of least resistance; hard stop conditions require deliberate design.
- **Not all errors are equal, but most retry logic treats them identically.** A rate limit (transient) and a malformed tool call (semantic) need completely different responses. Retrying a semantic error just wastes tokens and buries the signal.
- **The most expensive failure mode looks like success.** A runaway agent doesn't crash — it quietly burns budget and context until both are exhausted. Runaway Execution accounts for 5.1% of classified failures but carries the highest direct financial damage, with documented cases exceeding $47K per incident.
- **Rollback is a foreign concept to most agent code.** Agents produce side effects — database writes, API calls, file mutations — with no transaction boundary. By the time you detect the mistake, the damage is already done.

## The Move

Build a layered defense system. Each layer catches a different failure mode, and the layers compose into an agent that knows when to stop, how to recover, and when to escalate.

### Layer 1 — Hard Step Caps

The single most important guardrail. If the agent doesn't finish in N steps, it stops and escalates — no exceptions.

```
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

In LangGraph: `recursion_limit=12`. The cap must be tuned per workflow — coding agents need more steps than simple Q&A, but 50+ steps without a deliverable is almost always a loop.

### Layer 2 — Per-Tool Circuit Breakers

Track failures per external tool independently. Three consecutive failures within 60 seconds → open the circuit. Block all calls to that tool for 5 minutes (+ jitter). Then probe once in half-open state.

```
CLOSED (normal) → 3 consecutive failures → OPEN (blocked)
OPEN → 5 min timeout → HALF-OPEN (probe)
HALF-OPEN → success → CLOSED
HALF-OPEN → failure → OPEN (extended)
```

This is the circuit breaker from distributed systems, adapted to the tool-call level. It prevents the retry storm: when Agent A hits a degraded API, Agent B and C don't all fail over simultaneously and amplify the problem. It also means you stop burning tokens on a broken endpoint — you either try the fallback or degrade gracefully.

### Layer 3 — Error Taxonomy and Typed Recovery

Classify every failure before deciding the response. Four categories, each with a different strategy:

| Error Type | Examples | Recovery |
|---|---|---|
| **Transient** | 429 rate limit, 503, DNS timeout | Exponential backoff + retry, max 3 attempts |
| **Semantic** | Malformed JSON, schema violation, wrong tool call | Re-prompt with explicit correction in next turn's system prompt |
| **Capability** | Requested tool unavailable, model context exceeded | Escalate to parent agent or supervisor |
| **Fatal** | Auth revoked, resource deleted | Stop immediately, log, alert, do not retry |

The key insight: most frameworks default to "retry everything." Semantic errors must never be blindly retried — they need the agent to receive corrective feedback and try a different approach, not the same one again.

### Layer 4 — Checkpoints and Rollback

For any agent making irreversible mutations (DB writes, file deletions, external API calls), checkpoint state before each mutation. Store: task ID, timestamp, pre-mutation state snapshot, and the tool call that will be made.

If the agent exceeds step cap, hits a fatal error, or produces a semantically wrong result that passes validation but corrupts data, restore from the last checkpoint and either retry with a corrected prompt or escalate to a human.

For filesystem operations: copy the target directory before the agent writes to it. For database writes: store the pre-mutation row state. The checkpoint itself is the rollback mechanism — the agent can't undo, it can only restore.

### Layer 5 — Escalation Triggers

Define explicit conditions for human escalation. These are not edge cases — they are the operational contract:

- Step cap exceeded
- Cost ceiling hit → `budget-paused` state, notify orchestrator, await top-up
- Agent confidence below threshold on high-risk action (financial, security, legal)
- Tool circuit breaker open with no fallback available
- Repeated semantic errors on the same tool call (3x = escalate, not retry)

> Escalation is a deliberate design primitive, not a fallback. In production-grade systems, the HITL trigger conditions are defined at design time, not discovered during incidents.

## Evidence

- **Post-mortem / Incident report:** Alex Wu (CEO, Anythoughts.ai) documented a $400 runaway in 90 minutes — an outreach agent hitting a 429 endpoint with no stop condition, retrying indefinitely. Root cause: no step cap, no circuit breaker, no escalation path. After adding step caps and per-endpoint circuit breakers, the same scenario now stops within 12 steps and alerts. — [DEV Community: The Infinite Loop Problem](https://dev.to/alex_wu_anythoughts_ai/the-infinite-loop-problem-how-we-stopped-our-agent-from-running-forever-3ckb)

- **Production incident database:** RunCycles analyzed 20+ documented agent incidents (2025–2026) and found that 41–87% of multi-agent coordination failures stem from cascading retry storms where no agent had a circuit breaker — when one agent degraded, all retrying agents amplified the load. Their cost modeling shows runaway loops consuming $32–$2,300 per incident under typical token assumptions, with the highest-damage single incidents exceeding $47K. — [RunCycles: The State of AI Agent Incidents (2026)](https://runcycles.io/blog/state-of-ai-agent-incidents-2026)

- **Practitioner survey:** The Clyro blog analyzed 591 documented AI agent failures (2023–2026) and found that 88% of classifiable failures trace to infrastructure gaps — missing loop detection, missing circuit breakers, missing escalation paths — not model quality. Runaway Execution (5.1% of failures) has the highest direct financial damage. Silent Degradation (24.9%) is the most dangerous for business impact because quality drops with no error signal. — [Clyro: The 5 AI Agent Failure Modes](https://clyro.dev/blog/the-5-ai-agent-failure-modes-why-they-fail-in-production)

- **Framework-level circuit breaker pattern:** The AgentPatterns.ai community has codified the per-tool circuit breaker as an established pattern (last reviewed 2026-06-12), noting it "prevents token waste on retry loops" and that "backoff delays the waste rather than prevents it." The pattern wraps every external tool (API, search engine, code executor) in its own failure-tracking state machine, independent of the agent's main control flow. — [AgentPatterns.ai: Agent Circuit Breaker](https://www.agentpatterns.ai/patterns/agent-design/agent-circuit-breaker/)

## Gotchas

- **Backoff without a circuit breaker is a delay, not a solution.** Exponential backoff with jitter between retries is necessary for transient errors, but it doesn't stop the waste if the underlying tool is degraded. You need both: backoff per call AND a circuit breaker that trips after N failures regardless.
- **Step caps catch loops but not expensive zigzags.** An agent can consume 50 steps without looping, reaching a wrong answer via a long winding path. Step caps prevent infinite loops; trajectory evaluation (S-1798) catches expensive wrong paths. The two patterns are complementary.
- **Checkpoint overhead is real but necessary for destructive workflows.** The "I'll just be careful" approach has a documented failure rate. For any agent touching production data, the checkpoint-before-mutation discipline prevents the class of incidents that require manual database restores.
- **Escalation without a runbook is not escalation.** Defining "escalate to human" is not enough — the human needs context (task ID, last checkpoint, failure type, agent's reasoning trace). Without this, escalations pile up with no resolution path.
