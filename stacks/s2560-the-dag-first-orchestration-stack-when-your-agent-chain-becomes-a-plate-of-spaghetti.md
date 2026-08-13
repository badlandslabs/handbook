# S-2560 · The DAG-First Orchestration Stack — When Your Agent Chain Becomes a Plate of Spaghetti

When your "chain" of LLM calls graduates from a weekend project to a product feature, the same properties that made it easy to write make it catastrophically easy to break. Ad-hoc chaining — stitching agent calls together with Python conditionals and shared global state — works until it doesn't. Then it deadlocks, silently corrupts state, and costs 10x what it should.

## Forces

- **Prototyping speed vs. production resilience** — simple chains are fast to write and impossible to resume after a crash or a human approval that takes six hours
- **Single-agent limits vs. multi-agent coordination overhead** — one agent hits context limits; five agents hit deadlock, state corruption, and silent failure modes you never saw coming
- **Implicit control flow vs. explicit structure** — chat-transcript-based orchestration is readable but non-deterministic; state machines are verbose but auditable
- **Token-driven performance variance** — architecture explains ~80% of agent performance differences, far more than model choice, making the wiring load-bearing

## The move

Stop treating orchestration as a prompt problem. Treat it as a first-class state machine from day one — even if you're only wiring two agents.

- **Start with the minimal graph, not the minimal script.** If you have two agents with a conditional branch, that's already a DAG. Use LangGraph's `StateGraph` instead of a Python `if/else` over LLM outputs. The overhead is one afternoon; the rescue from spaghetti is months.
- **Choose the orchestration school that matches your failure tolerance.** DAG-based (LangGraph, Temporal, Prefect) for deterministic, resumable pipelines. Event-driven (Kafka, MCP, A2A Protocol) for reactive, decoupled systems. Actor model (AutoGen v0.4, Akka) for isolated-state message-passing with supervision hierarchies. Most teams need DAG first.
- **Treat the orchestrator and inference as separate services with independent scaling.** The orchestrator (CPU-bound, state machine logic) scales on conversation throughput. The inference engine (GPU-bound) scales on token volume. Coupling them is the #1 scaling mistake in local deployments.
- **Build failure detection into the graph, not as an afterthought.** Timeout detection and heartbeat liveness signals are mandatory. A failed agent that doesn't respond becomes a silent black hole — tasks disappear, the system waits indefinitely, and nobody notices until a customer escalates. Assign maximum retry counts, explicit stopping conditions, and confidence thresholds at the graph edge, not in the prompt.
- **Route models by task complexity, not globally.** Use frontier models for orchestration decisions and complex reasoning; mid-tier models for standard tool calls; small models for high-frequency execution tasks. This heterogeneous routing pattern delivers comparable results at a fraction of the cost.

## Evidence

- **Engineering blog (Anthropic, Jun 2025):** Anthropic's Research feature uses an orchestrator-worker pattern — a lead agent coordinates parallel subagents that each search independently, compress information, and report back. The lead decides next steps without waiting for all subagents to finish. Result: 90% improvement on internal benchmarks vs. single-agent, with token usage explaining 80% of performance variance. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)
- **HN discussion + engineering research:** A practitioner analyzing autonomous development platforms found that token usage explains ~80% of performance variance across agent tasks — architecture decisions matter more than model selection. Teams using CrewAI for fast prototyping are now migrating to LangGraph once they hit the ceiling: "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." — [URL HN](https://news.ycombinator.com/item?id=46993479) [URL Reddit](https://www.reddit.com/r/LocalLLaMA/comments/1qxn1gu/production_architecture_for_multimodel_agent/)
- **Engineering post (Tian Pan, Jun 2026):** Real-world deadlock in a production multi-agent system: Agent A requested data from Agent B, but that request crossed a "human review required" boundary and landed in a Slack channel watched by someone at lunch. Agent B, before answering, asked Agent A for context — landing in a Jira queue watched by someone in a customer call. Result: workflow hung for 19 hours with no error, no timeout, no alert. The lesson: if any tool call can route to human approval, you're running a scheduler. Treat approval gates as first-class edges in your DAG with timeout and escalation paths. — [URL](https://tianpan.co/blog/2026-06-01-the-multi-agent-deadlock-that-hangs-on-two-calendars)

## Gotchas

- **LangGraph's graph becoming unmaintainable** — the same expressiveness that makes it powerful makes it easy to over-graph. Start with 3–5 nodes. Extract sub-graphs only when a cluster of nodes has a clear boundary (e.g., "research subgraph" with its own internal state).
- **CrewAI-to-LangGraph migration debt** — the faster you prototype with CrewAI, the more structural debt you accumulate before you need branching, crash-safe resume, or human-in-the-loop approvals. Audit your graph topology before the migration becomes urgent.
- **Missing compensating transactions** — when an agent completes part of a multi-step task and a subsequent step fails, the workflow state is dirty. Without explicit compensating transactions (rollback steps defined at each graph edge), you get partial execution with no recovery path.
- **Framework overhead is real.** One Show HN practitioner built a 15KB multi-LLM orchestrator from scratch specifically because LangChain added 250ms+ overhead before the LLM was even called. For high-frequency, low-latency use cases, custom orchestration or a thin framework beats the full LangGraph stack.
