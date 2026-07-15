# S-1131 · The Shared-State Stack — When Your Second Agent Erases the First

You run two agents in parallel for speed. Both read the same file, make independent edits, and write back. One agent's work vanishes silently. No error is thrown. The output looks plausible. You find out three days later that the customer's record was overwritten. This is the shared-state problem — and as of April 2026, 57% of production multi-agent failures trace to concurrency issues, not model quality.

## Forces

- **Parallelism is the point, but shared state is the trap.** Multi-agent systems deliver value through parallel execution — yet every shared resource (file, database row, JSON store) becomes a race condition when two agents touch it simultaneously.
- **Silent failure is the worst failure mode.** Classic software race conditions throw errors. Agent race conditions return HTTP 200 with plausible-looking output. The agent doesn't know its work was overwritten. You don't know until a human notices.
- **Frameworks solve the easy coordination.** Agent frameworks handle individual agent capabilities well. They do not prevent two agents from silently overwriting each other's work on shared state. This gap is where production systems break.
- **Workspace isolation costs simplicity; shared state costs correctness.** Separating agent workspaces eliminates races but creates integration nightmares. Shared state is natural but requires engineering discipline that most teams underestimate.

## The move

**Treat shared state like a database, not a filesystem.** Apply database-grade concurrency controls to agent state, even when it's just JSON files on disk.

- **Use atomic writes exclusively.** Never `read → modify → write` in separate steps. Instead: write to a temporary file with a unique name, then rename atomically (e.g., `mv /tmp/output-{uuid}.json /data/state.json`). The filesystem rename is atomic on POSIX systems and prevents torn reads.
- **Implement optimistic locking for shared records.** Tag every state object with a monotonically increasing version. On write: `UPDATE ... WHERE version = expected_version`. If the affected row count is 0, someone else modified it — retry with the new version.
- **Assign one agent as the writer of record per resource.** Don't let two agents write the same entity. Use a lightweight coordination layer: a MongoDB document with a pipeline ID, a Redis lock with a TTL, or a simple `@coordinate` decorator that acquires a named lock before executing.
- **Isolate agent workspaces by default.** Give each agent a private working directory for intermediate artifacts. Only publish to shared state at explicit, intentional handoff points. This converts silent overwrites into loud "this path doesn't exist" errors.
- **Design for idempotent writes.** When a race does occur and a write is lost, make the next run of the same agent re-derive the correct state rather than corrupt it further. Use immutable event logs (append-only) instead of mutable snapshots where possible.
- **Instrument shared-state access with audit trails.** Log every read and write to shared state: which agent, which resource, which version, timestamp. Without this, debugging a race condition is archaeology.

## Evidence

- **AgentMarketCap blog (April 2026):** Documents the shared memory problem in depth, finding that 57% of production multi-agent failures stem from concurrency issues. Cites the specific failure mode: "two agents read the same file, make independent edits, and race to write back — with no error thrown anywhere. One agent's work silently disappears." — [agentmarketcap.ai/blog/2026/04/10/concurrent-multi-agent-state-management](https://agentmarketcap.ai/blog/2026/04/10/concurrent-multi-agent-state-management)
- **HN "Ask HN" multi-agent discussion (4 months ago):** Multiple practitioners independently surface state coordination as the #1 underrated problem. Comment from a developer running a 13-agent system: "The biggest underappreciated problem is state coordination. Frameworks handle individual agent capabilities well. What they don't handle: preventing two agents from silently overwriting each other's work on shared state." — [news.ycombinator.com/item?id=47387252](https://news.ycombinator.com/item?id=47387252)
- **r/LLMDevs coordination library post (8 months ago):** Developer built a coordination library specifically for multi-agent race conditions, using resource locks + event-driven decorators to serialize access to shared LLM APIs and state. Open-sourced after hitting rate limit failures and state corruption in production. — [reddit.com/r/LLMDevs/comments/1mq4p1q](https://www.reddit.com/r/LLMDevs/comments/1mq4p1q/built_a_coordination_library_to_handle_race/)
- **SynapseAI error catalog:** Documents concrete failure patterns including the "Two Parallel Agents Corrupt Shared File" symptom: partial data, last writer wins silently, no error. Root cause: read-modify-write without atomicity. — [ddaekeu3-cyber.github.io/synapse-ai/solutions/concurrency/parallel-agents-writing-same-file](https://ddaekeu3-cyber.github.io/synapse-ai/solutions/concurrency/parallel-agents-writing-same-file)

## Gotchas

- **The file `w` mode overwrite looks safe but isn't.** `open(path, 'w').write(data)` is atomic at the OS level only for small writes under PIPE_BUF (typically 4KB). For anything larger, use the temp-file-then-rename pattern.
- **CrewAI's `Process.hierarchical` mode serializes agents to avoid races — but at the cost of parallelism.** Many teams default to sequential processes and wonder why their 5-agent crew runs no faster than one. The tradeoff is real; pick the mode consciously.
- **Retry logic on optimistic lock conflicts amplifies cost.** If three agents all race to update the same record, two will fail and retry, doubling or tripling LLM calls. Budget for this in your token accounting.
- **Workspace isolation creates its own problem:** agents can't see what other agents wrote without explicit handoff. The integration surface (shared-state boundaries) just moves from data corruption to interface design. Plan the handoff protocol explicitly.
- **Trust scores with no time-based decay.** One open-source coordination library assigns trust scores to agents but doesn't decay them. An agent trusted six months ago and dormant since still walks back in with maximum trust. In long-running multi-agent systems, re-evaluate trust on a schedule.
