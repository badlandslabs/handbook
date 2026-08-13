# S-2591 · The Orchestration Topology Stack — When You're Not Sure What Shape Your Multi-Agent System Should Take

You have a complex agentic task. You know you might need multiple agents. But which pattern — sequential chain, parallel workers, hierarchical manager, or something else? Teams pick a topology based on vibes, spend three months building it, then discover the failure modes they didn't account for. The choice of orchestration pattern is the highest-leverage architectural decision in multi-agent systems, and the evidence for how to make it is finally real enough to use.

## Forces

- **Single agent matches multi-agent on 64% of tasks** — the coordination overhead isn't free, and for most work it's not worth paying
- **40% of multi-agent pilots fail within six months** — not because multi-agent doesn't work, but because teams pick the wrong topology or implement the right one without understanding how it breaks
- **Four canonical topologies exist** (orchestrator-worker, hierarchical, pipeline, peer-to-peer), each with distinct failure modes teams discover only in production
- **The "toy app ceiling"** — synchronous, single-session architectures collapse under real business workloads where work is async, cross-channel, and stateful across days
- **Context contamination** — shared global context in peer-to-peer or flat topologies causes agents to overwrite each other's state; context isolation is not automatic

## The move

**Use this decision tree:**

1. **Can the task be decomposed statically?** If yes → pipeline (sequential). If the steps are known ahead of time, a fixed chain is simpler and has one fewer coordination hop than any other pattern. No dynamic routing overhead.
2. **Are subtasks independent and parallelizable?** If yes → parallel fan-out (orchestrator-worker with concurrent dispatch). The orchestrator decomposes, fans out to workers, collects results. No inter-agent dependencies.
3. **Do agents need to delegate and synthesize with branching?** If yes → hierarchical (manager-agent). A manager receives the task, delegates to specialists, handles retries, synthesizes output. Correct home for delegation logic.
4. **Do agents need to negotiate or vote on a shared output?** If yes → peer-to-peer with a shared board. Each agent contributes to a shared artifact; consensus or voting resolves conflicts. Appropriate for evaluation, review, and debate tasks.
5. **None of the above, or genuinely unclear?** → Start with orchestrator-worker. It has the strongest production track record (Anthropic's own research system uses it), the clearest failure modes, and the most debuggable execution trace.

**For any topology above one agent:** run it behind a durable async queue (Redis Streams, Celery, or Temporal), not inline in a request thread. The moment your API request holds the LLM loop open, you've coupled your availability SLA to a non-deterministic process.

**For hierarchical:** pick `Process.hierarchical` in CrewAI once you have 3+ interdependent agents. The manager absorbs delegation and retry logic that a linear chain has nowhere to put.

**For topology generation at runtime:** Hive (Y Combinator-backed, 4 years in ERP production) takes a different approach — instead of a static DAG, a persistent "Queen" agent pilots work first, then spawns "Worker" clones at runtime based on task requirements. The topology grows from the work, not the other way around. This avoids the "fixed topology, changing requirements" brittleness that plagues LangChain/AutoGPT in production.

**Monitor for the specific failure modes of your topology:**

| Topology | Primary failure mode | Signal |
|---|---|---|
| Orchestrator-worker | Orchestrator becomes a bottleneck or single point of failure | Worker utilization < 30%, orchestrator queue depth growing |
| Hierarchical | Manager context overflow, cascading delegation failures | Manager turn count grows unbounded, worker outputs truncated |
| Pipeline | Error propagation; one bad output corrupts downstream steps | Downstream step outputs contain artifacts from upstream failure |
| Peer-to-peer | Context contamination, stale artifact reads | Agents acting on information from previous state |

## Evidence

- **Engineering post (primary):** Anthropic's Research system (June 2025) uses an orchestrator-worker pattern with a LeadResearcher agent that decomposes research tasks and spawns parallel Subagents. They explicitly cite avoiding a peer-to-peer "all agents talk to all" model because it caused "conflicting contributions" and "context fragmentation." — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **HN discussion (primary):** 543-point HN thread on "Building Effective AI Agents" (June 2025) surfaced broad agreement that "augmented LLM running in a loop" (Anthropic's definition) is the operative model, and that the distinction between workflows (predefined code paths) and agents (dynamic LLM-directed) maps directly onto topology choices. Multiple practitioners cited the 40% pilot failure rate as confirmation of topology mismatches. — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Research paper (primary):** UC Berkeley's "Why Do Multi-Agent LLM Systems Fail?" (arXiv:2503.13657, NeurIPS 2025) analyzed 1,642 execution traces from 7 frameworks and identified 14 failure modes in 3 categories (Design, Cooperation, Reasoning). Key finding: "MAS failures are primarily design problems, not just LLM limitations." — [arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)
- **Production framework (primary):** Hive's README documents the "toy app ceiling" problem — synchronous single-session architectures fail under real ERP workloads — and uses an OODA-loop-based Queen/Worker colony model that generates topology at runtime rather than from a static DAG. Backed by Y Combinator, 4 years in production for construction PO/invoice reconciliation. — [github.com/adenhq/hive](https://github.com/adenhq/hive)
- **Practitioner guide (secondary):** beam.ai's orchestration pattern guide (August 2026) benchmarks four patterns with cost/latency tradeoffs, cites Gartner's 1,445% surge in multi-agent inquiries, and notes that "72% of enterprise AI projects now use multi-agent architectures" while confirming the 40% pilot failure rate. — [beam.ai/agentic-insights/multi-agent-orchestration-patterns-production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

## Gotchas

- **The "more agents = better" trap:** A single agent with the right tools matches multi-agent on 64% of tasks at roughly half the cost. Only reach for multi-agent when you have genuine cross-domain specialization, parallelizable independent work, or open-ended research that no single loop can hold.
- **Context isolation is not free:** In peer-to-peer or flat topologies, agents sharing a workspace will overwrite each other's state. Use per-agent scoped snapshots or a shared "board" with explicit read/write contracts, not implicit shared context.
- **Hierarchical is not the default upgrade path:** Teams that start with sequential and "just add a manager" often end up with a manager that is itself a bottleneck. Hierarchical earns its cost at 3+ agents with branching dependencies — below that, the manager adds coordination overhead with no benefit.
- **The async queue is not optional for production:** Running a multi-agent loop inline in a request thread couples your availability SLA to non-deterministic LLM inference. Any team that skips the durable queue discovers this the first time a long-running agent gets killed by a timeout.
