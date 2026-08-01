# S-1968 · The Multi-Agent Handoff Stack — When One Agent Isn't Enough

You hit the wall with a single agent: context windows exhaust mid-task, reasoning flips between modes, parallel work waits serial, and debugging a 2,000-line prompt becomes archaeology.

## Forces

- **Context window is finite but tasks are not.** A single agent juggling research, coding, and review burns tokens and loses coherence.
- **Role confusion degrades quality.** When one agent must switch between "write code" and "judge code" in the same context, it conflates generation and evaluation.
- **DAGs beat chains.** Sequential pipelines have no recovery path — one step fails, the whole run collapses.
- **Frameworks have diverged philosophies.** LangGraph, CrewAI, AutoGen, and Google's ADK each answer "who runs next?" differently, and the abstraction you choose shapes what you can and can't do.
- **Multi-agent costs 4–15× a single agent.** Orchestration overhead is real; parallelism only pays if the work is embarrassingly separable.

## The Move

Split work across specialized agents with defined roles, explicit handoff protocols, and a graph-based orchestration layer. The orchestrator answers four runtime questions: who runs next, what do they see, how is progress saved, and when do we stop.

- **Supervisor pattern:** One orchestrator agent routes tasks to specialized workers and aggregates results. Best for dynamic, unpredictable task flows where the supervisor must decide at runtime.
- **Sequential pipeline:** Fixed order (research → draft → review → publish). Best when task order is known and each step's output feeds the next cleanly.
- **Parallel crew:** Multiple agents work simultaneously on sub-tasks, then a synthesizer merges results. Best when work is embarrassingly separable and latency matters.
- **Stateful loops with checkpointing:** The agent retries, revises, or escalates based on output quality. Checkpoints survive infrastructure failures. Native to LangGraph; achievable in others with explicit state management.
- **Tool interface standardization:** Use MCP (Model Context Protocol) to define tool schemas consistently. Avoids per-agent tool redefinition and enables tool sharing across the graph.
- **Budget and token governance:** Set per-agent token caps, aggregate cost budgets, and fail-fast on overrun. CloudZero data shows agents use ~4× tokens vs. chat; multi-agent ~15×.

## Evidence

- **MMC Ventures founder survey (30+ agentic AI startups):** The #1 deployment challenge cited was *not* technical — it was organizational. Getting agents to collaborate reliably in production requires role clarity, escalation paths, and human oversight checkpoints. — [https://mmc.vc/research/state-of-agentic-ai-founders-edition/](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)
- **Imperialis Tech production post-mortem (March 2026):** Multi-agent frameworks (LangGraph, CrewAI, AutoGen) each hit predictable failure modes in production: LangGraph requires explicit state management but gives full control; CrewAI's team abstraction hides complexity but limits customization; AutoGen's conversational pattern creates governance gaps. Standard LangChain chains collapse entirely on single-step failure with no recovery path. — [https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production](https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production)
- **NIST AISIC workshop (~140 experts, August 2025):** No standardized taxonomy existed for describing tool capabilities across agent systems. The consortium identified 7 structural approaches to tool taxonomy, highlighting that "tool use" in agents is far more diverse than simple function calls — spanning web browsers, code interpreters, database queries, and file system operations with fundamentally different trust and risk profiles. — [https://www.nist.gov/news-events/news/2025/08/lessons-learned-consortium-tool-use-agent-systems](https://www.nist.gov/news-events/news/2025/08/lessons-learned-consortium-tool-use-agent-systems)

## Gotchas

- **Don't go multi-agent prematurely.** If a single agent with better prompting solves your problem, multi-agent adds orchestration overhead, cost, and debugging complexity for no gain. The break-even is when a task has genuinely separable cognitive modes (research vs. write vs. review) or when you need parallelism for latency.
- **Handoffs leak context.** Each agent-to-agent handoff re-passes context. Without explicit summarization or compression at each handoff boundary, you will exhaust the context window in 3-4 steps. Architect compression into the handoff contract.
- **"Who decides who runs next" is the hardest design decision.** In supervisor模式 it's the orchestrator (clean but creates a bottleneck). In peer-to-peer it's emergent (flexible but hard to audit). Pick based on your governance requirements, not your demo's simplicity.
- **Monitoring breaks at the agent boundary.** Standard LLM observability gives you one trace per agent. Multi-agent systems produce interleaved traces where one agent's timeout is another's tool call. You need trace correlation IDs flowing through the handoff protocol, not just per-agent logging.
