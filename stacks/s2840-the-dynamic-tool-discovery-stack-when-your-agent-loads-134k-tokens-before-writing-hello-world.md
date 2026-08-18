# S-2840 · The Dynamic Tool Discovery Stack

When your agent loads 134K tokens of tool definitions before it can say hello — and you finally do something about it.

## Forces

- **Tool proliferation taxes context windows** — a typical enterprise MCP setup with GitHub, Slack, Jira, Sentry, Grafana, and Splunk consumes 55K+ tokens in tool definitions alone before the agent has done any real work. Anthropic has observed 134K tokens consumed before any optimization.
- **Loading everything means reasoning about nothing** — agents that receive all tool definitions at once perform worse because relevant tools get lost in noise, and context space spent on definitions is context space not available for the actual task.
- **Static tool sets are brittle** — baking a fixed tool list into the prompt means your agent can't adapt to novel sub-tasks, new APIs, or one-off integrations it encounters mid-session.
- **Tool definitions drift** — as MCP servers evolve, stale tool schemas cause parameter errors that cascade into failure.

## The Move

Shift from **bulk tool loading** to **on-demand tool discovery**: give the agent a lightweight registry it can query at runtime, fetch only the tools relevant to the current sub-task, and cache what it learns about tool behavior across sessions.

### Specific techniques

- **Tool Search Tool** — Anthropic's beta pattern: a lightweight search tool that lets the agent query a registry of available MCP tools by intent. The agent describes what it needs ("I need to read a file from the repo"), the search returns matching tool definitions, and only those definitions enter context. Their implementation reduced tool-definition tokens by ~85%.
- **Programmatic Tool Calling** — instead of describing tool behavior in natural language and hoping the model infers the right call, pass tool invocations as structured code. Anthropic's beta achieved 37% token reduction and enabled parallel tool execution, since the orchestrator rather than the model controls sequencing.
- **Tool Use Examples** — provide the agent with a few-shot library of correct tool invocations (parameters, success outputs, failure modes) rather than only schema definitions. Anthropic reported parameter accuracy improved from 72% to 90% with examples.
- **Semantic tool routing** — on session start, the agent queries the registry with the user's high-level intent, gets back the top-K relevant tools, and ignores the rest. This is the pattern behind Archetypal AI's three MCP tools for Claude Code: a lightweight index queried at task start, not a firehose of every available tool.
- **Stale-definition guard** — cache tool schemas with a TTL and refresh on-demand. Before invoking a tool, the agent verifies the schema is current. This prevents parameter errors from schema drift without paying the cost of refreshing every call.

## Evidence

- **Anthropic Engineering Blog (Nov 2025):** Documented the 134K-token problem and introduced Tool Search Tool (85% token reduction) and Programmatic Tool Calling (37% token reduction, parallel execution). Tool Use Examples raised parameter accuracy from 72% → 90%. — https://www.anthropic.com/engineering/advanced-tool-use
- **GitHub — Evolving Agents Framework:** Implements semantic search over a tool/agent registry to dynamically determine whether to reuse, evolve, or create new agents based on task similarity — not load everything upfront. — https://github.com/matiasmolinas/evolving-agents
- **Archetypal AI (r/ClaudeAI, r/LocalLLaMA):** A civilization of 14 agents built a persistent memory system for Claude Code via three MCP tools that the agent queries selectively at session start, rather than pre-loading all context. Their design principle: "Every session that ends is a death. Your agent learns your codebase, and then the session closes and everything is destroyed." — https://gist.github.com/bsharvey/7cb4d57600408ba4f1bd9745bd688816
- **Ghostd.io (HN Show HN):** Browser workflow agent that decomposes tasks into sub-agents, each given only the tools relevant to their step — avoids loading every possible action upfront. — https://news.ycombinator.com/item?id=47322046

## Gotchas

- **Tool search itself consumes tokens** — every search call, even a lightweight one, adds round-trips. Measure whether the token savings from selective loading exceed the overhead of the search calls.
- **The registry becomes a single point of failure** — if the tool search tool gives wrong results, the agent may never discover the right tools. Include a fallback to bulk loading when search returns empty or low-confidence results.
- **Tool use examples drift faster than schemas** — examples are more expressive but harder to keep current. Treat them as a living layer that needs its own review cadence.
- **Parallel tool execution requires idempotency guarantees** — programmatic tool calling enables concurrency that static tool chains don't, but overlapping writes to shared state become a real failure mode.
- **Not all tools benefit from on-demand loading** — if a tool is used in every session (e.g., file system access), the cost of a registry lookup each time outweighs the savings. Cache tool definitions for high-frequency tools.
