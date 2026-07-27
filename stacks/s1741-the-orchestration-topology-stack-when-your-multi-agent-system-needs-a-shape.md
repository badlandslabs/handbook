# S1741 · The Orchestration Topology Stack

When your single-agent system hits context overflow, diluted specialization, or serial bottlenecks — and you reach for multi-agent — the first question is not "what framework?" but "what shape should this system take?"

## Forces

- **Specialization vs. coordination overhead** — splitting one agent into many creates new capabilities but demands an orchestration layer that doesn't exist in single-agent systems
- **Determinism vs. flexibility** — structured pipelines are reliable but brittle; peer-to-peer handoffs are flexible but hard to trace
- **Architecture choice vs. model choice** — research shows topology beats model selection: AdaptOrch experiments showed 12–23% gains from better orchestration alone, comparable to or exceeding gains from switching models
- **Framework hype vs. production reality** — one HN commenter put it plainly: "There's absolute 0 framework out there that's good enough for serious work"; teams build custom orchestration layers on top of frameworks or from scratch

## The move

Match your orchestration topology to your agent count, task dynamism, and fault-tolerance requirements. Three patterns handle ~80% of real-world cases:

**1. Supervisor (centralized coordinator) — 3–8 agents**
- A single supervisor node owns routing decisions and task delegation
- Workers are stateless specialists with typed input/output contracts
- Supervisor can be rule-based or a lightweight LLM (a smaller, faster model often suffices — it just routes, not executes)
- Best for: deterministic pipelines, structured handoffs, compliance review, document processing pipelines
- LangGraph `create_supervisor` implements this natively; OpenAI Agents SDK uses "handoffs" as a first-class primitive
- Gotcha: supervisor is a single point of failure — monitor it, log all routing decisions

**2. Swarm (peer-to-peer handoff) — 2–15 agents**
- Agents hand off directly to the next appropriate agent with no central coordinator
- Each agent decides who to call next based on its own context
- OpenAI deprecated Swarm in September 2025 and replaced it with the Agents SDK, but the pattern lives on in CrewAI and custom implementations
- Best for: customer service routing, dynamic conversational scenarios, cases where no single agent has complete context
- Gotcha: without centralized visibility, failures are hard to trace — instrument every handoff with a trace ID

**3. Hierarchical (multi-level management tree) — 10–50+ agents**
- Multiple supervisor layers: a root coordinator delegates to team leads, who delegate to specialists
- Natural fit for enterprise: BASF Coatings deployed this pattern via Databricks to unify cross-team AI agents with domain-specific data access permissions
- Best for: large-scale enterprise systems, multi-team collaboration, nested workflows with clear decomposition boundaries
- Gotcha: latency compounds with tree depth; each layer adds token and time overhead

**Cross-cutting practices that apply to all topologies:**
- Define a spec per agent: purpose, tools allowed, context scope, output schema, fallback behavior
- Instrument handoffs — log source agent, target agent, trigger reason, and output schema validation
- Add a fixer/recovery agent that patches one failed component without re-running the entire pipeline ("cheap recovery over expensive retries")
- Use typed interfaces between agents so a failing specialist doesn't corrupt shared state
- Start with 3 agents (supervisor + 2 specialists) before adding complexity; most teams over-architect on first build

## Evidence

- **Survey:** MDPI "LLM-Based Multi-Agent Orchestration: A Survey of Frameworks, Communication Protocols, and Emerging Patterns" — 2,500+ papers published in 2025 (3× from 2024); Gartner documented a 1,445% surge in multi-agent inquiries Q1 2024 → Q2 2025 — [MDPI Future Internet](https://www.mdpi.com/1999-5903/18/6/326)
- **Engineering blog:** Microsoft ISE documented a retail customer's evolution from modular monolith (single-router pattern) to full multi-agent microservices — the team's finding: "Without the orchestration layer, a multi-agent system collapses into a collection of independent programs that duplicate effort, contradict one another, or loop without termination" — [Microsoft ISE Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Enterprise case study:** BASF Coatings deployed supervisor-agent architecture on Databricks to unify cross-team collaboration across critical enterprise functions, managing architectural complexity of extended runtimes, complex routing, and knowledge asymmetry — [Databricks Blog](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **HN production thread:** "Ask HN: How are you orchestrating multi-agent AI workflows in production?" — practitioners reported using LangGraph (with custom orchestrators on top), CrewAI, AGNO, roll-your-own Node.js in V8 isolates, and agent-managed agents; consensus: "Building a multi-agent AI system is more about software engineering than AI engineering" — [Hacker News](https://news.ycombinator.com/item?id=47660705)
- **Benchmark insight:** "Pattern choice matters more than model capability. Smaller models with better coordination outperform larger models with worse coordination" — Thread Transfer analysis of ChatDev (33.3% correctness on programming tasks), AppWorld (86.7% failure on cross-app workflows), and logistics systems (27% throughput gains, 22% cost reduction from topology improvements) — [Thread Transfer](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)

## Gotchas

- **The "God Agent" anti-pattern** — splitting one agent into many without structural separation just moves the problem; each specialist needs its own purpose, tools, and scope definition
- **Token cost compounds** — every inter-agent handoff carries the cost of synthesizing context for the next agent; conversation-based coordination (e.g., GroupChat) burns tokens on turn-selection overhead that graph-based or sequential pipelines avoid
- **Failure isolation** — if one specialist fails in a tight coupling, it can corrupt shared state; use typed interfaces and sandboxed execution (Docker/micro-VMs) for untrusted agents
- **Supervisor as SPOF** — the supervisor node is a single point of failure in the most common topology; teams underinvest in monitoring it because it "just routes"
