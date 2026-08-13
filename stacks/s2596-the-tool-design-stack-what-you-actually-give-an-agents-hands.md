# S-2596 · The Tool Design Stack — What You Actually Give an Agent's Hands

You built a clever agent. You gave it "access to your data." It hallucinated its way through three API calls, landed on the wrong resource, and deleted the wrong thing. The problem is not the agent. The problem is the tool. Tools are not just functions — they are contracts between deterministic systems and non-deterministic agents. Getting that contract wrong is how agents fail at the part where they touch the real world.

## Forces

- **Agents don't know what tools do, only what they say they do.** Unlike a developer reading API docs, an agent operates on description text. If the description is vague, the agent guesses. Wrong guesses cost real money and real data.
- **More tools don't mean more capability.** Every tool added to an agent's context is a new way to fail, a new token overhead, and a new decision the agent has to make. The MCP Python SDK has been downloaded 9+ million times — teams are building hundreds of tool integrations, and most are mediocre.
- **Token overhead is the invisible tax on tool-rich agents.** Anthropic measured agents consuming 10,000+ tokens reading tool definitions before a single user request is processed. At scale, this is the difference between a $0.02 and a $2.00 interaction.
- **A tool that returns too much is as bad as a tool that returns nothing.** Raw API responses flood the context window. The agent can't process everything, so it processes what it can and ignores the rest — often the part that mattered.
- **Sandboxing vs. capability is a real tension.** Giving an agent shell access makes it powerful. It also makes it dangerous. Llama.cpp's `llama-server --tools all` ships with an explicit "do not enable in untrusted environments" warning.

## The Move

Design tools for an agent that doesn't understand your system — only your description of it. The core principles:

- **Narrow, single-purpose tools beat broad, multi-purpose ones.** `get_customer_by_id(id)` beats `search_database(query)`. The narrower the scope, the fewer the ways the agent can go wrong. Anthropic's engineering guidance: each tool should do one thing, and the description should say exactly what it does.
- **Write descriptions in active voice, from the agent's perspective.** "Returns the last 10 error logs from the specified server" is better than "Query the logging service." Describe inputs, outputs, and side effects explicitly.
- **Filter results before returning them.** Don't hand the agent a raw API dump. Return only the top N results, the last 24 hours, the fields that are relevant. Anthropic's MCP code execution pattern: agents write code that calls tools and filters the results in-code, rather than receiving unfiltered streams. This can cut token overhead by 98.7%.
- **Use MCP as the tool exposure layer, not hardcoded integrations.** MCP standardizes tool discovery and invocation across any client. One MCP implementation connects to Claude Code, Cursor, Cline, and any custom agent — without rewriting integrations per client.
- **Make tool selection obvious with distinct names and examples.** When two tools do similar things (`create_ticket` vs. `create_incident`), add usage examples in the description so the agent can tell them apart. Anthropic's "Tool Use Examples" feature exists because distinguishing similar tools is a real failure mode.
- **Implement tool-level permission boundaries, not just app-level.** Not every agent in a system needs every tool. MCP's architecture lets you scope permissions per agent: one agent gets read-only database access, another gets write access with audit logging.

## Evidence

- **Engineering Blog:** Anthropic's "Writing Effective Tools for AI Agents" (Sep 2025) — describes the tool-as-contract model, the evaluation-driven tool design process (prototype → evaluate → let Claude optimize its own tool usage → repeat), and the three-layer tool use stack: tool definitions, tool use examples, and code execution. — [URL](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **Engineering Blog:** Anthropic's "Code Execution with MCP" (Nov 2025) — measured 10,000+ token overhead from loading all tool definitions upfront; demonstrated the code-as-API pattern reduces this by 98.7% by presenting MCP servers as callable code rather than direct tool calls. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **HN Discussion:** "I've built 12+ production AI agent systems across development, DevOps, and data operations" — practitioner thread on r/LocalLLaMA and HN discussing the permission-boundary problem: local builders consistently report that limiting filesystem and command permissions is what makes local agents useful rather than dangerous. — [URL](https://news.ycombinator.com/item?id=44623207)
- **Community Post:** Local AI Community Pulse (Jul 2026) — documented the shift from "prompt-based constraints" to "executable checks": "A prompt saying 'do not touch unrelated files' is a preference. A diff check that fails when unrelated files change is a constraint." — [URL](https://www.local-llm.net/blog/local-ai-community-pulse-july-2026)
- **ArXiv Survey:** "A Survey of Agent Interoperability Protocols" (2025) — cross-referenced MCP, ACP, A2A, and ANP; found MCP leads in production adoption for tool exposure due to its simplicity and broad SDK support (TypeScript SDK: 6.7M downloads, Python SDK: 9M+ downloads). — [URL](https://arxiv.org/html/2505.02279v2)

## Gotchas

- **Vague descriptions create specific failures.** "Query the database" tells the agent nothing useful. The agent will guess at the query language, the table names, the filtering logic. Write descriptions as if writing for a developer who has never seen your codebase — because that is exactly who you're writing for.
- **Unfiltered results are the most common token budget killer.** A `search_all()` tool that returns 500 rows will eat your context and your money. Always add pagination, filtering, and field selection at the tool level, not by asking the agent to filter downstream.
- **Tool name collisions break agents silently.** If two MCP servers expose a tool with the same name, the agent may call the wrong one. Namespace tools by domain: `drive_get_document` not `get_document`.
- **Agents call tools that shouldn't be called.** Without a circuit breaker or permission layer, an agent in a loop will hammer rate-limited APIs, attempt writes on read-only resources, or call destructive tools in the wrong context. Every tool should declare its risk level in its description and be gated accordingly.
- **Over-trusting `read_file` and `exec` tools in sandboxed environments.** Llama.cpp ships `--tools all` with explicit warnings about untrusted environments. If your agent runs on user input, the tool boundary is your security perimeter — design it like one.
