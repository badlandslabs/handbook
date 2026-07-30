# S-1886 · The Multi-Agent Orchestration Stack — When One Agent Isn't Enough and Three Is Too Many

Your single agent handles a 10-step workflow cleanly. Then the workflow grows to span three teams' APIs, four data formats, and a compliance check. Your agent starts missing steps, hallucinating intermediate results, and making domain decisions it wasn't trained for. You split it into specialized agents — and immediately face new problems: coordination overhead, shared state conflicts, and a 40% pilot failure rate. This is the multi-agent orchestration gap: the point where splitting work across agents becomes tempting, and the failure modes multiply just as fast.

## Forces

- **Single agents hit a complexity ceiling.** A monolithic agent handling heterogeneous tasks (code review + deployment + Slack notification + compliance check) requires a prompt so long it overflows context, a tool list so broad it exceeds rate limits, and a model so expensive it eats your budget. Domain-specific behavior gets diluted across the full scope.
- **Multi-agent systems have a 40% pilot failure rate within 6 months of production deployment.** The failure isn't that coordination doesn't work — it's that teams pick the wrong orchestration pattern or implement the right one without understanding how it breaks. The orchestration topology is load-bearing; changing it mid-production is expensive.
- **The right pattern is domain-dependent.** Gartner reported a 1,445% surge in multi-agent system inquiries between Q1 2024 and Q2 2025, with the average organization now running 12 agents. But the field has converged on no single dominant pattern — instead, four to six distinct topologies each solve a different coordination problem, and the risk is applying the wrong one.

## The Move

**Map your workflow structure to an orchestration topology, not the other way around.**

### 1. Match topology to dependency structure

Four patterns cover most production cases:

| Pattern | Best For | Failure Mode |
|---------|----------|--------------|
| **Supervisor/Coordinator** | Heterogeneous tasks, one query needs multiple domains | Coordinator becomes a bottleneck; single point of failure |
| **Orchestrator-Worker** | Tasks that decompose into independent subtasks | Orchestrator mis-splits work; workers produce incompatible outputs |
| **Pipeline/Linear** | Ordered stages, each output feeds the next | No branching; any stage failure cascades |
| **Group Chat / Broadcast** | Brainstorming, multi-perspective synthesis | Chaotic; no authoritative synthesis step |

The orchestrator-worker pattern delivers **40-60% cost reduction** over running all tasks on capable models, because workers use cheaper, task-specific models while the orchestrator handles routing and assembly. But this only works when subtasks are genuinely independent. If subtasks have shared dependencies, a pipeline pattern prevents race conditions.

### 2. Govern shared state explicitly

Multi-agent systems share state through three mechanisms, each with different trade-offs:

- **Shared context store** (e.g., Redis, PostgreSQL with agent-accessible schema): Low latency, ACID guarantees, but requires schema design upfront. Microsoft ISE's production case study documented a retailer migrating from a modular monolith to microservices with a shared Redis layer — the key lesson was that schema changes require a migration strategy because multiple agents may read/write simultaneously.
- **Message passing** (agents communicate via structured payloads): Easier to reason about per-agent, but requires a message bus and explicit serialization. Risk of message loss if consumers are down.
- **Event-driven** (agents publish/subscribe to domain events): Best for loose coupling across team boundaries. Hardest to debug because causal chains span multiple services.

### 3. Implement circuit breakers at the agent boundary

Unlike traditional circuit breakers that trip on HTTP 500s, agent circuit breakers must handle a broader failure surface: the LLM returning garbage (HTTP 200), a tool succeeding technically but failing semantically, or reasoning chains producing confident nonsense. The pattern from production deployments:

```
On tool failure → increment failure counter → if threshold exceeded, trip breaker → feed error back to agent as structured context ("Tool X unavailable; try alternative approach") → agent can degrade gracefully rather than retry into a loop.
```

### 4. Keep the context window manageable via code-execution-with-MCP

Anthropic's engineering team documented a practical token-reduction technique: rather than loading all MCP tool definitions upfront (which floods the context window), present MCP servers as code APIs. The agent writes code to call tools, batching operations. Their analysis showed this pattern is critical at scale — passing every intermediate result through the LLM context creates compounding token costs and latency, while code-based tool invocation keeps the context stable.

## Evidence

- **Microsoft ISE case study:** A large retailer's production chatbot transitioned from a deterministic router pattern (modular monolith) to a microservices model with coordinator-based orchestration. Documented real trade-offs: coordinator overhead vs. parallelism, shared state governance, and performance at scale. — [devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Beam.ai multi-agent research:** Analysis of 1,445% Gartner-reported growth in multi-agent inquiries (Q1 2024 → Q2 2025), average 12 agents per organization, 40% pilot failure rate within 6 months. Documents six orchestration patterns with cost tradeoffs and failure modes. — [beam.ai/agentic-insights/multi-agent-orchestration-patterns-production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **KDD 2025 survey (SAP Labs):** "Evaluation and Benchmarking of LLM Agents: A Survey" (arXiv:2507.21504) — "LLM evaluation is like examining the performance of an engine. In contrast, agent evaluation assesses a car's performance comprehensively, as well as under various driving conditions." Distinguishes evaluation objectives (agent behavior, capabilities, reliability, safety) from evaluation process (datasets, metrics, tooling). — [arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **Anthropic Engineering:** "Code execution with MCP: Building more efficient agents" (Nov 2025) — Documents token-cost reduction by presenting MCP servers as code APIs rather than direct tool calls, enabling agents to write code that calls tools instead of passing all tool definitions through the context window. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

## Gotchas

- **The orchestrator becomes a single point of failure.** If your coordinator agent degrades, the entire multi-agent system stops. Design for coordinator redundancy and graceful degradation (fallback to direct routing) before going to production.
- **Adding agents doesn't linearly increase capability.** The coordination overhead — shared state management, message sequencing, output synthesis — grows superlinearly with agent count. The 40% failure rate in multi-agent pilots is often traced to teams scaling from 2 to 5 agents without redesigning the coordination layer.
- **Memory benchmarks measure the wrong thing.** Letta's research showed Letta agents running on `gpt-4o-mini` achieved 74.0% accuracy on LoCoMo retrieval benchmarks using only basic filesystem storage — no specialized vector store or memory library. This means the bottleneck is often agent capability and context management, not the retrieval infrastructure.
- **Agent-level evaluation requires trajectory tracing, not prompt-response scoring.** Single-turn benchmarks (SWE-bench, MMLU) don't capture the multi-step failures that dominate production: wrong tool selection, state drift over long tasks, cascading error recovery. Build eval pipelines that record full execution traces and measure cumulative outcomes.
