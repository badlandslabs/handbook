# S-722 · The Five-Framework Landscape: Where the Winners Diverged

[Choosing an orchestration framework is not a tooling decision — it's an architectural commitment that shapes observability, failure modes, and your ability to evolve. The 2026 landscape has narrowed to five real choices, each mapped to a fundamentally different bet about where agent complexity belongs.]

## Forces

- **LangGraph, CrewAI, AutoGen/AG2, OpenAI Agents SDK, and Google ADK** now dominate — but they solve different problems. Teams that pick based on popularity rather than fit end up retrofitting the wrong abstraction.
- **AutoGen entered maintenance mode October 2025** — its successor is AG2, but migration isn't trivial. Teams on AutoGen face a forced decision.
- **CrewAI trades explicitness for speed** — role-based crews are fast to scaffold but collapse under dynamic rerouting. LangGraph's state machines are verbose but debuggable.
- **The demo works, production doesn't** — the 30% gap (The AI Vibe) between controlled test and production is not a model problem; it's an orchestration problem. Framework choice determines whether you can even instrument that gap.
- **Context is the defensible layer** — not the model, not the framework. Teams that pick frameworks and ignore memory architecture are building on sand.

## The move

**Map the choice to your failure mode, not your happy path.**

- **Use LangGraph** when you need durable execution, checkpointing, and production-grade observability. Best for systems where mid-run failures must be resumable and traceable. Used in production at Klarna, Replit, and Elastic. (Source: JetThoughts framework comparison)
- **Use CrewAI** when you have pre-defined agent roles that collaborate on structured pipelines (marketing agency, support triage, content workflows). Falls apart when tasks require dynamic re-routing. (Source: HN Show HN: Opensoul post)
- **Use AutoGen/AG2** only if already invested — the migration to AG2 is the canonical path forward. Microsoft's stated direction is the Agent Framework successor. Do not start greenfield on AutoGen. (Source: JetThoughts)
- **Use OpenAI Agents SDK** when you are all-in on OpenAI and want minimal ceremony for single-agent or light multi-agent workflows. Not a fit for complex state machines or multi-provider setups.
- **Use Google ADK** when your stack is GCP-native and you need tight integration with Vertex AI, Gemini, and Google Workspace tools.
- **Consider custom state machines** (Temporal, direct graph implementations) when the task is workflow-shaped (clear steps, explicit transitions) rather than agent-shaped (emergent, exploratory). The AI Vibe's data: 30% of cases break in production when agents have too much freedom — constrained action spaces are not a framework concern, they're an architectural one.

**For multi-agent specifically**, four patterns cover most production cases (RaftLabs, 100+ deployments): hierarchical (one supervisor delegates), pipeline (sequential handoffs), orchestrator-worker (dynamic task decomposition, e.g., Anthropic's own Claude Research system), and peer-to-peer (equal agents negotiate). Anthropic's engineering post (June 2025) describes their orchestrator-worker approach explicitly: parallel subagents explore separate aspects, the lead synthesizes. This pattern works for open-ended research. It breaks for tasks requiring strict handoff semantics.

## Evidence

- **Engineering blog:** Anthropic published a detailed post on how Claude Research uses an orchestrator-worker multi-agent architecture with parallel subagents operating in separate context windows. Subagents compress and explore independently; the orchestrator synthesizes findings. — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/built-multi-agent-research-system)
- **Framework comparison:** LangGraph (state machine, production-grade at Klarna/Replit/Elastic), CrewAI (role-based, fast delivery), AutoGen (maintenance mode since Oct 2025, successor is Microsoft Agent Framework/AG2). Each picked a different philosophy — none is universally superior. — [JetThoughts](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/)
- **HN field report:** An engineer built Opensoul (6-agent marketing agency) on Paperclip orchestration, documenting the crew/role model in production. Real agents: Director, Strategist, Creative, Producer, Growth Marketer, Analyst — each with autonomous heartbeat loops. — [Hacker News Show HN](https://news.ycombinator.com/item?id=47336615)
- **Production gap data:** One team documented 92% test success collapsing to 55% production success with 4x cost overrun. The breakdown is not model quality — it's action space constraints, observability, and error recovery. — [The AI Vibe](https://theaivibe.org/blog/building-production-ai-agents-lessons-2025)

## Gotchas

- **AutoGen without a migration plan is a liability.** AG2 is the successor but the API surface has changed. Budget time for it.
- **CrewAI's role model is a trap for dynamic tasks.** It works beautifully for marketing agencies and support pipelines. It fails for research, code generation, or anything that requires the agent to decide its own role at runtime.
- **LangGraph's explicitness tax is real.** You write more graph definition code upfront. Teams that want "5-line agent" simplicity and then reach for LangGraph end up frustrated.
- **Context management is your problem, not the framework's.** Every framework will happily route tokens through a 200K context window until your cost hits $50/task. Budget your memory architecture independently.
- **Sandboxing is its own layer.** HN discussion (Philipp Dubach, Feb 2026) flagged that the agent stack is stratifying — sandboxing (Shuru, E2B, Modal, Firecracker) is increasingly its own specialized concern, not something you bolt onto the framework.
