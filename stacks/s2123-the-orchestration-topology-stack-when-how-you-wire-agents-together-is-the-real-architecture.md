# S-2123 · The Orchestration Topology Stack — When How You Wire Agents Together Is the Real Architecture

You have three agents that each work perfectly on their own. Now you need them to collaborate — on a deadline, under budget, with observability, without any one agent spinning into a loop that costs you $4,000 in an hour. The hard part is not the agents. It's the topology: how you wire them together, who owns the state, and what happens when one link in the chain breaks. Choosing the right orchestration architecture is the decision that determines whether your multi-agent system actually ships.

## Forces

- **Explicit control vs. speed to first agent**: LangGraph gives you graph topology you can reason about; CrewAI gives you a running team in an afternoon. Teams often pick fast and regret it when production load hits.
- **State explosion at agent boundaries**: Every handoff between agents risks context pollution, lost state, and redundant work. The more specialized your agents, the more coordination surface you create.
- **Framework gap**: Both leading frameworks (LangGraph ~10K PyPI/month, CrewAI ~47K GitHub stars) leave teams owning the full production stack — routing, observability, cost controls, retries, and scaling are not included.
- **The single-coordinator trap**: One supervisor routing everything serializes latency and becomes a single point of failure. But distributing control adds coordination overhead that can exceed the original task cost.
- **Protocol fragmentation**: Agent-to-agent communication is being reinvented per team, per framework. Google's A2A protocol (April 2025) aims to standardize this but is early.

## The Move

### Pick your orchestration topology based on task shape, not preference

**1. Sequential pipeline** — for linear, dependency-ordered tasks (research → write → edit → publish). Each agent's output feeds the next. Simple to reason about, hard to parallelize. State is the output of each node passed as input to the next. Best when tasks have a strict order and failure at any step should halt the workflow.

**2. Parallel fan-out / fan-in** — for tasks where the same input needs independent processing by multiple specialists (summarize five documents, evaluate one result three ways). One coordinator broadcasts to N workers, collects results, synthesizes. State lives in a shared store (Redis, Postgres) so workers can read/write without blocking each other. Best when tasks are embarrassingly parallel and synthesis is cheap relative to the sub-tasks.

**3. Hierarchical supervisor** — for complex, branching tasks requiring dynamic delegation (upstream agent decides which specialist to call next based on intermediate results). A central supervisor agent decomposes tasks and routes to worker subgraphs. Workers are isolated subgraphs — a crashed worker doesn't kill the supervisor. LangGraph's supervisor pattern implements this with a durable checkpointer so supervisor state survives restarts. At production scale, add a message queue (Redis Streams) between supervisor and workers.

**4. Dynamic routing** — for heterogeneous input types where the right agent depends on content (intent detection → specialized handler). A lightweight classifier or LLM-based router directs each request. Best for high-volume, low-latency systems where you need to serve many task types from one pipeline. The failure mode is routing drift — the router gets confident about the wrong thing and sends requests to the wrong agent.

### Add these regardless of pattern

- **Shared state store as first-class infrastructure**: Multi-agent state is not just conversation history. It's intermediate outputs, task status, and partial results. Store it in Redis (for speed) or Postgres (for durability and auditability). In-process state dicts don't survive restarts or retries.
- **Agent-to-agent communication via A2A protocol**: Google's Agent2Agent protocol (HTTP/JSON-RPC + SSE for streaming) standardizes how agents discover each other and exchange tasks across boundaries. Use it to avoid custom per-integration wiring. Pair with MCP (Model Context Protocol) for tool access — A2A handles inter-agent communication, MCP handles agent-to-tool.
- **Streaming from day one**: SSE-based streaming lets upstream agents receive incremental updates from downstream workers, enabling better orchestration decisions (e.g., supervisor can interrupt a runaway worker before it exhausts its context window).
- **Cost and loop guards as structural primitives**: Build timeouts, token budgets, and iteration caps into the graph topology itself, not as post-hoc checks. LangGraph's checkpointing lets you replay from any node — useful for retry and audit.

## Evidence

- **Microsoft ISE case study:** A large retail organization evolved from a modular monolith router pattern (one intent classifier, one agent per query) to a microservices architecture with a dedicated agent registry, per-agent role-based access control, and a centralized orchestration layer. The driver was cross-team reuse — other business systems needed the same agents, and tightly coupled agents couldn't be shared. — [Orchestration Patterns for Multi-Agent Systems: Performance and Trade-offs](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems) (Microsoft ISE Developer Blog, June 2026)

- **HN practitioner survey:** When asked "how are you orchestrating multi-agent workflows in production?", respondents reported: custom Node.js/Express with MongoDB shared state (pablovarela); LangGraph + git worktree parallel workers using Claude Code, Codex CLI, Gemini CLI (Chepko932); AGNO framework for minimalism (kathir05/HuntYourTribe); and "there's absolutely 0 framework out there that's good enough for serious work" (se_gmondy). A common thread: teams reach for custom solutions when frameworks hit production constraints around observability and state management. — [Ask HN: How are you orchestrating multi-agent AI workflows in production?](https://news.ycombinator.com/item?id=47660705) (Hacker News, ~118 days ago)

- **LangGraph supervisor production guide:** A detailed breakdown of the supervisor pattern at scale: default production stack uses Redis Streams as task/result bus + PostgreSQL as checkpoint store. Key finding: adding a message queue introduces routing hops, but buys worker-level fault isolation and independent horizontal scaling. The trade-off is worth it above ~10 concurrent agents. — [LangGraph Supervisor Pattern: Production Architecture Guide](https://markaicode.com/architecture/langgraph-supervisor-architecture/) (Markaicode, July 2026)

## Gotchas

- **Don't start with the framework, start with the task shape**: Sequential tasks need pipelines. Parallel independent tasks need fan-out. Tasks with dynamic branching need a supervisor. Choosing LangGraph vs. CrewAI before answering this is backwards.
- **CrewAI prototypes fast but hits a production ceiling**: Role-based crews are intuitive for initial builds, but implicit control flow makes it hard to reason about what happens when an agent loops. The "Loop of Doom" — uncontrolled agent-to-agent iteration — is a common CrewAI production failure mode that requires structural rewiring to fix.
- **LangGraph's checkpointing is not automatic observability**: Checkpoints give you replay capability, but you still need structured logging, trace IDs that span agent calls, and cost tracking per node. These are separate infrastructure concerns.
- **A2A is early-stage**: The protocol (April 2025) is promising but adoption is nascent. Microsoft's Agent Framework and n8n have shipped implementations, but most teams are still building custom inter-agent wiring. Don't bet critical paths on protocol stability yet.
- **Context window pollution compounds across agents**: Each agent sees its own system prompt, task description, and intermediate outputs. At 4–5 agents in a chain, token costs multiply and latency adds up. Audit total token count per workflow, not per agent.
