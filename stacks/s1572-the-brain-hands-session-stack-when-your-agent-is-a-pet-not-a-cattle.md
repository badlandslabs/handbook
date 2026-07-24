# S-1572 · The Brain-Hands-Session Stack — When Your Agent Is a Pet, Not a Cattle

The default agent architecture couples decision-making, execution, and state into one container. That container becomes a pet: it can't be restarted cleanly, can't be debugged without SSH, can't be replaced without losing context. As agents grow more autonomous and run longer, this coupling becomes the failure mode that blocks scaling.

## Forces

- **Harnesses encode model-specific assumptions that go stale** — fixes for Claude Sonnet 4.5's "context anxiety" became dead weight on Claude Opus 4.5, but the harness held them anyway
- **Coupling the brain to execution makes the container unreplaceable** — credentials, session state, tool access, and the LLM loop all live together; restart means context loss or worse
- **Security blast radius grows with autonomy** — the more capable the agent, the larger the potential damage if its execution environment is compromised
- **Long-horizon work demands crash recovery without starting over** — an 11-day task that crashes on day 10 is not resumable if state lives in volatile memory
- **Tool ecosystems are fragmented** — MCP servers, browser sandboxes, code execution, file I/O all require different runtime environments

## The Move

**Virtualize agent components into independently replaceable interfaces** — three layers that each fail in isolation and communicate through stable abstractions:

- **Session** (append-only event log) — the durable record of everything that happened. Survives restarts, migrations, harness swaps. Acts as the single source of truth for "where we are." Never mutates; only grows.
- **Brain** (Claude + harness) — the decision-making loop. Calls the model, routes tool calls, maintains the plan. Completely stateless regarding execution. If the brain dies, reload from session and pick up where you left off.
- **Hands** (sandbox + tools) — the execution environment. Browser, MCP server, code interpreter, filesystem access. Does not contain session or model logic. Swappable; can run on a different machine, a different cloud, or a different security boundary than the brain.

**Context builder pattern**: The session feeds only the *relevant* context window slices to the brain, not the full append-only log. The brain doesn't know or care where the context came from — only that it's correctly formed. This makes context window management someone else's job (the infrastructure), not the prompt's job.

**Security isolation via separate process boundaries**: Hands run in isolated sandbox processes, not inside the brain's container. A compromised MCP server can't reach the session log directly.

**Agentic containment**: As agents grow more capable, their blast radius grows. Containment enforces that the hands can only operate within defined boundaries regardless of what the brain decides to do.

## Evidence

- **Engineering Blog (Anthropic, Apr 2026):** "Scaling Managed Agents: Decoupling the brain from the hands" — documents the session/harness/sandbox separation for Claude Managed Agents, explicitly referencing the OS virtualization analogy (processes outlasted specific hardware). Harnesses that encoded Sonnet-4.5-specific fixes were replaced without touching the session or sandbox. — [anthropic.com/engineering/managed-agents](https://www.anthropic.com/engineering/managed-agents)
- **Engineering Blog (Anthropic, Apr 2026):** "How we contain Claude across products" — the containment postmortem shows that agent capability and blast radius grow together; the engineering answer is architectural isolation between decision-making and execution. — [anthropic.com/engineering](https://www.anthropic.com/engineering)
- **HN "Show HN: Plano" (Jan 2025):** An edge proxy for AI agent orchestration — reflects the broader industry movement toward separating orchestration (control plane) from tool execution (data plane), preventing the agent process from having direct network access to sensitive systems. — [news.ycombinator.com/item?id=46517177](https://news.ycombinator.com/item?id=46517177)
- **Enterprise survey (Cleanlab, 2025):** Of 1,837 surveyed engineering leaders, only 95 (5.2%) had AI agents live in production. 70% reported rebuilding their AI stack every 3 months — a symptom of the "pet server" problem at scale. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **The session log grows unbounded without compaction** — an append-only log for an 11-day agent will eventually exceed context limits. The context builder must handle summarization, eviction, or retrieval — this is non-trivial and often an afterthought
- **Harness versioning is invisible until it breaks** — a harness written for today's model may encode assumptions that tomorrow's model invalidates. Treat harnesses as versioned artifacts with regression tests
- **Sandbox isolation has real latency cost** — crossing process boundaries for tool calls adds milliseconds; for agents making hundreds of tool calls per task, this compounds
- **Session recovery is only as good as checkpoint granularity** — if you only checkpoint at the end of a task, you replay a lot of work on crash recovery; if you checkpoint too frequently, you slow execution and bloat the session log
