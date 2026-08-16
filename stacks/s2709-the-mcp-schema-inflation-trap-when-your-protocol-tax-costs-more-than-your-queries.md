# [S-2709] · The MCP Schema Inflation Trap — When Your Protocol Tax Costs More Than Your Queries

When you wire up Model Context Protocol, every tool sends its full JSON schema, parameter definitions, and descriptions to the LLM on every single request — before the model processes a single user token. Add five servers with 30 tools each and you've burned 30,000 tokens of context before the conversation starts. At scale, this isn't overhead. It's the primary cost driver, and it's invisible unless you look for it.

## Forces

- MCP was designed for tool discovery and portability — not for token efficiency. Its architecture sends complete schemas on every call, and there's no built-in mechanism to send only the tools relevant to the current request.
- The problem scales with MCP adoption. More servers, more tools, more context consumed. Five MCP servers with 30 tools each: ~30K tokens per turn. Ten servers: ~60K. Your effective context window shrinks by 40–72% before the model does any real work.
- This is a *protocol-level* problem, not a tool-design problem. You can write perfect tool descriptions and still hit the ceiling — because the architecture itself is the bottleneck.
- The field has split: Perplexity's CTO (Denis Yarats, March 2026) publicly abandoned MCP citing 72% context consumption. Cloudflare replaced tool-calling with code generation. Google Workspace quietly dropped MCP support. But 97M+ downloads mean most production agents still carry this tax.
- Mitigation strategies exist — lazy loading, tool pre-selection, schema caching — but they require deliberate engineering and conflict with MCP's "just works" design philosophy. The protocol doesn't make the right thing easy.

## The Move

**1. Measure your schema footprint before adding more tools.**

Add instrumentation that logs token count of MCP tool schemas per request. Run your top 10 request types and record schema cost vs. content cost. If schema tokens exceed 30% of context, you have a real problem. If they exceed 60%, your agent is primarily a tool-catalog reader.

**2. Gate tool availability — not by permission, by relevance.**

The fastest fix: don't send every enabled tool to every request. Implement a tool pre-selector that filters the active toolset to the top-K relevant tools before the schema payload is built. At request time, send only the 5–10 tools most likely to apply, based on intent classification or a lightweight routing model. The rest are available on demand but don't consume context.

Christian Posta (Solo.io) and Gil Feig (Merge) both recommend staying under 10–15 active tools per turn. This isn't a preference — it's the practical ceiling before model tool-selection accuracy degrades.

**3. Use session-level schema caching, not per-request injection.**

MCP tool schemas are static for the duration of a session. Cache the compiled schema payload once per session and inject it only on the first turn. For subsequent turns, use a compact tool reference (name + version hash) that the routing layer expands. This eliminates the repeated tax on long conversations.

**4. Externalize tool logic into focused sub-agents.**

When a tool domain is large — a full SQL MCP server with 106 tools — don't expose all 106 to a single agent. Spin up a narrow sub-agent that owns that domain and exposes 2–3 high-level actions. The parent agent calls the sub-agent; the sub-agent's 106-tool schema never enters the parent's context.

**5. Treat MCP server count as a budget item, not a feature count.**

Every additional MCP server you enable is a token commitment. Set a schema token budget per agent (e.g., 20% of context) and track it as a first-class metric alongside latency and cost. When a new MCP server would push you over budget, that's a trigger to revisit tool pre-selection or restructure the agent's tool surface.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — routing decisions include tool budget tradeoffs
- [S-427 · MCP Schema Contracts](s427-mcp-schema-contracts-when-your-tool-description-changes-and-nobody-warns-you.md) — schema *drift* over time vs. per-request schema *inflation*
- [S-773 · The Fixed Token Overhead Problem](s773-the-fixed-token-overhead-problem-when-per-call-costs-eat-your-budget.md) — economics of per-call overhead vs. query cost
