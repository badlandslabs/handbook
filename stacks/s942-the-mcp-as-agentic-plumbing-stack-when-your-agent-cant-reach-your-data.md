# S-942 · The MCP-as-Agentic-Plumbing Stack — When Your Agent Can't Reach Your Data

Your agent works in the demo. Then it hits production. The database connector breaks after an API update. The ticketing integration needs an undocumented auth flow. The compliance team asks which data the agent accessed last Tuesday. Nobody can answer. You've built a custom integration for every tool, and every one of them is now your maintenance burden. MCP (the Model Context Protocol) solves the connectivity problem — but only if you treat it as infrastructure, not a library, and treat the public registry with the same skepticism you'd apply to a six-commit npm package.

## Forces

- **Every team was building the same adapter.** Before MCP, connecting Claude to Postgres and Claude to GitHub required two independent custom integrations with no shared semantics. Tool discovery, auth, schema definitions, transport — all were per-connection bespoke work.
- **The public registry is mostly abandoned.** Of 1,847 MCP servers audited in 2026, 52% are abandoned, 31% are lightly maintained, and only 17% meet a reasonable production bar. The median server has six commits. Building on a random public MCP server is the same risk profile as depending on an unmaintained npm package.
- **Production failures cluster at predictable layers.** Across 12,000 trials on 100 servers, 38% of failures came from schema mismatches, 24% from timeouts, 19% from auth/quota issues, and 7% from MCP protocol bugs. Only 12% came from upstream API failures — meaning the integration layer is the dominant failure source, not the underlying service.
- **Silent errors are the worst kind.** One team had 60+ API calls fail silently over 48 hours because stdout/stderr confusion in the stdio transport caused errors to disappear. MCP's flexibility on transports enables this failure mode.
- **Context quality matters more than model quality.** Neo4j's field data shows the core reliability problem in production agents isn't the LLM — it's that agents hallucinate when context is missing, lose track of state across steps, and misuse tools. MCP addresses the tool-misuse piece but doesn't solve context engineering end-to-end.

## The Move

Use MCP as the standardized connectivity layer — but gate it behind infrastructure discipline, not just SDK integration.

- **Build an internal MCP gateway before connecting anything.** Treat MCP as you treat an API gateway: auth, rate limiting, audit logging, and request routing all belong at this layer. Don't let agents call raw MCP servers any more than you'd let a service call raw third-party APIs.
- **Write tool descriptions like documentation, not API specs.** The model reads the description to decide *when* to call a tool, not just *how*. Vague descriptions ("Queries a database") cause agents to call tools at the wrong moment. Specific, behavior-describing descriptions ("Returns up to 50 rows matching the WHERE clause from the orders table, filtered by the user's org_id; returns empty array if no matches") reduce hallucinated tool calls measurably.
- **OpenTelemetry instrumentation on every tool call, from day one.** Every tool invocation should emit a trace with tool name, parameters, result status, latency, and cost. This is the difference between discovering a 48-hour silent failure and catching it in minutes. The teams hitting 95%+ task completion all instrument from the start.
- **Validate the public registry aggressively before adopting.** Audit the commit history, open issues, maintenance cadence, and schema stability. If the server wraps a third-party API, check that API's change cadence — schema mismatches drive 38% of failures. Prefer servers with an active maintainer, semantic versioning, and a changelog.
- **Prefer HTTP/SSE for multi-user production, stdio for local dev.** Stdio transport (parent process spawning the server) is fine for local dev. For anything with concurrent users, HTTP+SSE with proper auth (OAuth 2.0 for enterprise) is the right production shape.
- **Plan for graceful degradation when tools fail.** MCP gives you a standardized interface — use it. If a tool call fails, the agent should know it failed, why, and whether to retry, substitute, or escalate. A tool that returns an error code and a retry-after header is more useful than one that returns 200 with broken data.

## Evidence

- **Enterprise research post:** MCP reached 97 million monthly SDK downloads and 9,400+ public servers by April 2026; 78% of enterprise AI teams have at least one MCP agent in production (up from 31% a year earlier). Fortune 500 adoption is ~28%. — [AI Agents First](https://aiagentsfirst.com/mcp-in-production-2026-builder-playbook)
- **Independent technical analysis:** Of 1,847 MCP servers audited in 2026, 52% are abandoned; median server task completion is 71%, top 10% achieves 95%+. Failure breakdown across 12,000 trials: 38% schema mismatches, 24% timeouts, 19% auth/quota, 12% upstream API, 7% protocol bugs. — [AI Agents First](https://aiagentsfirst.com/mcp-in-production-2026-builder-playbook)
- **Ecosystem overview:** MCP was introduced by Anthropic in November 2024, donated to the Linux Foundation's Agentic AI Foundation in December 2025. Supported by Anthropic, OpenAI, Google, Microsoft, Salesforce, Snowflake, and most API gateway vendors. One team had 60+ API calls fail silently over 48 hours due to stdio stdout/stderr confusion. — [Kubiya AI](https://www.kubiya.ai/blog/model-context-protocol-mcp-architecture-components-and-workflow) and [Blaxel AI](https://blaxel.ai/blog/mcp-use-cases)
- **Field perspective:** Reliability depends on context quality, not model capability. Production agents break down most often when context is missing, state is lost across steps, or tools are misused. MCP addresses the tool-misuse component. — [Neo4j Blog](https://neo4j.com/blog/agentic-ai/ai-agent-useful-case-studies/) (Jesús Barrasa, AI Field CTO, February 2026)

## Gotchas

- **The "works in demo, fails in prod" pattern.** MCP demos typically run locally with stdio transport and a single agent. Production adds concurrency, auth, rate limits, network transport, and audit requirements. Design for production from the first server, not after.
- **Schema drift is silent.** When the upstream API changes its response shape, the MCP server may return subtly different data that passes type checks but breaks the agent's expectations. Regression-test your MCP servers against the real API, not just mocked responses.
- **Don't over-abstract.** MCP's strength is standardization. Wrapping every micro-tool behind an MCP server adds ceremony without benefit. Gate MCP adoption at the meaningful integration boundary (database, external API, file system, internal service), not at every function call.
- **MCP doesn't solve context engineering.** It gives agents a standardized way to call tools. Whether the agent has the right context to make that call correctly — that's a separate problem solved by your context pipeline (RAG, memory, conversation compression), your orchestration pattern, and your evaluation system.
