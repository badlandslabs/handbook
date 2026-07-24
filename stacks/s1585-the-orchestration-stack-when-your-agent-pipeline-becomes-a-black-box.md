# S-1585 · The Orchestration Stack — When Your Agent Pipeline Becomes a Black Box

You have a multi-step agent. It chains LLM calls, calls tools, and makes decisions. Somewhere between step 3 and step 15, it starts producing garbage. Nobody can trace where it went wrong — or whether it went wrong at all.

## Forces

- **Flexibility vs. control** — agentic loops (LLM decides the next step) are powerful but unpredictable; chains are predictable but rigid
- **Routing overhead vs. autonomy** — every routing decision is an LLM call before any real work starts, and that compounds fast
- **Context is a budget** — state accumulation across turns fills context windows with stale results that degrade decisions
- **The framework seduction** — orchestration frameworks promise simplicity but add their own failure modes; 89% of teams that ship LangChain to production ignore the official agent patterns anyway
- **Iteration without limit** — demos show elegant loops; production shows $180 requests after 47 iterations with no guardrails

## The Move

**Start at the bottom of the complexity ladder. Move up only when simpler patterns genuinely fail.**

The six orchestration patterns, ordered by production prevalence and complexity:

1. **Sequential Chain** — Model A output feeds Model B input. Use for: extract → classify → format; summarize → validate → store.
2. **Router / Classifier** — A classifier step directs the request to a specialized handler. Use for: intent classification, triage, routing between known paths.
3. **Agent Loop (ReAct)** — LLM decides next action in a think→act→observe cycle. Use for: open-ended exploration where the solution path is genuinely unknown.
4. **Plan-and-Execute** — A planner decomposes the task, an executor runs steps, results feed back to the planner. Use for: complex tasks requiring sub-task planning before execution.
5. **Supervisor-Worker** — A supervisor agent routes to specialized workers, monitors progress, synthesizes results. Workers are subgraphs with their own prompts and tools.
6. **Multi-Agent Peer Debate** — Agents propose solutions, critique each other, iterate toward consensus. Use for: high-stakes decisions requiring adversarial reasoning.

**For supervisor-worker patterns, enforce three guards from day one:**
- Iteration limits (hard cap before any routing loop starts)
- Per-request budget caps
- Explicit state checkpointing (LangGraph's Checkpointing API, 2026)

**For simple chains, enforce three boundaries:**
- Error handling at every step boundary (not just at the end)
- Explicit state passed between steps (not implicit context)
- Observability: what happened at every stage, not just the final output

## Evidence

- **Production LangChain survey (10,000+ deployments, 2025):** 89% of successful production LangChain apps ignore the official LangChain agent patterns entirely. Teams using chains + manual orchestration reach production in 2.1 months on average vs. 8.3 months for teams using official LangChain patterns. The three patterns that dominate in reality: chains (34%), routers (29%), and agent loops (28%). Multi-agent systems represent under 9%. — [Reddit r/LangChain / analysis by Nipurn_1234](https://www.reddit.com/r/LangChain/comments/1mjq5sm/i_reverseengineered_langchains_actual_usage/)

- **LangGraph supervisor production analysis (2026):** Multi-agent demos break predictably in production: full LLM call before every routing decision (cost), state accumulation bloat by iteration 15, no iteration guards, and silent tool failures. Real cost example: $180 on a single user request after 47 supervisor iterations — [BuildMVPFast](https://www.buildmvpfast.com/blog/langgraph-supervisor-deep-agents-multi-agent-patterns-2026)

- **Agentic AI workflow overview (April 2026):** LangGraph's idiomatic supervisor pattern encodes orchestrator-worker as a state graph rather than ad-hoc prompts. A supervisor node reads accumulated state, routes to named worker subgraphs, and loops until a termination condition — explicit, debuggable, checkpointable. The pattern works when: tool selection paralysis (>10 tools), context explosion from mixed concerns, and debuggability requirements exceed what a single agent prompt can deliver. — [DevStarSJ](https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability/) + [Easton Dev](https://eastondev.com/blog/en/posts/ai/20260512-langgraph-multi-agent-supervisor)

- **Production AI agent loop analysis (June 2026):** "Most teams can build a loop in an afternoon. Making it reliable at scale takes weeks." The reliable loop requires: permissions, verification, context management, and stop rules — the four wrappers that turn a demo agent into production infrastructure. — [Lightrains](https://lightrains.com/blogs/production-ai-agent-loops-engineering)

- **LangGraph market data (Q1 2026):** LangGraph (stateful graph-based orchestration) powers ~41% of new enterprise agent projects tracked by a16z. CrewAI wins on speed-to-first-agent (2–3 week average pilot time). AutoGen wins on multi-agent collaboration where the solution path is unknown at design time. — [Iterathon](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026)

## Gotchas

- **Tool selection paralysis** — with >10 tools, even frontier models degrade at choosing the right one. The fix is a router step before the agent, not more agent prompting.
- **Context window as a leaky bucket** — every intermediate result in a multi-agent pipeline consumes tokens and degrades downstream decisions. Prune or compress state at each handoff boundary, not just at the end.
- **Silent tool failures are the most dangerous failure mode** — API timeouts cause agents to hallucinate plausible-but-wrong results. Wrap every tool call with explicit success/failure signals; never let a tool failure pass as a success.
- **Supervisor routing is not free** — every routing decision is a full LLM call before any worker starts. Budget for it; don't let it surprise you in production cost analysis.
- **Most teams over-engineer the orchestration on first build** — "Start with the simplest pattern that could work. Most teams over-engineer with agents when a chain would do." (Harrison Chase, LangChain, paraphrased from community discussion)
