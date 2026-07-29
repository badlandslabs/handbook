# S-1833 · The Tool Paradox Stack — When Giving Your Agent More Tools Makes It Less Capable

You give your agent a dozen tools: web search, calculator, code executor, database connector, file reader, API client, Slack notifier. It still picks the wrong tool half the time, calls three in sequence when one would do, or ignores the perfect tool and tries to regex-parse the output. This is the tool paradox: each tool you add reduces the agent's effective capability with the others. Tool count is not power.

## Forces

- **Tool selection is a classification problem that degrades with N.** A 5-tool agent picks correctly ~80% of the time. A 15-tool agent drops to ~40% without careful schema design and prompt anchoring. Each new tool is noise in the context the LLM uses to decide.
- **Every tool has a failure mode that can cascade.** A faulty database connector that returns partial rows causes the agent to build on bad data and compound the error downstream.
- **Latency compounds non-linearly.** Sequential tool calls in a 5-tool chain add 2–4 seconds each. A 15-tool agent that chains three tools to solve one question costs 12+ seconds — and users blame the model, not the architecture.
- **Tool quality varies more than tool quantity matters.** A perfect browser automation tool beats five mediocre ones, but teams keep adding instead of improving the one.
- **The ecosystem is shifting from bespoke integrations to protocol standards.** MCP (Model Context Protocol) has 79K+ GitHub stars and 97M monthly SDK downloads as of early 2026, with official servers from Microsoft, GitHub, Stripe, Atlassian, Figma, and Cloudflare. The era of hand-rolling every tool integration may be ending.

## The move

**Principle 1 — Start with the smallest viable toolset.** Anthropic's engineering team worked with dozens of production agent teams and found the most successful implementations used "simple, composable patterns rather than complex frameworks." Every tool must earn its place by being genuinely necessary for the core use case, not "might be useful someday."

**Principle 2 — Give tools a single, well-scoped purpose, not a menu of capabilities.** Each tool does one thing with a tight input schema. Browser Use (107K stars on GitHub) exemplifies this: it extracts interactive page elements and presents them to the LLM, which outputs structured actions like `input_text(id=3, "Hello")`. One tool, one abstraction, zero ambiguity about what it does.

**Principle 3 — Use MCP for production tool plumbing, not hand-rolled integrations.** MCP has reached ecosystem critical mass. Rather than writing bespoke API connectors, teams connect via MCP servers — Google's enterprise survey found MCP adoption doubled in 6 months. The protocol handles auth, serialization, and discovery. Hand-rolled integrations fail at edge cases MCP already solved.

**Principle 4 — Present tools as structured options, not natural language descriptions.** HN commenter koakuma-chan (June 2025, 543-point thread on Anthropic's building-effective-agents guide): "Sub-agent is another LLM loop that you simply import and provide as a tool to your orchestrator LLM... The agent framework layer here is so thin it might as well not exist, and you can use Anthropic/OAI's SDK directly." Tool schemas with explicit enums and examples outperform free-text descriptions for tool selection.

**Principle 5 — Benchmark tool accuracy before shipping.** Browser Use achieves 87.4% accuracy on a 100-task real-world benchmark and ranks #1 on the Odysseys leaderboard. For every new tool, define a small evaluation set of representative tasks and measure whether the tool works correctly before adding it to the agent's available set.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective Agents" (Dec 2024) — After working with dozens of production agent teams, found the best results came from simple composable patterns. Defined agents as systems where "LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks" — distinguishing agents (dynamic) from workflows (predefined paths). Key recommendation: start with direct API calls, not frameworks. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **GitHub / YC:** Browser Use (YC W25), 107,181 stars, 87.4% accuracy on 100 real-world browser tasks. Core mechanic: extract all interactive elements from a page, present as structured list to LLM, LLM outputs action with element ID. Powers form-filling, data extraction, and QA automation. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)

- **Industry standard:** MCP (Model Context Protocol) reached 79K GitHub stars, 97M monthly SDK downloads, and confirmed production integrations from Microsoft, GitHub, Stripe, Atlassian, Figma, and Cloudflare as of early 2026. Anthropic released MCP in November 2024; the November 2025 update added server discovery, async operations, and scalability improvements targeting enterprise production use. — [modelcontextprotocol.io](https://modelcontextprotocol.io)

- **Hacker News discussion:** Thread on "Building Effective AI Agents" (543 points, June 2025) surfaced strong consensus against framework overhead. koakuma-chan: "The agent framework layer here is so thin it might as well not exist... I don't see a need for fancy graphs with circles here." — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)

- **Production integration:** Anthropic's advanced tool use blog (Aug 2025) introduced programmatic tool calling — code execution can call other tools via `allowed_callers` schema field. This lets agents write code that calls internal APIs safely, without exposing those tools to the LLM directly. — [anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use)

## Gotchas

- **Adding tools without anchoring them in prompts causes the agent to ignore them.** A tool in the schema but not mentioned in the system prompt gets used only when the agent guesses it exists — which is unreliable.
- **Tool schemas that are too generic ("query the database") cause ambiguous selection.** Name the tool for its specific output, not its category: `get_customer_last_30days_orders` not `query_database`.
- **MCP servers are not all production-ready.** The 14,000+ published MCP servers vary wildly in quality, latency, and error handling. Evaluate each one; being on the official registry is not a quality signal.
- **Browser automation tools are brittle to UI changes.** Browser Use (and competitors) depend on element selectors that break when apps update. Build in selector-repair or fallback logic, or use Frigade-style reverse-engineered API-level tools that survive UI changes.
- **Sequential tool calls compound latency in ways that feel like model slowness.** Profile the actual tool execution time separately from LLM inference time — you may find the model is fine and the database query is the bottleneck.
