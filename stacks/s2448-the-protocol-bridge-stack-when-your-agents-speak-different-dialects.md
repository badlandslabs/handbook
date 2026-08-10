# S-2448 · The Protocol Bridge Stack — When Your Agents Speak Different Dialects

Your researcher agent found a critical bug. Your writer agent has no idea. Your code-execution agent can't access the same tool as your data agent because each was built with a different integration layer. This is not a model problem. It's a plumbing problem. In 2025-2026, the agent ecosystem is converging on two complementary open protocols — MCP for vertical tool access, A2A for horizontal agent coordination — and teams that wire them together deliberately are leaving the ones that didn't far behind.

## Forces

- **Two distinct communication problems require two distinct protocols.** MCP solves how an agent talks to *tools* (client-server, request-response). A2A solves how agents talk to *each other* (peer-like, task negotiation). Treating them as interchangeable leads to overengineered tool definitions or underspecified agent handoffs.
- **Early integration choices lock you in.** Teams that hardcoded proprietary tool abstractions in 2024 are rewriting them in 2026. The MCP/A2A convergence is real — both donated to the Linux Foundation — but the migration cost of early choices compounds with every new agent you add.
- **Token cost explodes when tools are loaded naively.** Anthropic's November 2025 post documented that loading all tool definitions into context upfront — the naive MCP approach — causes quadratic token growth at scale. The fix is code-execution-based tool dispatch, not fewer tools.
- **Multi-agent coordination overhead degrades sequential tasks.** Openlayer's March 2026 analysis found that supervisor and hierarchical patterns boosted *parallel* task performance by ~80% but *degraded* sequential reasoning by 39–70%. The protocol stack doesn't fix bad task decomposition — it just makes bad decomposition faster.

## The Move

**Build a two-layer protocol bridge: MCP as the tool interface layer, A2A as the agent coordination layer. Keep them explicit and composable.**

- **Use MCP for every agent-to-tool interaction.** Define tools as MCP servers with explicit schemas, idempotent operations, and structured error responses. Single implementation, any MCP-aware runtime. This replaces the custom per-agent integrations that dominated 2024.
- **Use A2A for every agent-to-agent handoff.** When one agent needs work from another — task assignment, status negotiation, context passing — A2A's Agent Cards provide discovery without hardcoding URLs. This is the layer that enables supervisor/worker and peer patterns to compose.
- **Write code to dispatch tools, not prompt tool descriptions.** Anthropic's production pattern (November 2025): agents write code that calls MCP tools rather than embedding tool definitions in prompts. This reduces token consumption per step and makes tool behavior deterministic and testable.
- **Partition tool definitions from agent prompts.** Load tool schemas at startup into a tool registry; load only the relevant subset into each agent's context at task time. This directly addresses the token explosion from loading 100+ tools naively.
- **Expose Agent Cards for every agent you operate.** A2A's Agent Card (JSON manifest of capabilities, skills, and endpoints) enables runtime discovery — new agents joining a supervisor pool self-register rather than requiring manual coordination code.
- **Layer circuit breakers at the MCP client boundary.** When an MCP tool call fails — timeout, API error, malformed response — the retry and fallback logic lives here, not inside the agent's reasoning loop. The agent should see only a clean success/failure with no exposed retries.

## Evidence

- **Engineering blog:** Anthropic published "Code execution with MCP" documenting that direct per-call tool definitions cause token inefficiencies, and that code-execution-based tool dispatch scales better at high tool counts. Production agents using this pattern saw reduced context consumption and faster tool selection. — [Anthropic Engineering, Nov 4 2025](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Industry analysis:** Openlayer's March 2026 multi-agent architecture survey found supervisor patterns improved parallel task throughput by ~80%, while sequential reasoning degraded 39–70% due to coordination overhead. The data comes from analyzing production deployments across framework types (LangGraph, CrewAI, AutoGen). — [Openlayer, Mar 9 2026](https://www.openlayer.com/blog/multi-agent-system-architecture-guide)
- **Enterprise case study:** Databricks documented BASF Coatings deploying a supervisor agent architecture with a central orchestrator managing specialized sub-agents, using Databricks' agent framework. The system integrated cross-team data sources and delivered measurably smarter field collaboration decisions. — [Databricks Blog, Oct 23 2025](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **Protocol standard:** Google's A2A protocol was donated to the Linux Foundation in June 2025 with 50+ founding partners (AWS, Microsoft, Salesforce, SAP). It specifies agent capability discovery, task negotiation, and state sharing — complementing MCP's tool-access focus with inter-agent collaboration primitives. — [Google Developers Blog, Apr 2025](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)

## Gotchas

- **Don't use A2A for tool calls.** A2A is designed for agent-to-agent task negotiation, not tool invocation. Trying to use A2A where MCP belongs produces unnecessary overhead — A2A's negotiation protocol is overkill for a single tool call, and you lose MCP's structured tool semantics.
- **Don't load all MCP tools into every agent's context.** Tool schema explosion is real. At 50+ tools, naive loading consumes your context budget before the agent does any useful work. Use a tool registry with selective loading per task type.
- **Don't assume protocol stability before you pin versions.** Both MCP and A2A are under active development. Pin to specific protocol versions in your MCP server and A2A agent card manifests; test compatibility on every upgrade, especially for schema changes in tool definitions.
- **Supervisor patterns don't help sequential tasks.** If your workflow is inherently serial — each step depends on the previous — adding more agents creates coordination overhead without throughput benefit. Profile before adopting a multi-agent architecture.
- **MCP stdio transport is for development, HTTP for production.** Many teams start with stdio-based MCP servers for local dev and then hit transport issues when deploying. Plan the HTTP transport migration on day one.
