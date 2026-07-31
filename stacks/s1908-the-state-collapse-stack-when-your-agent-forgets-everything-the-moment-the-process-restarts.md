# S-1908 · The State Collapse Stack — When Your Agent Forgets Everything the Moment the Process Restarts

Your agent spent 40 minutes navigating a codebase, wrote three files, and was three steps from done when the Kubernetes pod hit a memory limit and restarted. In-memory state: gone. It restarted from scratch and did it again. And again. By the fourth restart it had burned through $180 and still hadn't finished — not because the model was weak, but because there was nowhere to save "where I was."

This is State Collapse: the failure mode where agent progress exists only in RAM, and any process interruption — OOM kill, redeploy, crash, timeout — erases it completely. Unlike a traditional service restart, you can't just start the process back up; you have to re-explain the goal, re-establish context, and re-do all the work the agent had already completed.

## Forces

- **Agent progress lives in the LLM's context window, not in durable storage.** A traditional long-running job checkpoints state to disk or a DB. An agent's state is encoded in the growing conversation history, tool call outputs, and intermediate reasoning — none of which survives a process restart unless explicitly saved.
- **LLM providers enforce hard timeout limits.** Anthropic's max session duration, OpenAI's response timeout, and per-request latency limits mean agents running complex tasks across dozens of steps will eventually hit a wall they cannot route around.
- **Naive in-memory recovery restarts the entire conversation.** Copying chat history back into context re-sends all prior tokens, but the agent's *working memory* — what it was about to do next, what partial results existed, what the stack state looked like — is lost. The agent may produce different intermediate outputs even from the same history, leading to non-deterministic re-runs.
- **Long-running agents accumulate context at the worst possible time.** The richer the agent's progress history, the more tokens it must re-send on restart — increasing cost and latency per recovery attempt.
- **Tool call side effects compound the problem.** If an agent partially executed a task (wrote a file, sent an email, called an API) before crashing, naive restart can produce duplicate side effects unless state tracks which steps completed.

## The Move

Checkpoint agent state at each step boundary and resume from the last durable checkpoint, not from scratch.

**Checkpoint what, not just history.** The conversation log is necessary but not sufficient. Capture:
- The full message history (for LLM context reconstruction)
- A structured state object (agent-defined TypedDict) holding key variables, pointers, and flags
- A sequence number or step index marking where execution stopped
- Which tool calls have been applied as side effects (idempotency key per step)

**Use a persistence-backed graph framework instead of raw loops.** LangGraph's `MemorySaver` / `PostgresSaver`, AutoGen's session persistence, and CrewAI's checkpointing primitives all provide step-boundary snapshot semantics. These frameworks serialize state to a DB between LLM inference calls, so a process restart loads the last snapshot and the agent resumes from the next unexecuted step.

**Distinguish two checkpoint scopes.** Short-term checkpointing (per-step) handles crashes and redeploys and should be fast (SQLite for single-instance, Postgres for distributed). Long-term memory (vector-backed episodic or fact-based storage) handles cross-session continuity — "the user prefers conservative risk models" — and is queried on session start rather than replayed wholesale.

**Design checkpoints at natural boundaries.** Save after each tool call completes successfully, not mid-call. Mid-call crashes (network timeout between writing output and acknowledging it) should leave the agent in a known state — either the tool executed and the checkpoint includes its output, or it didn't and the checkpoint excludes it.

**Make state reconstruction explicit, not implicit.** On resume, the agent should receive a structured prompt indicating: `task: <goal>, completed_steps: <N>, last_output: <data>, next_action: <reasoning>`. Don't rely on the LLM to re-derive "where was I" from raw history — give it a state briefing.

**Implement idempotency guards for non-idempotent operations.** Before executing a tool call on resume, check whether it was already applied (using the step's idempotency key). Skip it if completed; execute if not. This prevents double-sends, double-writes, and duplicate emails.

## Evidence

- **HN Show HN — AgentKeeper (2025):** "Agents lose memory when switching providers, restarting, or crashing. AgentKeeper introduces a cognitive persistence layer that stores facts independently of any LLM provider and reconstructs context dynamically." — [Show HN: AgentKeeper – cognitive persistence layer for AI agents](https://news.ycombinator.com/item?id=47217244)

- **AWS Database Blog — LangGraph + DynamoDB (2025):** Detailed walkthrough of using DynamoDB as a checkpoint store for LangGraph agents. Shows that checkpointed state lets an agent "load the state from the last node and add the competitor step" — without it, "it cannot resolve what 'looks good' refers to and has to start over." — [Build durable AI agents with LangGraph and Amazon DynamoDB](https://aws.amazon.com/blogs/database/build-durable-ai-agents-with-langgraph-and-amazon-dynamodb/)

- **"Edge of Context" engineering blog — Long-Running AI Agent Runtime (2025/2026):** Defines five runtime primitives for long-running agents: Session (append-only event log), Sandbox (process isolation), Checkpoint (step-boundary snapshot), Harness (feedback/retry logic), and Gate (human approval). States: "If you cannot explain where each primitive lives, the agent is still a prototype." — [Long-Running AI Agent Runtime in 2026: Sessions, Sandboxes, Checkpoints, and Harnesses](https://slavadubrov.github.io/blog/2026/05/26/ai-agent-runtime)

- **Google Agent Bake-Off — distributed multi-agent (2024/2025):** Google's internal experiments found distributed multi-agent architectures cut processing time from 1 hour to 10 minutes (6×), in part because each sub-agent maintains independent state that survives failures of peer agents. — [Multi-Agent AI Architecture in Production: Patterns, Frameworks & Observability (2026 Guide)](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)

- **Amazon Kiro incident — pre-execution enforcement (December 2025):** An agent autonomously deleted and recreated a production environment, causing a 13-hour outage. Key lesson: the agent had no durable checkpoint of policy constraints, so it re-executed side-effect-bearing actions on restart. — [Solving the 78% Problem: Why AI Agent Pilots Work and Production Deployments Don't](https://earezki.com/ai-news/2026-04-22-the-78-problem-why-ai-agent-pilots-work-and-production-deployments-dont/)

## Gotchas

- **"Checkpointing" chat history is not the same as checkpointing agent state.** Serializing the full conversation to a DB is necessary for context reconstruction but doesn't tell the resumed agent *where to pick up*. Always pair history with a structured state briefing.
- **SQLite checkpointers work for single-instance agents but not for horizontally scaled ones.** If your agent fleet shares work across processes, use a distributed checkpoint store (Postgres, DynamoDB, Redis) with proper locking or a single-writer protocol to avoid race conditions on resume.
- **Checkpoint frequency is a trade-off between recovery time and overhead.** Saving after every LLM call adds latency (~50–200ms per checkpoint). Saving only after major steps risks re-doing expensive sub-computations. The sweet spot: checkpoint after every tool call that produces state change.
- **State schema changes break existing checkpoints.** When you add or rename fields in your TypedDict state, old checkpoints fail to deserialize. Implement schema versioning and migration, or use a schema-lax serialization format (JSON with versioning field) for checkpoints.
- **Idempotency keys require careful scoping.** If a tool call writes `file_v2.py` and the checkpoint saves before the write, a resume will skip the write. If the file didn't exist, the agent deadlocks. Always check preconditions before applying idempotent-safe skips.
