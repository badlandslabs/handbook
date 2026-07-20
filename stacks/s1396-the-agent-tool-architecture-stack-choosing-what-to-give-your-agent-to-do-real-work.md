# S-1396 · The Agent Tool Architecture Stack — Choosing What to Give Your Agent to Do Real Work

An agent without tools is a chatbot that prints text and stops. An agent with too many tools is a person handed a toolbox with 1,000 drawers and told to fix a leaky faucet. The tool selection problem — what to expose, how to structure it, and what the model can actually invoke reliably — is the single biggest architectural decision in agentic systems. It determines whether your agent ships results or just describes them.

S-1393 (orchestration) covers chaining steps. S-1394 (token budgets) covers cost control. Neither addresses the core capability gate: **what the agent can actually touch in the world**.

## Forces

- **Tool count scales inversely with reliability.** Giving an agent 600+ tools sounds powerful but makes the model call the wrong one, miss one entirely, or hallucinate a tool that doesn't exist. Production deployments consistently find that fewer, well-scoped tools outperform comprehensive tool sets.
- **The tool-definition surface is where most agent bugs live.** JSON schema mismatches, missing error fields, ambiguous tool names, and underspecified parameters cause more production failures than model quality. Local models (Qwen 3.5 27B/35B, Gemma 4) fail to properly use tools and agentic templates in ways that Claude and DeepSeek handle "out of the box" — a hard hardware requirement for agentic workloads.
- **Browser control is now a first-class production tool, not a demo.** Claude Computer Use, OpenAI Operator, Google Mariner, and open-source alternatives (Browser Use, Open Computer Use) give agents pixel-level screen control. This shifts what's possible — and what risks exist — fundamentally.
- **MCP solved the integration plumbing but created a new governance problem.** Anthropic introduced MCP in November 2024; SDK downloads went from ~100K/month to 97 million/month by March 2026 (970x in 18 months). Every Fortune 500 now has at least one MCP use case in production. The standard solved "how to connect" but left unanswered "which tools, with what permissions, audited how."
- **Function calling accuracy varies dramatically by model.** Smaller local models fail at tool selection under real-world input variance (null values, Unicode names like O'Brien or José, empty fields). Claude and DeepSeek are consistently cited as working "out of the box" for agentic tool use; everything else requires significant prompt scaffolding.

## The Move

The tool architecture is not "give the agent everything." It is **curate capability surfaces, then make each tool unambiguous to invoke**.

### Curate, don't aggregate

- Expose only the tools relevant to the agent's specific task. A research agent gets web search + document read + note write. A DevOps agent gets log read + deploy trigger + alert acknowledge. An agent with 5 tools and clear schemas beats an agent with 500 tools and vague ones.
- Composio (29K GitHub stars) and ACI.dev (4.7K stars) both started as aggregation platforms but the pattern that works in production is **selective tool registration** — install 10-20 relevant toolkits, not all 1,000.

### Structure tool definitions like APIs, not prompts

- Name tools with verb-noun patterns: `search_web`, `read_file`, `write_database`, `send_email`. Avoid clever names the model has to decode.
- Define every parameter with strict types, enums where possible, and descriptions that explain what valid values look like. The MCP server must define parameters clearly — array schemas without `items`, missing descriptions, and ambiguous types are the top source of `invalid_function_parameters` errors.
- Return structured error responses, not free text. The agent needs to know *why* a tool failed to decide whether to retry, substitute, or escalate.

### Browser control as a production tool (with guardrails)

- Browser Use (browser-use.com, open source) is the dominant open-source framework for giving agents web interaction. It uses vision-enabled LLM analysis of rendered HTML to automate form filling, data extraction, and multi-step workflows — replacing brittle Selenium/Playwright scripts that break on any UI change.
- Cost per browser workflow: Claude Computer Use runs $0.24–$0.36 per task. OpenAI Operator hits 87% success on complex sites. Google Mariner scores 83.5% on WebVoyager benchmark.
- Open Computer Use (coasty-ai/open-computer-use, 82% on OSWorld) is the leading open-source alternative for full desktop control: browser + terminal + desktop apps via MCP. Ships as a self-hosted Docker container with no vendor lock-in.
- For regulated environments: sandboxed execution, permission scoping, and audit logging are non-negotiable before letting an agent click through real UI.

### Use MCP as the protocol, not the policy

- MCP (Model Context Protocol) is the dominant connection standard. Any tool registered as an MCP server is accessible to Claude, Cursor, Windsurf, and any other MCP-compatible client without per-integration code.
- The tool categories that appear across every agentic stack: (1) web search/scraping (Firecrawl, Tavily, Jina), (2) code execution (sandboxed Python/shell), (3) database operations (Postgres, MongoDB via MCP), (4) file I/O, (5) API integrations (Slack, GitHub, Salesforce — the SaaS layer).
- Authentication is a first-class concern: Composio ships with per-user OAuth, per-user sessions, and a sandbox workbench. When agents act on behalf of users (not just in system-wide contexts), each action must be scoped to that user's permissions.

### Add a deterministic core for high-stakes paths

- For workflows where the agent must produce a specific outcome (not explore): embed deterministic fallback logic. One HN practitioner reports: "marking with a red line versus rewriting is fundamentally easier and less error-prone" — use unified diffs for code changes, structured output formats for data extraction, and bounded action trees for sequential workflows.
- The "deterministic core + LLM orchestration" pattern (SSOT architecture) addresses the most common production failure: "The Loop of Doom" where the agent retries the same failed tool call indefinitely. Wrap tool calls with max-retry logic and explicit escalation paths.

## Evidence

- **GitHub repo / primary source:** ComposioHQ/composio — 29,292 stars, 4,667 forks, 1,000+ toolkits, per-user authentication, MCP-native. Used by enterprise teams replacing bespoke API integrations. — [github.com/ComposioHQ/composio](https://github.com/ComposioHQ/composio)
- **GitHub repo / primary source:** browser-use/monitor — open-source Browser Use project that integrates LLMs with rendered page analysis for AI-driven web automation. Desktop app uses Electron to run agents locally with privacy-preserving browser control. — [github.com/browser-use/monitor](https://github.com/browser-use/monitor)
- **Benchmark / engineering post:** WOWHOW benchmark (April 2026) testing Claude Computer Use, OpenAI Operator, and Google Mariner on WebVoyager and OSWorld. Operator 87% complex-site success; Claude $0.24–$0.36/workflow; Mariner 83.5% WebVoyager. — [wowhow.cloud](https://wowhow.cloud/blogs/computer-use-ai-agents-browser-desktop-automation-2026)
- **Industry data:** Bacancy Technology — MCP SDK downloads grew from ~100K/month to 97 million/month in 18 months (Nov 2024 to March 2026), attributed to enterprise adoption across financial services, healthcare, retail, and manufacturing. — [bacancytechnology.com/blog/enterprise-mcp-use-cases](https://www.bacancytechnology.com/blog/enterprise-mcp-use-cases)
- **Community / discussion:** r/LocalLLaMA discussion on local LLM tool use — "Agentic workflows require very strong models specifically trained for agentic workflows and tool use. Smaller models will make you lose hours debugging errors while Claude and DeepSeek work 'out of the box' most of the time." — [reddit.com/r/LocalLLaMA/comments/1sdvhk3](https://reddit.com/r/LocalLLaMA/comments/1sdvhk3)
- **Agent community brief:** Agent Brief (Feb 2026) documents "16 distinct failure patterns" in agent production including "The Loop of Doom" and "Tool Output Pollution," addressed by SSOT/deterministic-core architectures. — [news.agentcommunity.org](https://news.agentcommunity.org/issues/2026-02-25-hardening-the-agentic)

## Gotchas

- **Tool count explosion causes model paralysis.** Giving an agent access to 600+ functions is the path to "I don't know which tool to use" responses. Start with 3–8 tools scoped to the task. Add breadth only when the agent demonstrates it can use the core set reliably.
- **Tool schema errors are silent failures.** A missing `items` in an array schema, an underspecified `description`, or a tool that returns unstructured text instead of typed output will cause the agent to misinterpret results. Write integration tests that validate each tool's schema and output shape independently.
- **Browser agents require anti-detection infrastructure in production.** Sites block automation patterns. Browser Use and Open Computer Use both require stealth browser features (fingerprint rotation, human-like timing) to work on real sites — a separate engineering concern from the agent logic itself.
- **Per-user auth is not optional for user-facing agents.** A single system-level API key shared across all users is a data leakage risk. Composio's per-user OAuth sessions address this; rolling your own tool layer must implement the same.
- **Local models cannot reliably drive agentic tool use without strong scaffolding.** If your stack uses Ollama + Qwen or Gemma, budget significant engineering time for tool-calling scaffolding, retry logic, and error recovery. The "it works in demos" trap is real.
