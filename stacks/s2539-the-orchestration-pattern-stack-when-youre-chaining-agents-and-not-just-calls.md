# S-2539 · The Orchestration Pattern Stack — When You're Chaining Agents, Not Just Calls

When a single LLM call won't finish the job, the instinct is to add more LLM calls. Then more. Then more. Six months later you have a tangle of chained prompts that no one fully understands, and adding a new feature means threading a new call through a dozen existing ones. The orchestration pattern stack is the set of decisions that determine whether your multi-agent system is a well-governed team or a hallway of people yelling at each other.

## Forces

- **Chains are DAGs; agents need cycles** — The moment you need an agent to loop, retry, or pivot based on output, a linear chain breaks. You need state.
- **Distributed context beats one giant context** — Anthropic's internal evals show >90% performance improvement from multi-agent research over a single agent with the same total token budget, because reasoning spreads across independent context windows.
- **Cost compounds across agents** — A 4-agent orchestrator-worker workflow costs $5–8 per complex task. A single-agent with 5 LLM calls costs $0.10–0.50. The gap is 50–80x.
- **Untyped handoffs kill multi-agent workflows faster than anything else** — Every agent-to-agent boundary needs a validated schema with version numbering, or a subtle type mismatch silently corrupts the downstream agent's reasoning.
- **Most teams reach for orchestration too early** — A single `create_agent` with 3–5 well-scoped tools beats a three-node graph that re-implements the same loop with extra latency. LangGraph earns its keep only at branching, parallelism, or checkpoint complexity.

## The move

Anthropic's engineering team (Schluntz & Zhang) codified five canonical patterns, ranging from simplest to most complex. Choose the lowest-complexity pattern that fits your task shape.

**Five patterns, in order of increasing complexity:**

1. **Prompt chaining** — Decompose into a sequence; each LLM call feeds the next. Add programmatic gate checks between steps. Use when task is cleanly decomposable and you want to trade latency for accuracy. Example: generate → review → revise → format.

2. **Routing** — Classify input at the top and send it to a specialized subsequent step. The router is a single LLM call that decides; the downstream handlers are stateless. Use when your input types are distinct and have separate optimal paths. Example: intent classification → specialized handler.

3. **Parallelization** — Run independent sub-tasks simultaneously and aggregate results. Use when subtasks have no data dependencies. Example: simultaneous web search, document retrieval, and database query → synthesize.

4. **Orchestrator-worker** — A lead agent dynamically decomposes a complex task and coordinates specialized workers. The orchestrator plans, assigns, and synthesizes; workers operate in fresh context windows. Use when task decomposition is non-trivial and path-dependent — like research or analysis. This is Anthropic's own Research system pattern: 90%+ benchmark improvement over single-agent. Cost: ~15x tokens vs. standard chat.

5. **Evaluator-optimizer** — An agent generates output, a separate evaluator scores it against criteria, and generation loops until the score passes a threshold. Use when quality is non-negotiable and you can define evaluation criteria: code generation, summarization, regulatory compliance review.

**LangGraph's role:** Treats orchestration as a first-class **state machine** — nodes are functions (agents or tools), edges are transitions, state is explicit TypedDict. Checkpointing enables crash-safe resume. This is what separates it from CrewAI and raw LangChain: it handles the cycles, branching, and human-in-the-loop checkpoints that other frameworks approximate with chat history.

**Real-world architecture (PRISM-INSIGHT, Korean/US stock trading):** An orchestrator (`stock_analysis_orchestrator.py`) coordinates 13 specialized agents — Technical Analysis, Trading Flows, Financials, News Sentiment, Market Conditions, and others — each with distinct model assignments (GPT-4.1 for analysis, GPT-5 for trading decisions, Claude Sonnet for conversational). Agents communicate via Telegram alerts and SQLite storage with explicit schema versioning.

**The hierarchy rule:** The supervisor-worker (hierarchical) pattern — a single orchestrator with bounded, specialized workers — is the most reliable for production. Peer-to-peer and fully dynamic topologies have higher theoretical flexibility but create debugging nightmares.

## Evidence

- **Anthropic Engineering Blog:** Five canonical orchestration patterns codified by Schluntz & Zhang — prompt chaining, routing, parallelization, orchestrator-worker, evaluator-optimizer — with explicit guidance to start simple and graduate up. Production implementation in Anthropic's own Research system. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Anthropic Engineering Blog:** Multi-agent research system architecture (June 2025) — lead agent orchestrates parallel subagents in fresh contexts; >90% benchmark improvement over single-agent Opus 4; ~15x token cost vs. standard chat. Independent ByteByteGo and Colourful Codes analyses confirm these figures. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)

- **RaftLabs analysis (Gartner-sourced data):** 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025; 57% of organizations have agents in production; 89% have observability but only 52% have evals — revealing the eval gap. — [URL](https://www.raftlabs.com/blog/multi-agent-systems-guide)

- **GitHub / HN Show:** PRISM-INSIGHT — 13 specialized agents in orchestrator-worker topology for Korean/US stock analysis. Each agent has a defined role (Technical Analysis, News, Trading Flows, etc.) with explicit model assignments. Open-source, production-deployed. — [URL](https://github.com/dragon1086/prism-insight) — [HN URL](https://news.ycombinator.com/item?id=45946056)

## Gotchas

- **Unvalidated handoff schemas** — If the output schema from one agent changes, downstream agents silently misparse. Schema versioning at every agent boundary is not optional.
- **Ignoring the eval gap** — 89% observability / 52% evals means most teams can see what their agents are doing but can't tell if it's right. You need both. Without evals, orchestration complexity becomes unmanageable at scale.
- **Picking orchestration before needing it** — A 3-node LangGraph graph for what a single agent with 4 tools could handle adds latency, cost, and debugging surface area. Ship the simple version first; graduate when you hit a specific complexity wall.
- **Silent cost compounding** — A 4-agent workflow at $5–8/task sounds acceptable until you're running 10,000 tasks/day. Model economics before committing to architecture.
