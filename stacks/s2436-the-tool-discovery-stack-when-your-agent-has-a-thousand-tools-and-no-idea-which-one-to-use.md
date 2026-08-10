# S-2436 · The Tool Discovery Stack — When Your Agent Has a Thousand Tools and No Idea Which One to Use

The moment you give an agent 20+ tools, a new class of problem emerges: not "can it use the right tool?" but "can it even find the right tool without burning half its context window first?" This is the tool discovery problem — and it's the first wall every production agent hits.

## Forces

- **Token overhead compounds.** A single MCP server with 35 tools (GitHub) can consume ~26K tokens in tool definitions before the agent does any real work. Stack three servers and you're already at context limit before the first action.
- **Static tool registration vs. dynamic tasks.** Registering all tools at initialization is safe but wasteful. Discovering tools on demand is efficient but requires the agent to know what it doesn't know.
- **Accuracy vs. verbosity trade-off.** Rich tool descriptions improve selection accuracy but inflate the prompt. Minimal descriptions save tokens but increase misrouting.
- **Tool quality varies by source.** MCP servers from the community can have malformed schemas, misleading descriptions, or missing parameter docs — the agent trusts what it receives.

## The move

**Give the agent a tool to find tools — then design every other tool to be discovered, not declared all at once.**

- **On-demand tool discovery.** Anthropic's Tool Search Tool (Nov 2025 beta) lets Claude search across thousands of registered tools by semantic query, loading only the relevant definitions. The GitHub MCP server drops from ~26K tokens to ~4K tokens when discovered dynamically — an 85% reduction while preserving 95% of context. The agent calls a `tool_search` tool with a natural-language description of what it needs, and the system returns ranked candidates.

- **Programmatic tool calling over natural-language round-trips.** Anthropic's Programmatic Tool Calling (Nov 2025 beta) lets agents invoke tools directly via code execution rather than waiting for the next inference cycle. This enables parallel tool calls, conditional invocation, and loop-based retry without piling tool results into context. Claude for Excel uses this to read/modify spreadsheets with thousands of rows without context overflow. Token reduction: ~37% on orchestration-heavy tasks.

- **Tool use examples as a universal standard.** Anthropic's Tool Use Examples let developers attach demonstration conversations showing the tool in action. From their Nov 2025 engineering post: "Agents need to learn correct tool usage from examples, not just schema definitions." In testing, this raised tool-call accuracy from 72% to 90% on complex multi-step tasks.

- **Design MCP tools for discovery, not just specification.** Each tool needs: (1) a precise name that mirrors how a human would ask for the action, (2) a description written for an LLM, not a developer (state the effect, not the implementation), (3) concrete examples of inputs/outputs. The MCP registry (GitHub, launched Sep 2025) now indexes thousands of community-built servers — tool design directly affects discoverability.

- **Instrument the four-layer failure surface.** Tool calls traverse a delegation chain: LLM planner → orchestration layer → tool executor → connector → OAuth provider → upstream API. Per-step reliability of 95% sounds fine until you run a 10-step workflow — you get a 60% success rate. Scalekit's production analysis (2025) found tool calls fail silently 3–15% of the time due to network timeouts, rate limits, and upstream interruptions. Instrument each layer explicitly; the agent's "success" response at each step masks partial failures.

## Evidence

- **Anthropic Engineering (Nov 2025):** Introduced Tool Search Tool, Programmatic Tool Calling, and Tool Use Examples on the Claude Developer Platform. Tool Search reduced GitHub MCP token overhead by 85%. Programmatic Tool Calling achieved 37% token reduction via parallel execution. Tool Use Examples improved accuracy from 72% to 90%. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)

- **ClickHouse Engineering Blog (2025):** Compared 12 agent frameworks supporting MCP. Found that MCP adoption has been rapid since Nov 2024 launch, with OpenAI, Gemini, and Vertex AI all adding support. Key differentiator across frameworks: Claude Agent SDK uses security-first production with explicit tool allowlists; OpenAI Agents SDK uses agent handoffs and streaming; Agno achieves minimal boilerplate (~10 lines for MCP). — [URL](https://clickhouse.com/blog/how-to-build-ai-agents-mcp-12-frameworks)

- **Scalekit (2025):** Production telemetry analysis found 1 in 20 AI model requests already fail in production (per Datadog). Tool call failures compound geometrically: a 10-step workflow at 95% per-step reliability succeeds only 59.9% of the time. Silent auth failures (expired OAuth tokens returning empty results) were identified as a structural blind spot — the agent treats empty context as valid state. — [URL](https://www.scalekit.com/blog/tool-call-failures-production)

- **GitHub MCP Registry (Sep 2025):** Launched to address fragmented MCP server discovery. Before: finding the right server required searching GitHub, reading docs, and writing custom integration. After: centralized registry with searchable MCP servers. — [URL](https://github.com/mcp)

## Gotchas

- **Tool schema drift breaks agents silently.** When an upstream API changes a response schema, the tool definition may still match but the agent's output parsing fails. The agent doesn't crash — it returns malformed data downstream. Version pin MCP servers or add schema validation at the connector layer.

- **"All tools available" is not a feature in production.** Developers often expose every MCP server they have access to. The agent wastes tokens evaluating irrelevant tools and may misroute on ambiguous tasks. Whitelist only the tools relevant to the current session's goal.

- **Rate limit errors return HTTP 429 — but tool call timeouts can return empty `null` with no error.** Different MCP servers handle errors differently. Some return structured error objects; others return `null` and an HTTP 200. The agent treats both as "got a result." Wrap every tool invocation with explicit error detection before passing output to the next step.

- **Tool names are the first (and cheapest) UX decision.** Anthropic's docs explicitly note that agents learn correct usage from examples, not schema. A tool named `get_user()` vs `fetchUserById()` will produce measurably different agent behavior even with identical schemas. Invest naming effort upfront.
