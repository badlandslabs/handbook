# S-1636 · The Interruptible Agent Stack — When Your Agent Crashes Halfway and Starts Over

Your document-processing agent ran for 58 minutes, processed 3,400 pages of regulatory filings, then timed out on Cloud Run. It restarts. It processes the same 3,400 pages again. This happens every afternoon during peak load. The agent works — it just doesn't know how to stop, remember, or resume. You are paying for the same work twice, three times, every day.

This is the interruptibility gap: agents that can run but cannot survive being interrupted. The fix is not a longer timeout. The fix is structured checkpoint-and-resume — saving state after every step, classifying tools for safe replay, and building a recovery hierarchy that escalates from retry to replan to decompose to human.

## Forces

- **Ephemeral execution is the default.** Most agent frameworks treat each run as a single process. When the process dies — rate limit, OOM, service restart — the state dies with it. A ten-step agent run without checkpointing loses everything on step seven.
- **Binary recovery wastes the most expensive resource.** Either retry the same action or replan the entire task. The first option re-samples a decision that already worked; the second option burns LLM tokens re-executing steps one through six. Neither is efficient. The right recovery level depends on failure type.
- **Not all tool calls are safe to replay.** A `send_email` tool is idempotent in schema but not in effect. A `create_file` tool with random UUID generation is non-idempotent. Retrying blindly on non-idempotent tools produces duplicate side effects — double charges, duplicate records, corrupted state.
- **Context overflow destroys recovery.** Without checkpointing, resuming means re-sending the entire conversation history. Long-horizon tasks hit context limits fast, and re-sending everything on every resume burns tokens and degrades output quality past ~60–70% context utilization.
- **Failure type drives the fix.** A transient 503 error needs a retry. A semantic failure (wrong tool selected, hallucinated argument) needs a replan. A stuck agent needs intervention. Using the wrong recovery strategy for the failure type just compounds the damage.

## The move

**Build a layered recovery hierarchy with checkpoint-resume at the core.**

### 1. Classify tools for safe replay before you use them

Tag every tool at definition time with one of three replay modes:

- **PURE** — no side effects, safe to replay indefinitely (search, read, compute)
- **SIDE_EFFECT** — has side effects, replay is safe if inputs are identical (upsert, send_webhook)
- **NON_DETERMINISTIC** — replay produces different results each time (generate UUID, fetch current timestamp, call_random_api)

The agent or orchestrator consults this tag before deciding whether to replay a failed step. Never retry a NON_DETERMINISTIC tool without first checking whether the prior call actually succeeded.

### 2. Checkpoint state at every step boundary — not on completion

After each tool call completes — success or failure — serialize the full agent state to durable storage:

- Conversation history / message history
- Tool call log (what was called, what was returned)
- Intermediate outputs and accumulated decisions
- Progress marker (current step, pending steps)

Checkpoint at the step boundary, not the end. A checkpoint that only saves on success is useless when the failure happens mid-step. LangGraph, Temporal, and Dagster all ship first-class checkpoint APIs for this pattern.

For resumability: on restart, reload the checkpoint and skip all completed steps. The completed steps' decisions reload verbatim — no re-sampling, no token burn.

### 3. Build a three-tier recovery hierarchy

Escalate through levels based on failure type — do not apply the same recovery for every failure:

| Level | Trigger | Action |
|-------|---------|--------|
| **Retry** | Transient (503, timeout, rate limit 429) | Same agent, same step, same inputs — exponential backoff with jitter |
| **Replan** | Semantic failure (wrong tool, hallucinated args, logic error) | Meta-agent rewrites the task description from the failure reason; re-execute from current step |
| **Decompose** | Step keeps failing after replan | Break the failing step into smaller subtasks; retry each independently |
| **Escalate** | All above exhausted | Human-in-the-loop: surface the failure, current state, and what was attempted |

The industry baseline is ~1–5% of LLM calls fail transiently. A ten-step agent run without this hierarchy fails on roughly 1 in 20 runs under normal load.

### 4. Detect stuck agents before they waste budget

A stuck agent — in a loop, waiting on an unresponsive tool, silently hallucinating — looks identical to a slow agent in naive monitoring. Instrument with:

- **Step timeout** — hard cap on seconds-per-step; trigger recovery if exceeded
- **Activity window** — if no tool calls within N seconds, intervene (nudge, retry, or escalate)
- **Progress monotonicity check** — if accumulated output length decreases without explanation, flag as potential loop
- **Health heartbeat** — for long-running workflows, periodic ping that surfaces current state to a monitor

### 5. Use structured state storage with version tokens

Raw JSON checkpoints on disk work for prototypes. Production systems need:

- **Content-addressable checkpoint DAG** — git-style snapshots with branching and rollback; checkpoints identified by hash, not sequence number
- **Data version token** — each checkpoint carries a version of the external data it read; on resume, validate whether those versions are still fresh (stale data handler replays or aborts)
- **Cross-region write consideration** — if the checkpoint store is remote, account for latency and partition risk; collocated writes are faster but single-region

### 6. Treat the checkpoint store as a first-class dependency

It is not optional or best-effort. The checkpoint store must be at least as available as the agent itself. Redis for low-latency transient state (short-lived, fast resume), PostgreSQL for durable queryable checkpoints. If the checkpoint store goes down, the agent pauses — it does not continue without coverage.

## Evidence

- **GitHub (isaacuselman/agentckpt):** Checkpoint-recovery middleware providing a "Checkpoint DAG — git-style content-addressable state snapshots with branching and rollback" with idempotent tool wrappers classified as PURE, SIDE_EFFECT, or NON_DETERMINISTIC. Supports branch-and-merge execution with majority vote and best-of-N across parallel branches. — [https://github.com/isaacuselman/agentckpt](https://github.com/isaacuselman/agentckpt)
- **GitHub (crzyc0d3r/agent-checkpoint-resume):** Pattern where "after each completed step, the agent serializes its full state — progress, accumulated decisions, and the reasoning log — to a JSON checkpoint. On resume, completed steps are skipped and their decisions reload verbatim, so no earlier judgment is ever re-sampled." — [https://github.com/crzyc0d3r/agent-checkpoint-resume](https://github.com/crzyc0d3r/agent-checkpoint-resume)
- **Blog (Brandon Lincoln Hendricks, 2026):** Documents a financial services client whose document-processing agent lost 58 minutes of work to a Cloud Run timeout. The lesson: "without checkpointing, a single timeout meant starting from scratch." Recommends checkpointing at every step boundary as a production necessity for long-running agent tasks. — [https://brandonlincolnhendricks.com/research/implementing-agent-checkpointing-recovery-patterns-long-running-ai-tasks](https://brandonlincolnhendricks.com/research/implementing-agent-checkpointing-recovery-patterns-long-running-ai-tasks)
- **Zylos Research (2026):** Notes that "LangGraph, Temporal, and Dagster all ship first-class checkpoint primitives" and that "checkpointing transforms brittle agentic pipelines into fault-tolerant, resumable workflows." — [https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability)
- **GitHub (NousResearch/hermes-agent):** Issue #344 specifies a three-level failure recovery hierarchy (Retry → Replan → Decompose Further) plus checkpointing to `~/.hermes/checkpoints/` after each tool call, with stuck detection and health monitoring. — [https://github.com/NousResearch/hermes-agent/issues/344](https://github.com/NousResearch/hermes-agent/issues/344)

## Gotchas

- **Checkpointing on success only is not checkpointing.** If your system saves state only after a successful step, failures mid-step lose all progress. Checkpoint after every step boundary — success and failure alike.
- **Non-idempotent tool retries corrupt state.** The most common production mistake is retrying all failed tool calls indiscriminately. A duplicate email, a double-charged payment, a second UUID generated for the same entity — these are the real cost of not tagging tools by replay safety.
- **Skipping completed steps without replay protection re-samples decisions.** The checkpoint must freeze not just state but also the randomness state and tool-call history. If you replay a step because "it looked like it succeeded but we aren't sure," you may get a different tool or different arguments — which can invalidate downstream steps.
- **Context overflow on resume defeats the purpose.** Long-horizon tasks that checkpoint everything and reload everything on resume hit context limits fast. The checkpoint should contain only the accumulated state summary and tool history — not a full replay of every intermediate LLM output.
- **A crashed agent is not always recoverable.** If external state changed between checkpoint and crash (e.g., a database row was deleted by another process), resuming from checkpoint produces a semantically inconsistent world. Check for data version staleness before resuming execution, not after.
