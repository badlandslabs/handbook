# S-2495 · The Supervisor Agent Stack — When One Agent Is Trying to Do Everything and Doing Nothing Well

When your agent gets slow, inaccurate, or unreliable on complex tasks — and the reflex is to add more tools or longer prompts instead of more agents.

## Forces

- A single agent handling research + writing + review produces mediocre output at every step instead of excellent output at one
- Context window pressure tempts you to truncate, but truncation kills quality on long tasks
- Adding tools to one agent creates routing ambiguity — the agent doesn't know which tool to trust
- A monolithic agent is opaque — you can't inspect *why* it chose a path or intervene cleanly
- Multi-agent sounds expensive, but single-agent retry loops on complex tasks are often more expensive

## The Move

The **supervisor agent pattern**: one coordinator breaks down the task, delegates to specialized workers, aggregates results, and handles routing. Workers are narrow, testable, and stateless between calls. The supervisor owns global state.

**The five production patterns** (explainx.ai, 2026):

1. **Orchestrator/Worker** — Supervisor decomposes task, assigns to workers, synthesizes output. Best for complex, non-linear tasks.
2. **Pipeline** — Sequential handoff: A → B → C → D. Each agent adds a transformation. Best for linear workflows (research → write → edit → publish).
3. **Fan-out/Fan-in** — One task splits to N parallel agents, results merge. Best for independent parallel work (scrape N URLs, query N DBs).
4. **Debate** — Two+ agents argue positions, a judge resolves. Best for high-stakes decisions requiring adversarial verification.
5. **Routing** — A router agent classifies input and dispatches to the right specialist. Best for high-volume, heterogeneous requests.

**Implementation mechanics** (LangGraph, OpenAI Agents SDK, Claude Agent SDK):
- Supervisor holds a shared state object; workers read from and write to it
- Conditional edges route based on output type, confidence, or task class
- Human-in-the-loop middleware pauses on high-stakes actions (refunds, emails, writes)
- Async execution enables parallel fan-out within the supervisor graph
- Middleware stack handles PII redaction, context summarization, and rate limiting

**Tiered model strategy** (common in 2026 production):
- Fast/cheap model for routing and classification decisions
- Capable model for specialized workers (research, writing, code)
- Frontier model for synthesis and judgment

## Evidence

- **Databricks engineering blog:** BASF Coatings deployed a supervisor agent system (Marketmind) coordinating specialized agents for structured and unstructured enterprise data across 11,000 employees and 70+ global sites. Problem: too many tools → poor routing; context growth → quality degradation. Solution: supervisor owns routing, workers own execution, shared state for observability. — [databricks.com/blog/multi-agent-supervisor-architecture](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

- **LangChain customer case studies:** LinkedIn built a multi-agent SQL bot on LangGraph — agents for table discovery, SQL generation, self-correction, and access enforcement — serving hundreds of employees with a 95% query accuracy satisfaction rate. AppFolio built a property management copilot that saved property managers 10+ hours/week and achieved 2x improvement in decision accuracy. — [langchain.com/blog/is-langgraph-used-in-production](https://www.langchain.com/blog/is-langgraph-used-in-production) + [agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/08/langgraph-fortune-500-production-stateful-multi-agent-workflows)

- **Hacker News / production deployments:** Optio (Show HN, 88 points) runs AI coding agents as Kubernetes pods — a supervisor manages the ticket-to-PR workflow across repos using Claude Code or Codex, with BullMQ job queuing and self-healing on CI failures. — [news.ycombinator.com/item?id=47520220](https://news.ycombinator.com/item?id=47520220)

- **SDK landscape:** Gartner reported a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. Six SDKs dominate 2026 production: LangGraph (state machine graph, 14K+ GitHub stars), CrewAI (role-based teams, 52K+ stars), OpenAI Agents SDK (sandbox execution), Claude Agent SDK, Google ADK, Microsoft Semantic Kernel. — [requesty.ai](https://www.requesty.ai/blog/best-ai-agent-sdks-compared-2026-langchain-crewai-openai-anthropic-google)

## Gotchas

- **The "many agents, one boss" antipattern:** simply chaining three agents behind a supervisor with no shared state is just three sequential LLM calls with extra latency — workers must write to a state object the supervisor can read and route on
- **Supervisor becomes the bottleneck:** if the coordinator does meaningful work itself rather than pure routing, it becomes the slowest, most error-prone part — keep supervisors dumb and workers smart
- **Human oversight is not optional for high-stakes actions:** every production supervisor stack needs interrupt points for refunds, emails, external API writes, and data modifications — retrofitting this after the fact is painful
- **Fan-out without a merge strategy is a common mistake:** spawning 20 parallel agents is easy; designing the synthesis logic that actually combines contradictory outputs is the hard part that most tutorials skip
