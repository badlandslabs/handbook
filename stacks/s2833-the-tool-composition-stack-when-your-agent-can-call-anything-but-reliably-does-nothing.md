# S-2833 · The Tool Composition Stack — When Your Agent Can Call Anything but Reliably Does Nothing

You've given your agent a GitHub MCP server, a Notion server, a Slack server, a code execution sandbox, and a web browser. 800 lines of tool definitions. It responds to every query with a plausible-sounding plan and then produces a JSON function call that passes schema validation while silently doing the wrong thing. The error logs are empty. The agent confidently reports success. The CRM record was never updated.

This is the tool composition problem: tools are easy to add and nearly impossible to reason about once they interact. The question isn't whether your agent can call a tool — it's whether it reliably does so correctly, safely, and without cascading into silent failure.

## Forces

- **The 95% reliability cliff:** At 95% per-step reliability, a 10-step workflow succeeds ~59% of the time. A 15-step workflow drops to ~46%. Most enterprise agent workflows exceed 15 steps. (AgentMarketCap, 2026)
- **The N+M simplification:** Before MCP, every agent-to-tool integration was custom. N agents × M tools = N×M one-off connectors. Model Context Protocol reduced this to N+M — a single standard that agents and tools both speak. (Reactify Solutions, June 2026)
- **The tool count optimum:** The sweet spot is 5–20 scoped tools per agent. Below 5, the agent lacks coverage. Above 20, boundaries blur and the model struggles to select correctly. (Shopify Sidekick engineering, ICML 2025)
- **The USB-C moment:** Anthropic donated MCP to the Linux Foundation's Agentic AI Foundation in December 2025. Within 18 months of launch, MCP had 97M+ monthly SDK downloads and 10,000+ active public servers. It won by solving the integration tax. (Anthropic, December 2025)
- **The silent failure tax:** The most common production failure isn't a crash — it's a tool call that returns HTTP 200, produces a plausible output, and skips the actual work. Schema validation failures, semantic mismatches, and permission errors are invisible unless you instrument for them. (AgentMarketCap, April 2026)

## The Move

**Compose tools in layers: narrow, typed, permission-scoped, and observability-wired from day one.**

### 1. Start with MCP as your tool protocol
- MCP (Model Context Protocol) is the winning standard — backed by Anthropic, OpenAI, Google, and Microsoft, governed by the Linux Foundation. Use it for every tool integration. Do not write custom REST wrappers for individual APIs.
- The three MCP roles enforce clean boundaries: **Host** owns the model and user consent; **Client** maintains the secure channel to each server; **Server** exposes scoped tools without seeing the model or other servers.
- 41% of senior software leaders were already running MCP in production as of early 2026. (Stacklok State of MCP 2026 survey)

### 2. Scope tools to a single responsibility
- One tool = one atomic operation. Not `update_customer_and_notify_and_log`, but `update_customer_record` and `send_notification` as separate tools. This gives the agent granular control and makes each call independently observable.
- Shopify Sidekick uses MCP servers per layer: Dev MCP for documentation + GraphQL schemas (no production data), Storefront MCP for storefront data, Catalog MCP for product data. Each MCP server is a separate trust boundary with separate authentication. (Shopify Engineering, August 2025)

### 3. Give agents a tool hierarchy, not a flat list
- Present tools in context: relevant tools only, not all 47 available tools. JIT (just-in-time) tool delivery — showing only the tools needed for the current task — outperforms giving the agent full access.
- Claude's tool use guidance recommends: "Prefer retrieving information and adding it to your model context through RAG rather than giving the model direct database access." The tool should serve the context, not replace it.

### 4. Sandbox code execution tools
- Any tool that runs LLM-generated code must run in isolation. E2B (Firecracker microVMs), Modal, or agent-sandbox provide cloud sandboxes with CPU/memory/network/time limits.
- The agent-sandbox project (Apache 2.0, GitHub) consolidates multiple sandbox types — code execution, browser use, computer use — into one deployment, used by enterprises who need FIPS-compliant isolation.
- At minimum: no production credentials in the sandbox, resource limits enforced, stdout/stderr captured, timeout per execution turn. (Chaitanya Prabuddha blog, March 2026)

### 5. Instrument for silent failures
- Log every tool call with: tool name, arguments, return value, duration, and a success/failure flag. A tool call returning 200 with empty data is a failure, not success.
- Schema validation failures are the #1 silent killer — the model produces a tool call that passes your JSON Schema but contains wrong argument types or out-of-range values. Add application-level validation beyond schema, and surface validation errors back to the agent with corrective guidance.
- Anthropic's recommendation: "The language model should be the most boring part of your code. You should be spending most of your time building the actual software and tooling." (HN user sippeangelo paraphrasing, March 2025)

### 6. Build browser/computer use only when necessary
- Browser agents (Browser Use, Open Interpreter) score 63–79% on benchmarks like BrowserArena. The gap to 95%+ production reliability is still significant.
- Cloud browser tools (Browser Use Cloud) outperform open-source models by 16 points through full-stack optimization: stealth proxies, CAPTCHA solving, persistent filesystem, optimized tool orchestration — not just a better LLM. (BrowserArena data)
- Prefer structured APIs and MCP connections over browser automation whenever the target exposes an API. Browser use is for sites that don't.

## Evidence

- **Shopify Engineering (Aug 2025):** Sidekick's architecture uses MCP servers per trust boundary (Dev, Storefront, Catalog). The agent loop: human input → LLM → decision → action → feedback → repeat. Key insight: tool count above 50 splits into separate agent teams with scoped access. — [https://shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)

- **Anthropic Engineering (Dec 2024):** "Most successful implementations weren't using the most capable models. They used simpler architectures with more reliable tooling." Agents are appropriate only when task completion genuinely requires model-directed next-step determination — not as a default pattern. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **AgentMarketCap (April 2026):** At 85% per-step reliability × 10 steps, end-to-end success is ~20%. At 95% × 15 steps, ~46%. Most enterprise workflows exceed 15 steps. Silent function calling failures (schema validation, semantic mismatch, permission errors) are the #1 untracked production failure mode. — [https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026](https://agentmarketcap.ai/blog/2026/04/11/function-calling-reliability-production-agents-2026)

- **Reactify Solutions (June 2026):** MCP SDK downloads grew 100K → 97M per month in under a year. 41% of senior software leaders in production with MCP. The protocol transformed N×M custom connectors into N+M standardized connections. — [https://www.reactify-solutions.com/articles/mcp-production-ai-integrations-2026](https://www.reactify-solutions.com/articles/mcp-production-ai-integrations-2026)

## Gotchas

- **Schema validation ≠ correctness.** A tool call that passes JSON Schema can still have wrong values. Add application-level validation and return corrective feedback to the agent on failure — not just an error string.
- **Too many tools is worse than too few.** The model must reason over every available tool. JIT delivery (showing only relevant tools per step) consistently outperforms full tool inventory access. A 47-tool flat list is not an advantage.
- **Browser use is not production-ready for high-stakes workflows.** Current benchmarks (BrowserArena, GAIA) show 63–79% accuracy. Design for graceful degradation: if the browser automation fails, fall back to structured API calls or human review.
- **43% of public MCP servers have command injection flaws** (analyzed across 177,436 servers, per Alice Labs/MCP study). Audit any MCP server before giving an agent access — especially those exposing shell commands or filesystem writes.
- **Tool permission scopes are your real access control.** MCP's Host/Client/Server separation is not just architectural — it's your security boundary. Treat each MCP server as a separate process with its own credentials and blast radius.
