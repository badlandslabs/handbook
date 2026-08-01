# S-1970 · The Orchestration Stacking Stack · When You Reach for Multi-Agent Before You Need It

When your team spins up three LangGraph nodes, two CrewAI agents, and an orchestrator before writing a single line of business logic — because "that's what production agents look like" — and now debugging takes longer than the feature.

## Forces

- **Frameworks make demos fast but production hard** — CrewAI gets you a working prototype in an afternoon; LangGraph gets you a run you can resume after a Thursday deploy. Teams pick the wrong one for their stage.
- **Multi-agent adds latency and failure surface area** — every agent-to-agent handoff is a potential hallucination, a missed context transfer, or a contradictory output nobody catches until it reaches the user.
- **The orchestration pattern is not a free choice** — the right pattern depends on task structure (linear vs. branching vs. open-ended), whether you need resumability, and whether humans need to approve mid-flow. Picking the wrong one means fighting the framework.
- **The community swing** — after years of "just use LangChain," the consensus has flipped to "use the LLM API directly, add complexity only when you feel the pain." But that advice has its own failure mode: teams under-invest in observability and error recovery until they burn budget in production.

## The Move

Match the orchestration pattern to the actual task structure, not to how impressive the architecture looks.

**Decision tree (from Microsoft Azure Architecture Center, confirmed across HN discussion):**

1. **Single LLM call with crafted prompt** — sufficient for classification, summarization, translation, single-step tasks. This is the default. Start here.
2. **Single agent with tools** — one agent in a multi-step loop with tool/API access. The right default for enterprise. Use when queries vary within a single domain but the control flow is recoverable.
3. **Sequential workflow** — agents work one after another on a fixed pipeline. Use when each agent's output feeds the next, like content creation or staged data transformation.
4. **Supervisor/hierarchical pattern** — a central agent routes tasks to specialized workers. Use when task types are known upfront and a router can dispatch without dynamic decomposition.
5. **Orchestrator-Workers** — a central planner dynamically invents sub-tasks and spawns workers at runtime. Use when you cannot enumerate sub-tasks ahead of time and the orchestrator must figure out what needs doing based on the input.
6. **Collaborative/Magentic pattern** — agents debate and refine a plan before execution. Use when diverse expert perspectives improve the solution and you need a verifiable reasoning ledger. Avoid when speed matters or the path is deterministic.

**Three patterns that survive production (per LangChain's 2025 production survey, corroborated by r/LangChain community):**
- Simple chains for linear workflows
- Router patterns for task classification  
- Agent loops for open-ended problems

**Framework selection:**
| Criterion | LangGraph | CrewAI |
|---|---|---|
| Production reliability | ★★★★★ | ★★★ |
| Dev speed | ★★ | ★★★★★ |
| Observability | ★★★★★ | ★★ |
| Human-in-the-loop | ★★★★★ | ★★ |
| Best for | Complex state, branching, resumability | Fast PoC, role-based demos |

AutoGen is in maintenance mode (2026); Microsoft moved active development to Agent Framework.

## Evidence

- **Anthropic engineering post:** "The most successful implementations use simple, composable patterns rather than complex frameworks." Key distinction: **workflows** (predefined code paths) vs. **agents** (LLM dynamically directs its own process). Agents trade latency and cost for better task performance on open-ended problems. Start with optimizing single LLM calls before reaching for agents. — [Anthropic — Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Microsoft Azure Architecture Center:** Documented five orchestration patterns with complexity spectrum: direct model call → single agent with tools → multi-agent orchestration. Real-world example: an SRE team uses magentic/collaborative orchestration to handle site reliability incidents — multiple agents debate and synthesize a remediation plan dynamically, with a task ledger tracking progress. Avoid collaborative patterns when the path is deterministic or speed matters. — [Azure AI Agent Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- **Reddit r/LangChain community consensus (2026):** "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." Teams migrating from CrewAI to LangGraph cite need for branching logic, approval gates, and crash-safe resumability — not raw agent capability. Most teams over-engineer with multi-agent before they need it; a single `create_agent` with 3–5 well-scoped tools beats a three-node graph. — [Idea to MVP — LangGraph Orchestration Patterns](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)
- **LangChain production survey (2025):** Simple chains handle ~80% of production use cases, yet teams consistently over-engineer their first implementations. Multi-agent orchestration earns its keep when at least one of these is true: branching execution paths, crash-safe resumability, or human approval gates. — [ZenML Blog — LlamaIndex vs CrewAI](https://www.zenml.io/blog/llamaindex-vs-crewai)

## Gotchas

- **The "God Prompt" anti-pattern** — stuffing all business logic into one massive system prompt. It hallucinates under load and contradicts itself at scale. Break logic into modular chains where each agent has one role, one context, one toolset.
- **Agents without perception** — an agent that writes follow-up emails but cannot check the CRM to verify whether the lead already converted. Connect every action layer to a perception layer before execution.
- **No checkpoint, no resume** — multi-step chains fail silently between steps. LangGraph's checkpointing is the main reason teams migrate to it from simpler frameworks. Design for resumability from step one.
- **Token explosion in retries** — agent retries resend the full conversation context. Ten retries × 8,000 accumulated tokens = 80,000 tokens of zero productive work. Budget for this explicitly.
- **Framework longevity risk** — AutoGen moved to maintenance mode in 2026. CrewAI is less battle-tested at scale than LangGraph. Prefer patterns over frameworks where possible; abstract the agent runtime, not the orchestration logic.
