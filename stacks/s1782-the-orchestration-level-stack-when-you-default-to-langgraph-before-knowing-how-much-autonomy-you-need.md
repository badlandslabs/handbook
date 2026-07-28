# S-1782 · The Orchestration Level Stack

When you start with LangGraph because everyone uses LangGraph — before you've answered whether your agent needs full autonomy or a well-defined path. The real architectural decision is not which framework to use; it's where to place your system on the spectrum from deterministic code path to fully self-directing agent. Teams that skip that question ship fragile systems either way.

## Forces

- **Agents fail non-linearly** — a bad decision at step 3 of a 12-step autonomous flow propagates forward in ways a predefined workflow never could, making every step's failure surface area larger
- **Framework choice flows from autonomy level** — LangGraph's state graph is the right tool for complex, auditable workflows; it is the wrong tool for a simple three-step pipeline; CrewAI is built for rapid multi-agent prototyping but production-hardening it costs more than starting in LangGraph
- **AutoGen's v0.4 redesign (Jan 2025) and Microsoft's Agent Framework (Oct 2025)** signal convergence toward async, event-driven multi-agent architectures, raising the bar for what "production-ready" means

## The move

Map your task to the right orchestration level before touching any framework:

1. **Deterministic code path** — If the steps are known and bounded, write Python functions. No LLM call needed for routing logic.
2. **Prompt chaining (workflow)** — LLM calls in sequence, each feeding into the next. Use LangChain Expression Language or direct API calls.
3. **Routing (workflow)** — A classifier or rule engine dispatches to the right handler. Lowest token cost, highest predictability.
4. **Parallelization (workflow)** — Independent subtasks run concurrently, results merged. Use this before going multi-agent.
5. **Multi-agent with defined roles** — CrewAI or AutoGen two-agent setup covers ~60% of production cases. Role definition is the hard part, not the framework.
6. **State graph for complex flows** — LangGraph when you need full trace visibility, conditional branching, checkpointing, and the ability to replay execution from any node. ~400 lines vs ~120 in CrewAI for the same triage agent.
7. **Fully autonomous agent** — Only when the task genuinely cannot be decomposed and the failure cost is acceptable. Anthropic recommends this last.

Frameworks to match: CrewAI for speed-to-prototype (2–4 hours), LangGraph for production auditability (1–2 days), AutoGen for enterprise multi-agent conversations. None of them wins for non-technical users — use no-code platforms instead.

## Evidence

- **Anthropic Engineering Blog:** "The most successful implementations use simple, composable patterns rather than complex frameworks." Their recommended decision sequence: start with prompts + deterministic logic, add retrieval when needed, only reach for agents when the task genuinely requires dynamic tool use and long-horizon planning. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN Thread (543 points):** Practitioners debated the Anthropic post on HN. Key counterpoint: "An agent is nothing more than a very limited workflow. Modern workflow engines are very dynamic." — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **LangChain Blog:** Uber (code migrations), LinkedIn (recruiter agent), and Replit use LangGraph in production specifically for trace visibility and checkpointing. AppFolio's property management copilot saved over 10 hours/week and achieved 2x accuracy in decisions. — [langchain.com/blog/is-langgraph-used-in-production](https://www.langchain.com/blog/is-langgraph-used-in-production)
- **Qodo.ai / HN Discussion:** Team chose LangGraph for their coding agent because "the graph abstraction is a very useful mental model for thinking about an agentic flow." HN commenter: "For what LangChain does, most of the time I see no need for any framework." — [news.ycombinator.com/item?id=43468435](https://news.ycombinator.com/item?id=43468435)
- **Second Talent / Enterprise Research:** AutoGen v0.4 (Jan 2025) redesign: async event-driven architecture. ~60% of production AutoGen deployments use two agents. Token cost multiplier is 3–5x without controls; 50–70% savings with optimized sub-agent selection. — [secondtalent.com/resources/how-enterprises-are-using-autogen](https://www.secondtalent.com/resources/how-enterprises-are-using-autogen/)
- **Statewright (Show HN, 126 points):** Uses formal state machines to constrain agent behavior — "What if I made the problem smaller instead of making the model bigger?" — [news.ycombinator.com/item?id=48108778](https://news.ycombinator.com/item?id=48108778)

## Gotchas

- **LangGraph is not LangChain** — the graph abstraction is genuinely useful; the surrounding LangChain ecosystem is widely criticized as leaky abstractions that add complexity without value. Pick and choose.
- **Multi-agent does not mean more reliable** — adding agents adds failure modes (miscommunication, role collision, token cost explosion). Two-agent setups cover most use cases; group chats (>3 agents) are under 15% of production deployments for a reason.
- **Checkpoint and replay are non-negotiable in production** — whether you use LangGraph's built-in checkpointing, Redis, or PostgreSQL, you need the ability to replay a failed execution from any node. Without it, debugging a multi-step agent is archaeology.
