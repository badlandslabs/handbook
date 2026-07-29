# S-1840 · The On-Demand Tool Loading Stack — When Your MCP Catalog Is Eating Half Your Context Window

Your agent connects to five MCP servers. Each exposes 8–40 tools. Your context window is now 40% tool schemas, 30% history, and 30% actual work. Latency is up, cost is up, and the model starts hallucinating tool names because its attention is diluted across a schema forest. This is the **on-demand tool loading problem**: MCP solves tool discovery, but leaves tool delivery — when and how much to load — as an unsolved production concern.

## Forces

- **MCP's adoption is massive but its loading model is naive.** As of early 2026: 10,000+ active MCP servers, 97 million monthly SDK downloads (arXiv:2603.13417). The protocol standardizes tool discovery, not tool delivery — loading is "all or nothing" by default.
- **Context is finite and expensive.** Anthropic's Applied AI team identified context engineering as the top technical challenge in enterprise agent deployments (2025). Every tool schema in context is a token that doesn't carry task state.
- **Enterprise agents hit hundreds of tools.** Production agents connect to multiple MCP servers simultaneously. With 5 servers × 20 tools each, the model sees 100 tool definitions per turn. Quality degrades well before context overflows.
- **On-demand loading is an architectural shift, not a config change.** Solutions range from simple category-based filtering to full meta-tool hierarchies — but all require rethinking the client-side tool management layer.

## The move

**Load tool schemas progressively, not eagerly.** The agent starts with a lightweight tool index; full schemas load only when the agent signals intent.

**Three implementation patterns (from simplest to most sophisticated):**

- **Category pre-filtering.** Group tools into named categories. Send the agent a lightweight manifest of `{category: [tool_names]}` plus high-level descriptions. When the agent commits to a category, load that subset's full schemas. voicetreelab/lazy-mcp uses this with `get_tools_in_category(path)` as a meta-tool — the agent explicitly navigates the tool tree before executing. The repo's README reports **17% token savings** (34,000 tokens) on a single Claude Code session by hiding 2 of 50 tools that weren't needed.

- **On-demand schema loading with summary hints.** Rather than full JSON schemas, start with one-line capability summaries. Let the agent request the full schema for the tools it selects. Anthropic's engineering post on MCP code execution describes loading tools on demand to "filter data before it reaches the model, and execute complex logic in a single step" — the principle extends beyond code execution to any tool with large schemas.

- **Tool instruction pre-filtering (Anthropic pattern).** Process data at the tool layer before it reaches the model. Anthropic's code execution blog shows this: "loading tools on demand, filtering data before it reaches the model." For structured tools (database queries, API calls), apply server-side filtering, aggregation, or truncation before returning results to the agent — keeping the model-facing result lean regardless of what the underlying tool computed.

**Tool budgeting for long tasks.** arXiv:2603.13417 identifies "adaptive tool budgeting" as one of three missing MCP protocol primitives at production scale — the idea that a tool should receive a time/computation budget per turn, and the agent should re-plan if the budget is exceeded. This prevents a single slow or verbose tool from derailing a multi-step task.

**Context baseline reduction.** Industry reporting from The Daily Workflow cites enterprise teams reducing MCP baseline context overhead from **143k to under 2k tokens** through dynamic tool schema loading — a 98% reduction. The techniques: lazy tool registration, schema eviction, and context budgeting.

## Evidence

- **Engineering Blog:** Anthropic's "Code execution with MCP" (Nov 2025) — describes on-demand tool loading as a core efficiency pattern; explains filtering data at the tool layer before reaching the model. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **GitHub Repo:** voicetreelab/lazy-mcp — MCP proxy with lazy loading, 104+ stars, MIT license. Live result: 17% token savings (34k tokens) by loading 2 of 50 tools on demand. — [URL](https://github.com/voicetreelab/lazy-mcp)
- **arXiv Paper:** Srinivasan, "Bridging Protocol and Production: Design Patterns for Deploying AI Agents with MCP" (arXiv:2603.13417, March 2026) — documents 10,000+ MCP servers, 97M monthly SDK downloads; identifies "adaptive tool budgeting" as a missing production primitive; notes the gap between MCP's discovery standard and its delivery model. — [URL](https://arxiv.org/html/2603.13417v1)
- **Show HN:** Agent Browser Protocol — Chromium fork for AI agent browser automation; the HN discussion and benchmark repo address stale-state problems in browser agents. — [URL](https://news.ycombinator.com/item?id=47336171)
- **Conference Talk:** Anthropic Applied AI team, "Building Production AI Agents" (2025) via ZenML LLMOps Database — context engineering as top production challenge; transition from workflow-based to agent-based architectures. — [URL](https://www.zenml.io/llmops-database/building-production-ai-agents-lessons-from-claude-code-and-enterprise-deployments)

## Gotchas

- **Loading tools lazily means the agent must know what it doesn't know.** If the manifest omits a tool's existence entirely, the agent cannot request it. Start with a complete capability list (even if summarized) and load schemas on demand — don't filter out tools the agent should see.
- **Schema drift still applies to lazy-loaded tools.** s-999 covers MCP schema drift in depth — the same versioning problem exists, but hits later in the session when a tool the agent just requested has changed since the session started. Version the schema snapshot at load time.
- **Meta-tool overhead.** If `get_tools_in_category` itself consumes significant tokens across many turns, you've moved the cost without reducing it. Profile the meta-tool's contribution to context before committing to this pattern.
- **Multi-agent contexts multiply the problem.** If multiple agents share an MCP connection, each agent loading tools on demand creates concurrent schema requests. Coordinate tool loading at the session or project level, not per-agent-turn.
