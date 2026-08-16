# S-2739 · The Shared-State Coordination Stack — When Your Agent Knows Too Much and Does Too Little

You split your agent into two specialized agents to parallelize work. Both now have their own context windows, their own tool sets, and their own partial views of the task. Six hours later, one agent has been waiting on a result the other never produced, and nobody can reconstruct the conversation because there was no shared state. Single agents hit context limits and degrade. Multiple agents without shared state fragment and deadlock. The answer is a shared workspace that all agents read from and write to — a coordination layer that decouples who thinks from what gets remembered.

## Forces

- **Context windows are finite but work is not.** A single agent's context degrades as it accumulates history. At 150k+ tokens, it starts missing recent instructions. Splitting into multiple agents is the right instinct, but naive splitting just moves the problem into inter-agent silence.
- **Specialization requires state sharing, not just task delegation.** A researcher agent and a coder agent working in isolation produce partial solutions. Without a shared memory that both can read and write, the researcher finishes, the coder starts from scratch, and neither knows what the other concluded.
- **Inter-agent message passing has all the classic distributed systems problems.** Without explicit sequencing, agents race on shared resources. Without idempotency, duplicate writes corrupt the shared state. Without visibility, a stuck agent blocks the whole pipeline silently.
- **The blackboard pattern solves context window pressure differently than a manager agent.** Funneling everything through a manager's context window bottlenecks at the model's limits. A shared memory system lets each agent contribute partial solutions without forcing them through a single head.

## The Move

The core technique: decouple **thinking** from **remembering**. Specialized agents each maintain their own context window and focus on their domain, but all write structured outputs to a shared state store. The orchestrator (or the agents themselves) read from this store to decide next steps.

**Structured shared state design:**
- **Per-task workspace.** Create a dedicated namespace/folder for each task session. All agents working on that task read and write only within it.
- **Structured write protocol.** Agents don't dump free-text summaries — they write structured entries: `{agent_id, step, finding, confidence, next_needed}`. This makes state machine-readable, not just human-readable.
- **Signaling, not just storage.** The shared state also serves as a signal bus: an agent writes "step_3_complete, see key_X" so other agents know when to proceed. No polling, no implicit sequencing.
- **Distillation before consolidation.** Anthropic's research system (2025) found that subagents should produce distilled findings — not raw tool outputs — before writing to shared state. The lead agent then synthesizes. This prevents shared state from becoming a noise dump.
- **Read-your-writes consistency.** Use a store that guarantees read-your-writes (Redis, SQLite, or a proper KV store). An agent that writes a checkpoint must be able to read it back immediately, even if it restarts.

**Framework support:**
- LangGraph supports shared graph state with typed state schemas — agents update specific state fields, not the whole context
- CrewAI uses role-based agents with shared crew goals and configurable memory backends
- Smolagents (HuggingFace) supports multi-agent via message passing with a lightweight coordination layer
- Microsoft AutoGen and AutoGen Studio support group chat with a shared manager that can pass state
- CAMEL (Communicative Agents) uses role-playing with structured task decomposition
- DeerFlow (ByteDance, GitHub trending Feb 2026, 25k+ stars) uses a structured shared-state approach with role-specialized subagents

**Failure handling in shared-state systems:**
- An agent that crashes mid-write must leave a state marker (e.g., `step_3_in_progress`) so the orchestrator knows to resume rather than restart
- Dead-letter queues for state entries that fail validation — don't block other agents
- Circuit breaker on shared-state reads: if the store is unavailable, agents degrade to their local context rather than hanging

## Evidence

- **Engineering blog:** Anthropic's multi-agent research system (June 2025) uses Opus 4 as lead agent with Sonnet 4 subagents that produce distilled findings into a shared synthesis layer. The system outperforms single Opus 4 by 90.2% on internal research benchmarks. Key lesson: subagents run in parallel with separate context windows, then the lead agent synthesizes — not the reverse. — https://www.anthropic.com/engineering/multi-agent-research-system

- **Research paper:** A 2025 paper on LLM-based multi-agent blackboard systems reported stronger end-to-end task success than RAG baselines and master-slave architectures. The blackboard approach outperformed because it avoids funneling all information through a manager's context window — agents contribute partial solutions to persistent shared memory. — Reported via Zylos Research synthesis (2026), citing the original paper as primary source

- **Founder survey:** MMC Ventures interviewed 30+ European agentic AI startup founders (November 2025). 52% build agentic infrastructure fully or predominantly in-house, with multi-agent coordination cited as the primary area of architectural investment. Inter-agent state management was the top engineering challenge reported — ahead of model selection or tool integration. — https://mmc.vc/research/state-of-agentic-ai-founders-edition/

## Gotchas

- **Don't make shared state a free-text dump.** Agents that write long narrative summaries to shared state create exactly the context-overflow problem the architecture was meant to solve. Enforce structured schemas.
- **Don't assume atomicity.** A shared state write that crashes mid-update leaves corrupted state. Use append-only logs with checkpoint markers rather than in-place overwrites.
- **Don't coordinate through a manager agent unless the task genuinely requires it.** The manager becomes the bottleneck. Only use hierarchical coordination when task decomposition requires it — prefer flat blackboard for independent parallel work.
- **Don't skip observability at the coordination layer.** Log every state write, every signal, and every read. Without this, debugging a multi-agent deadlock is archaeology.
