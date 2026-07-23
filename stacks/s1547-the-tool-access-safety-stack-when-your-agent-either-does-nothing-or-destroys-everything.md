# S-1547 · The Tool Access Safety Stack — When Your Agent Either Does Nothing or Destroys Everything

The moment you give your agent real filesystem access or the ability to run CLI commands, you face a binary failure mode: either the sandbox is too tight and the agent is useless, or it's too loose and the agent corrupts state, deletes files, or escalates privileges in ways you didn't anticipate. The pattern that works in production is not "less access" — it is **structured access with resumable isolation and explicit boundaries**.

## Forces

- **Agents are unpredictable by design.** Unlike deterministic software, LLMs make non-deterministic decisions about when and how to use tools. You cannot audit every action at runtime; you must architect the environment so that mistakes are recoverable.
- **Token cost grows with tool surface area.** MCP clients that load all tool definitions into context upfront pay a massive tax — hundreds of tokens per tool, compounding with every call. This is not just a cost problem; it shapes which tool architectures are actually usable.
- **Real tools require real consequences.** A browser agent that can only read pages can't actually book flights or fill forms. A coding agent that can't write files can't refactor codebases. "Safe" tool access that removes all consequences is often no tool access at all.
- **Sessions must survive interruptions.** Production agents run for minutes to hours across complex tasks. If the agent process dies mid-task, you need resumable state — not a full restart from scratch.

## The move

**Layer 1 — Isolated execution environment.** Give agents a sandboxed workspace (a virtual filesystem backed by SQLite, a container, or a dedicated temp directory) that is surgically mapped to the resources they need. AgentFS exemplifies this: it provides filesystem isolation where the agent can read/write within a controlled scope, and the backing store is a SQLite file that can be inspected, rolled back, or audited. Real files stay untouched.

**Layer 2 — Resumable session state.** Serialize agent execution state (tool call history, intermediate outputs, current step) to durable storage between turns. This serves two purposes: the agent can resume after a crash, and operators can inspect, replay, or rollback a session. AgentFS stores session state alongside the isolated filesystem — the agent picks up exactly where it left off.

**Layer 3 — Tool interfaces as code, not tool calls.** Anthropic's November 2025 MCP blog demonstrated that writing code which calls tools is more token-efficient and more sandbox-friendly than direct tool-calling definitions. The agent generates code that imports and invokes MCP servers as APIs, keeping tool definitions out of the context window and running them inside an execution environment with its own scope. This fundamentally changes the power/safety tradeoff: the agent gets real tool execution, but inside a controlled code runner.

**Layer 4 — Principled capability mapping.** Map every tool to a specific capability with an explicit blast radius. Browser agents (Ghostd.io) use purpose-built browser profiles per task so a research agent cannot access a banking session. CLI agents get isolated toolchains (git, linter, compiler) without shell escape. The key is capability namespacing: a tool named `filesystem_read_project_files` is auditable in a way that a raw `bash` tool is not.

## Evidence

- **GitHub repo + HN discussion:** The Evolving Agents Framework (March 2025) uses a `SmartLibrary` with ChromaDB-backed semantic search to manage tool persistence and discovery, and a `SmartAgentBus` for capability routing between agents. The HN discussion notes that the framework builds on BeeAI rather than reinventing orchestration — a pattern of composability over monolithic frameworks. — [github.com/matiasmolinas/evolving-agents](https://github.com/matiasmolinas/evolving-agents), [news.ycombinator.com/item?id=43310963](https://news.ycombinator.com/item?id=43310963)

- **Engineering blog:** Anthropic's MCP code execution post (November 2025) shows that code generation + tool APIs scales better than direct tool calling as agent tool counts grow — loading 50 tool definitions into context costs ~5,000 tokens per turn; writing code that imports the MCP SDK costs ~200 tokens. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **Product + security context:** AgentFS (from Turso, 2025) implements resumable, isolated filesystem access backed by SQLite, explicitly addressing the "agents need power but access is risky" tradeoff. The AutoJack attack (Microsoft, June 2026) demonstrates what happens when browser agents reach privileged local services without isolation — a single malicious webpage can redirect an agent into spawning arbitrary processes on the host. — [agentfs.ai](https://www.agentfs.ai/), [thehackernews.com/2026/06/autojack-attack](https://thehackernews.com/2026/06/autojack-attack-lets-one-web-page-hijack-ai-agent-for-host)

## Gotchas

- **Sandboxing that is too aggressive produces a useless agent.** If the isolated workspace cannot access the actual files or tools the task requires, the agent will fail silently or hallucinate solutions that don't work in the real environment. Validate that the sandbox maps to the actual resource topology (project files, databases, APIs) before deploying.
- **Resumable state is not the same as idempotent state.** If an agent's tool calls have side effects (writes, API calls, deployments), replaying a session can produce duplicate or conflicting effects. Checkpoint the state *before* each side-effecting call, not after.
- **Tool definition overload is a silent cost.** Teams often don't discover the token tax of large tool sets until production costs spike. Measure context window usage per task type and switch to code-as-tool patterns before the context window becomes the bottleneck.
