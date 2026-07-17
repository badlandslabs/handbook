# S-1228 · The Orchestration Decision Stack — When Your Agent Pipeline Isn't a Pipeline

When you need multiple LLM calls, tools, or agents to cooperate on a task — and you keep debating whether to use a framework, build custom, or hard-code the flow.

## Forces

- **Frameworks abstract too much or not enough** — LangGraph is powerful but demands graph thinking; OpenAI Agents SDK is simple but graph-agnostic; rolling your own gives control but no guardrails
- **The workflow-vs-agent distinction is load-bearing** — workflows (predefined paths) are debuggable and cheap; agents (LLM-directed) are flexible and expensive; teams pick one and get surprised by the other
- **State爆炸** — every agent needs memory, but short-term vs. long-term vs. shared context are three different problems most frameworks conflate
- **No single framework dominates** — even teams using LangGraph often build a custom orchestrator on top; even OpenAI's own team deprecated their Assistants API for the leaner Agents SDK

## The Move

The production consensus from 2025–2026 primary sources: **start with the simplest orchestration that fits, and promote to more complex only when forced by evidence**.

**1. Use predefined workflows (prompt chaining, parallel calls) before reaching for full agents.** If your task is a sequence, encode it as a sequence. Anthropic's December 2024 research found that the most successful teams used simple composable patterns first, and only escalated to dynamically-directed agents when single-call approaches failed.

**2. Choose your orchestration primitive based on control vs. flexibility tradeoff:**

| Need | Approach | Framework Examples |
|---|---|---|
| Linear sequence of steps | Prompt chaining | Raw API calls, LangChain chains |
| Parallel independent tasks | Fan-out/fan-in | LangGraph, Pydantic AI |
| Dynamic routing to specialists | Handoffs | OpenAI Agents SDK, CrewAI |
| Long-running with checkpoints | Durable execution | LangGraph with checkpointing |
| Multi-agent with shared state | Graph-based | LangGraph, AG2/AutoGen |

**3. Use MCP (Model Context Protocol) for tool discovery and standardization.** Launched by Anthropic November 2024, adopted by OpenAI, Google, Microsoft, AWS within months. As of April 2025, MCP server downloads grew from ~100K to 8M+ with 5,800+ servers and 300+ clients. It solves the "tool registry" problem — agents discover capabilities at runtime rather than having them hard-coded.

**4. Handle multi-agent handoffs explicitly, not via shared context drift.** OpenSwarm (Show HN, ~34 points) uses a Worker → Reviewer → Test → Documenter pipeline with explicit handoff boundaries and LanceDB for shared memory. Practitioners on HN warn that context drift across agent chains is the #1 failure mode: each agent slightly misunderstands the task, and by the time the last agent validates, it's validating the wrong thing. LanceDB's structured embeddings are cited as the solution that grounds shared context.

**5. For stateful agents, separate short-term working memory from long-term persistent memory.** LangGraph (37k+ GitHub stars) treats these as distinct: `messages` accumulate within a thread (short-term, checkpointed), while a separate memory store handles cross-session context (long-term, namespace-keyed JSON). Practitioners building production agents consistently cite "stateless functions with no memory across sessions" as the #1 user experience failure.

**6. Checkpoint aggressively for durable execution.** LangGraph's checkpointing lets agents resume from mid-step on failure — critical for tasks that run overnight or across days (a use case cited in the Hive framework's construction-industry ERP work: "accountants want the ledger reconciled while they sleep, not a chatbot that forgets when the tab closes").

## Evidence

- **Anthropic Research:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." — [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents) (Dec 2024)
- **Hacker News discussion (Ask HN, 8 pts, 11 comments):** "There's absolutely 0 framework out there that's good enough for serious work." Multiple practitioners build custom orchestration on top of LangGraph or AGNO. Agents communicate via structured JSON through shared databases (MongoDB), not in-memory. — [HN Thread: Multi-Agent Workflow Orchestration in Production](https://news.ycombinator.com/item?id=47660705)
- **Show HN — OpenSwarm (34 pts):** Multi-agent Claude Code pipeline (Worker/Reviewer/Test/Documenter) with LanceDB long-term memory and Discord bot for status. Author notes cascading context drift across agent chains as the primary failure mode to prevent. — [HN Thread](https://news.ycombinator.com/item?id=47160980), [GitHub](https://github.com/Intrect-io/OpenSwarm)
- **GitHub — LangGraph README:** Trusted by Klarna, Replit, Elastic. Key differentiator: durable execution (persist through failures, auto-resume from checkpoint) + human-in-the-loop inspection. — [langgraph/README.md](https://github.com/langchain-ai/langgraph/blob/main/README.md)
- **BCG AI Platforms Group (April 2025):** MCP (Model Context Protocol) adopted by OpenAI, Google, Microsoft, AWS within 4 months of launch. 8M+ MCP server downloads by April 2025, 5,800+ servers, enterprise deployments at Block, Bloomberg, Amazon. — [BCG Briefing: AI Agents and the MCP](https://blog.infocruncher.com/resources/agents-1-rise-and-future-of-agents/AI%20Agents%2C%20and%20the%20MCP%20%28BCG%2C%202025%29.pdf)
- **Reddit r/LocalLLaMA (2y ago, 907K members):** "Langchain agents were complicated and over engineered... crewAI and Autogen felt vision-tunneled on some goals and hard to extend to other use cases, only tested against GPT-4." — [Thread: Any updates to the agents scene?](https://www.reddit.com/r/LocalLLaMA/comments/1d5hnqk/any_updates_to_the_agents_scene/)
- **Show HN — Hive Framework (107 pts):** Agent framework for construction ERP (PO/invoice reconciliation) using OODA loops instead of DAGs — "DAGs crash on failure, OODA adapts." Addresses the "toy app ceiling" where chatbots lose state on tab close and can't handle 2-week asynchronous business workflows. — [HN Thread](https://news.ycombinator.com/item?id=46979781), [GitHub](https://github.com/adenhq/hive)
- **Prompt Genius (2026):** OpenAI Agents SDK (19k+ stars) positions itself as batteries-included for simple multi-agent tasks with handoffs, guardrails, and tracing. Bad fit for graph-structured fan-out (use LangGraph) and tight token budgets (hard to inspect per-step costs). — [Architecture Deep-Dive](https://promptgenius.net/blog/openai-agents-sdk-architecture)

## Gotchas

- **Don't reach for agents before exhausting workflows.** The latency and cost premium is real. If a single LLM call with retrieval and in-context examples suffices, use that. Anthropic's research is explicit: "Start with the simplest solution possible."
- **Context drift compounds across agent chains.** Without explicit grounding (shared memory store, structured embeddings), each handoff loses signal. This is the failure mode practitioners on HN cite most often, and it's invisible until it isn't.
- **Framework lock-in is real even for "minimal" frameworks.** OpenAI deprecated the Assistants API in August 2026, forcing migration to the Agents SDK. Teams that built on LangGraph's lower-level primitives had easier migration paths than those who used higher-level abstractions.
- **Checkpointing has serialization costs.** LangGraph practitioners note that large `AgentState` objects slow down checkpoint/restore. Keep state lean; summarize long conversations rather than accumulating them.
