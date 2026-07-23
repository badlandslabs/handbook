# S-157 · The Durable Execution Stack — When Your Pod Restarts and Your Agent Forgets Everything

An agent that crashes mid-task and restarts from scratch is not an agent with error handling — it is a slot machine. The failure mode that costs real teams real hours is not the agent choosing wrong. It is the infrastructure pulling the rug out: a Kubernetes OOMKill, a Cloud Run timeout, a process restart during a 20-step workflow — and all progress disappears. Durable execution externalizes agent state to persistent storage so that infrastructure failures become resume points, not restart points. Without it, every production deployment is a ticking clock on data loss.

## Forces

- **Agents are stateless by design.** LLMs have no memory between calls. Every conversation starts fresh. In production, that statelessness is a liability: a crash mid-workflow wipes everything.
- **Human-in-the-loop breaks the happy path.** A workflow that pauses 30 minutes for manager approval cannot hold an open HTTP connection. Without state persistence, the agent cannot resume after the approval comes back.
- **The persistence layer decision is the one teams get wrong first.** Teams ship on `MemorySaver`, watch a pod restart kill twenty in-flight threads, then scramble to reverse-engineer a database schema while checkpoint writes block the event loop. LangChain's 2026 report ties 60%+ of production incidents to state management failures.
- **Checkpointing is not free.** Every snapshot adds latency and storage overhead. The tradeoff between durability and performance must be made deliberately, not accidentally.

## The Move

The move is durable execution: persisting agent state at every step boundary so that infrastructure failures — not agent failures — become recoverable resume points.

**Checkpointing at every super-step.** LangGraph (GA at v1.0, October 2025) persists a state snapshot after every node transition. The checkpointer stores the full state object — messages, tool call history, intermediate results, progress markers — to durable storage. On restart, the agent resumes from the last checkpoint, not from scratch. A document analysis agent at step 17 of 20 restarts at step 17, not at step 1.

**Choose the right checkpointer backend for the deployment context.** `MemorySaver` is for development only — it survives nothing. `SqliteSaver` works for single-node deployments and local development. `PostgresSaver` (or Redis) is required for multi-instance production deployments where any node must be able to resume any thread. Using `MemorySaver` in production is the most common durable execution mistake.

**Tie checkpoints to idempotency keys.** A retry is only as safe as its idempotency key. Without one, a retried step that completed before the crash re-executes and corrupts state (double-insert, duplicate API call). Checkpoint the completion marker alongside the state so the retry knows it already ran.

**Use durable execution platforms as an alternative to rolling your own.** Inngest, AWS Step Functions, and Cloudflare Durable Objects provide automatic state persistence, automatic retries, and workflow resumption without custom infrastructure. These platforms treat human-in-the-loop as a first-class construct: approval queues are native pause/resume points, not async hacks. Durable execution crossed the early majority in 2025 with new offerings from AWS, Cloudflare, and Vercel, driven primarily by AI agent infrastructure needs.

**Build rollback capability into the graph.** A single bad tool call should not crash the entire application. Three lines of code can perform a state rewind that saves a 12-step run from a bad tool call. Design nodes that trigger automatic rollback when an external API fails, reverting to the last known-good state without dropping user context.

**Use thread IDs to isolate conversations and enable replay.** A thread_id groups checkpoints for one conversation or task. Engineers can replay past executions for debugging by resuming any historical thread. The store (separate from checkpointer) holds state across threads, enabling cross-session memory without checkpoint noise.

## Evidence

- **LangChain 2026 incident analysis:** 60%+ of production incidents traced to state management failures — [LangChain Engineering Report](https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture/)
- **LangGraph GA v1.0 checkpointing:** SqliteSaver and PostgresSaver provide persistent state snapshots across node transitions, enabling resume after pod restart or OOMKill — [LangGraph State Management Guide](https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture/)
- **GitHub PoC under OOMKill eviction:** The `nadja-mansurov/langgraph-checkpoints` repo demonstrates a container crash and seamless recovery via persistent checkpointer, simulating production Kubernetes OOMKilled scenarios — [GitHub Repository](https://github.com/nadja-mansurov/langgraph-checkpoints)
- **Durable execution platforms adoption:** New offerings from AWS, Cloudflare, and Vercel in 2025, driven by AI agent infrastructure needs, with Inngest treating human-in-the-loop as a native pause/resume pattern — [Inngest Engineering Blog](https://www.inngest.com/blog/durable-execution-key-to-harnessing-ai-agents)
- **Human-in-the-loop pattern:** Three fundamental challenges solved by checkpointing: HITL workflows (approval takes 30 minutes, agent must resume after), fault tolerance (process crash loses 80% progress), and context rot (fresh agents have no memory of prior work) — [Understanding Data — Agent Memory Patterns](https://understandingdata.com/posts/agent-memory-patterns/)

## Gotchas

- **MemorySaver in production will bite you.** It works perfectly in development. It loses everything on the first pod restart. Migrate to PostgresSaver or Redis before any deployment that matters.
- **Checkpoint writes block the event loop in synchronous backends.** For high-throughput production systems, use async checkpointers or accept the latency hit and load-test for it.
- **Without idempotency keys, retries are dangerous.** A checkpoint at step 17 does not mean step 17's side effects completed. Always checkpoint the completion marker alongside state.
- **Checkpoint frequency is a tradeoff.** Every step boundary snapshot means high storage and latency overhead. For long-running agents, consider snapshotting only at significant milestone nodes, not every atomic step.
- **State rewind is not the same as rollback.** Reverting to a previous checkpoint reverses the agent's memory of what happened, but does not undo external side effects (sent emails, written records, API calls). Design with that constraint in mind.
