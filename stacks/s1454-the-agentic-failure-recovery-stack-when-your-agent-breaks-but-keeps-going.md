# S-1454 · The Agentic Failure Recovery Stack — When Your Agent Breaks But Keeps Going

Your agent has been running for 47 minutes on a CRM cleanup task. It has called the email API 38 times, created 12 tasks in Asana, and sent three contradictory status updates to your customer. It is also completely hallucinating. Nobody noticed because the agent kept executing — and the task "completed." This is the agentic failure recovery gap: agents that fail non-deterministically, compound damage at machine speed, and provide no natural rollback point.

## Forces

- **Agents fail differently than code.** Code bugs are local and well-understood. Agent mistakes are distributed, irreversible, and happen before monitoring fires. A `DROP TABLE` that an agent executes successfully is not a crash — it is a completed action with permanent consequences.
- **The agent has no stop condition until you give it one.** Without explicit convergence detection, agents iterate until they hit a hard cap — which stops too early (clipping a still-improving loop) or too late (wasting budget and returning a worse answer than iteration N-3).
- **Self-correction requires knowing you are wrong.** The agent cannot validate its own outputs without an external signal. It will confidently repeat a broken strategy if the error message does not tell it exactly what to fix.
- **Cascading errors outpace human review.** In multi-agent pipelines, one agent's bad output becomes the next agent's input. By the time a human notices, the damage has propagated through dozens of downstream tool calls.
- **Checkpointing is not optional for long-running tasks.** An agent mid-migration that loses its context has no way to resume — it must start over or operate blind.

## The Move

Build failure recovery as a first-class layer in the agent scaffold, not as exception handling around it.

### 1. Validate inputs before every tool call — not outputs after

Tool parameter hallucination (fabricated IDs, wrong date formats, invalid enums) is the most common failure mode. Validate every parameter against the actual schema and referential integrity before execution, not after.

```
Before: agent decides to call delete_user(id="usr_abc123")
After:  validator.check("user_exists", id="usr_abc123") → pass/fail
       Only then: agent.execute_tool("delete_user", ...)
```

Source: Harsh Rastogi (Modelia.ai / Asynq.ai) documented this as the root cause of a candidate evaluation agent hallucinating tool parameters, getting stuck in loops, and costing 3x its allocated budget. — https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns

### 2. Replace max_iterations with convergence detection

Fixed iteration caps are a blunt instrument. `LoopGain` (Apache-2.0, HN Show HN, fitz2882) calculates **loop gain (Aβ)** — the ratio of current error to previous error — each iteration:

- `Aβ < 1` → error is shrinking → loop is improving → let it continue
- `Aβ ≥ 1` → error held or grew → loop is stuck → stop and roll back

This replaces arbitrary caps that stop too early or return a degraded final answer. The library also tracks trajectory state (converging / oscillating / diverging) and emits signals for each.

Source: LoopGain GitHub — https://github.com/loopgain-ai/loopgain
Source: HN discussion — https://news.ycombinator.com/item?id=48919562

### 3. Checkpoint state at every boundary, design tools as idempotent

Long-running workflows (dozens of tool calls, hours of execution) need state persistence that survives context loss or infrastructure failure. LangGraph, Temporal, and Dagster ship first-class checkpoint primitives. The key practices:

- **Checkpoint at every decision point**, not just at the end
- **Design every tool as idempotent** so re-execution after a resume does not duplicate side effects
- **Store the full event history**, not just the final state — this enables replay-based debugging and LLM-as-judge replay (agent-triage uses this pattern)

Source: Zylos Research, "AI Agent Workflow Checkpointing and Resumability" (2026-03-04) — https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability

Source: AgentMarketCap, "Agent Checkpoint and Rollback Engineering 2026" (documented cases: DROP TABLE before backup confirmed, S3 prefix misidentification deleting 6 months of logs) — https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026

### 4. Build compensation logic alongside every destructive action

When rollback means reverting a deploy, that is infrastructure work. When rollback means executing compensation logic across dozens of completed tool calls — undo the email sent, restore the deleted records, revoke the API tokens issued — that is application work that must be designed upfront.

> Agents fail in five predictable modes: hallucinated actions, scope creep, cascading errors, context loss, and tool misuse. Each has a distinct mechanism, a distinct signature, and a distinct mitigation. — NimbleBrain AI failure taxonomy — https://nimblebrain.ai/why-ai-fails/agent-governance/agent-failure-modes

The compensation stack is not a rollback in the traditional sense — it is a set of compensating actions that restore the system to its pre-task state, designed in advance and triggered by a failure signal.

### 5. Self-correction is a retry with a specific error message

The model is not broken. The orchestration is unspecified. A validator that says "this is wrong" is useless. A validator that says "the `date` parameter must be ISO 8601 format, got 'next Tuesday', here is the schema" gives the agent enough to self-correct in one retry, not three.

```
Self-correction quality = specificity of error signal × retry budget
```

Phantom agent (OpenAI Agents SDK, BitGN PAC1 Challenge, ~86% score on 43 tasks) demonstrates this pattern: the classifier uses LLM-first classification with regex fallback and override logic, and the agent can call `list_skills` / `get_skill_instructions` mid-run to switch to a different workflow when the current one is failing.

Source: Phantom agent GitHub — https://github.com/vakovalskii/phantom-agent
Source: BestAIWeb, "Retry, Fallback & Self-Correction in AI Agents (2026)" — https://www.bestaiweb.ai/how-to-implement-retry-fallback-and-self-correction-loops-in-ai-agents-in-2026

## Evidence

- **HN Show HN:** LoopGain – control theory for agent loops, replaces max_iterations with convergence detection (Aβ < 1 = improving) — https://news.ycombinator.com/item?id=48919562
- **GitHub (MIT):** Apigee Agent Loop Detector – Apigee X + Gemini 2.5 Flash semantic loop detection for LangChain, CrewAI, Google ADK, Vertex AI Agents — https://github.com/saiflayouni/apigee-agent-loop-detector
- **GitHub (MIT):** agent-triage – CLI that analyzes production traces: extracts behavioral rules from system prompts, replays conversations with LLM-as-judge, flags the exact step and agent where cascade started — https://github.com/converra/agent-triage
- **GitHub (Apache-2.0):** Agentic Reliability Framework (ARF) – graph-native reliability platform with dual-architecture separating decision intelligence (OSS) from governed execution (Enterprise); addresses the 73% AI agent project failure rate through memory-and-reasoning graphs, self-healing incident loops, and deterministic safety guarantees — https://github.com/petterjuan/agentic-reliability-framework
- **Company engineering:** Harsh Rastogi (Modelia.ai / Asynq.ai) – "Building your first AI agent is exciting. Then you deploy to production and everything breaks." Documents five failure modes with real cases: tool parameter hallucination, self-correction loops, stateful rollback gaps, stuck-in-loop detection, graceful degradation — https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns
- **Research post:** Zylos Research on checkpointing as standard production practice: LangGraph, Temporal, Dagster all ship first-class checkpoint primitives; idempotent tool design enables re-execution without side-effect duplication — https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability
- **Industry analysis:** AgentMarketCap documents real rollback failure cases (DROP TABLE before backup, S3 prefix misidentification) as evidence that irreversibility is the defining infrastructure challenge of 2025-2026 — https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026

## Gotchas

- **A validator that only says "failed" is not a validator.** It must output a structured error with field-level specificity, schema reference, and the observed value. Self-correction quality is a direct function of error signal specificity.
- **Idempotency is not the default for most API calls.** Sending the same "refund order" request twice with a naive retry loop will refund the customer twice. Idempotency keys or GET-then-act patterns are required infrastructure, not an afterthought.
- **Cascading errors compound faster than your monitoring fires.** In a 5-agent pipeline, agent 3's hallucinated output becomes agent 4's input, which agent 5 trusts. By the time a human notices, three agents have acted on bad data. You need cross-agent output validation, not just per-agent retry.
- **"The task completed" and "the task succeeded" are not the same thing.** Agents report task completion as a signal. You need an independent validator that checks actual outcome state, not just the agent's self-reported completion status.
- **Hard iteration caps are not loop detection.** Setting `max_iterations=10` stops the loop but returns the last iteration's output — which may be worse than iteration 3. Convergence detection stops at the best answer seen and rolls back to it.
