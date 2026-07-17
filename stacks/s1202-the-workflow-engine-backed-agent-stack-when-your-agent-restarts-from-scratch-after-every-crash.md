# S-1202 · The Workflow-Engine-Backed Agent Stack — When Your Agent Restarts from Scratch After Every Crash

Your agent is 37 minutes into a 45-minute task: it has searched 9,847 SEC filings, drafted a financial report, sent a Slack message to the analyst, and is about to submit the report to the compliance system. Your container restarts. When it comes back up, the agent has no memory of any of that. It starts over. Nine thousand filings. Forty-five minutes. The Slack message fires again. This is not a model problem. This is an architecture problem.

The fix: run your agent inside a **workflow engine** — the same class of infrastructure that runs critical business processes in banking and healthcare. Not as a feature you add later, but as the execution substrate from day one.

## Forces

- **Agents are long-running by nature.** A single task can span minutes to hours, dozens of tool calls, API rate-limit pauses, and human approval gates. A standard HTTP request/response (or even a queue worker) has no mechanism to survive a process restart mid-task.
- **Session memory is not durable execution.** Saving chat history lets the agent *remember*. It does not prove which shell command ran, which email was sent, whether a compliance form was submitted, or whether a retry would fire a side effect twice. These are fundamentally different guarantees.
- **LLM steps are non-deterministic.** Re-running "extract the revenue figure" can return a different answer. Naive restart-from-chat-history is not reproducible execution — it's a coin flip.
- **Human-in-the-loop means indefinite pauses.** An agent awaiting compliance approval may wait days. It must wake with full context when the approval arrives.
- **Tool calls have real-world consequences.** Duplicate email sends, double database writes, repeated API charges. An execution substrate must track completed steps as first-class facts, not chat history.

## The move

**Treat the workflow engine as the operating system for your agent.** Just as an OS persists file writes to disk before confirming them to the application, a workflow engine persists completed execution boundaries before the agent proceeds. On crash, the agent resumes from the last confirmed boundary — not from the beginning.

### The five capabilities a workflow engine must provide for agents

1. **Execution journal** — a durable, append-only log of every completed step. Not the agent's memory, not its chat history: a verified record of what the engine confirmed was done. The agent's session state becomes a read cache of this journal; the journal is the source of truth.

2. **Idempotent tool boundaries** — every tool call that has side effects must be wrapped with idempotency keys. The workflow engine issues the key; the tool receives it and de-duplicates. If the workflow replays after a crash, the tool recognizes the already-seen key and returns the cached result without re-executing. Without this, durable execution is a duplicate-side-effect machine.

3. **Versioned prompts and tools** — when a workflow is mid-execution and you deploy a model update, the running instance must continue with its original versions. Pin the model, the prompt, and the tool schemas at workflow start. Track versions in the journal.

4. **Durable human approvals** — externalize approval gates as workflow tasks with their own durable state. The workflow pauses, the approval is stored durably, and the workflow resumes on signal. Do not rely on in-memory state or chat history to hold a pending human decision.

5. **Recovery tests** — before shipping, kill your agent process mid-workflow and verify it resumes correctly. This is the agentic equivalent of chaos engineering. If you cannot survive a process crash, you cannot survive a deployment, a spot-instance termination, or a network partition.

### Reference stack

```
┌─────────────────────────────────────────┐
│  Agent (model + tools)                  │
│  [thinks, calls tools]                  │
└──────────────┬──────────────────────────┘
               │ tool calls + results
               ▼
┌─────────────────────────────────────────┐
│  Workflow Engine                         │
│  ┌─ Journal (durable, append-only)      │
│  ├─ Step executor (confirms completion)  │
│  ├─ Idempotency key issuer             │
│  ├─ Human approval gate manager         │
│  └─ Version pin store                   │
└─────────────────────────────────────────┘
```

**Engines to evaluate:** Temporal (strongest ecosystem, Walrus persistence), Inngest (serverless-first, TypeScript-native), Restate (fault-tolerant, minimal ops), DBOS (database-native, SQL-accelerated), Hatchet (event-driven, parallel step support), Cloudflare Workflows (edge-native, KV-backed), AWS Lambda Durable Functions, Azure Durable Task.

### The MCP + workflow engine combination

MCP handles the *vertical* integration (agent → tools with schema, auth, and response parsing). The workflow engine handles the *horizontal* integration (agent run → crash → resume → completion). The two are complementary and independently valuable. An agent with MCP but no workflow engine survives tool integration failures but not process crashes. An agent with a workflow engine but no MCP has durable execution but must rebuild every tool integration from scratch.

### Key signals that you need this now

- Your agent tasks run longer than 5 minutes
- You have already written a retry loop and it still produces duplicate side effects
- Your on-call runbook for agent failures says "restart from the beginning"
- You have human approval gates in your agent workflow
- Your agent cost per task varies by 3×+ for similar inputs (a sign of non-deterministic re-runs)

## Receipt

> Verified 2026-07-16 — Pattern distilled from Zylos Research (2026-04-24, "Durable Execution for AI Agent Runtimes"), Brandon Lincoln Hendricks (2026-04-09, "Implementing Agent Checkpointing"), and WorkflowBuilder.io production analysis. Key citations: Temporal's durable execution model, Restate's fault-tolerance semantics, Inngest's serverless approach. No fabricated numbers.

## See also
- [F-15 · Durable Execution](f15-durable-execution.md) — the forward-deployed companion; this entry covers the workflow-engine substrate, F-15 covers the field-deployment patterns
- [S-1003 · Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — specific failure mode patterns; this entry is the infrastructure substrate that makes recovery durable
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — the decision tree for recovery strategies; this entry is level 0 (the execution journal that makes all other recovery levels possible)
- [S-09 · Memory Systems](s09-memory-systems.md) — what the agent knows; this entry is how far the agent got (the execution journal)
- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — reproducible agent behavior; workflow engines enable this by pinning versions and replaying idempotent steps
