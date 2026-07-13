# S-1042 · The Protocol Stack — When Your Agent Needs to Talk to Agents and Tools

Your agent calls a Slack API, searches a vector DB, and hands a sub-task to a second agent. Each integration works in isolation. But getting them to share state, handle a handoff failure, or add a third agent means rewriting everything. The agent ecosystem is converging on two complementary protocols — one for tools, one for agents — and teams that treat them as a single problem get stuck building custom bridges that don't survive the next framework upgrade.

## Forces

- **Tool integrations and agent handoffs are architecturally different problems.** Tool calls are synchronous, resource-oriented, and stateless. Agent handoffs are intent-oriented, stateful, and require negotiation about capability, ownership, and completion criteria.
- **Custom protocol proliferation is a dead end.** Before HTTP, every web service had its own wire format. The agent ecosystem is in that phase now — every framework ships its own agent-to-agent format, and cross-framework deployments require translation layers that become maintenance burdens.
- **MCP and A2A address different protocol layers.** Treating them as competitors misses the point: MCP connects agents to external capabilities (tools, data, resources), while A2A connects agents to other agents (delegation, collaboration, negotiation). Teams that implement only one end up with agents that can act but can't coordinate.
- **Adoption is moving faster than documentation.** MCP hit 97M+ downloads by mid-2026. A2A reached v1.0 and attracted 150+ organizational adopters within its first year. But most teams are still using custom JSON schemas for agent communication — the window to standardize is now.

## The Move

**Implement a layered protocol stack: MCP for tool integration, A2A for agent collaboration.**

- **Use MCP as the universal tool integration layer.** MCP servers expose tools via a standardized manifest that any MCP-compatible client can discover — eliminating per-integration custom code. Each server publishes available tools, required permissions, and authentication methods declaratively.
- **Route low-level orchestration decisions to small LLMs.** The Plano architecture uses 1–4B parameter models trained specifically for routing and orchestration decisions — not response generation. They fall back to static policies on failure. This separates the "thinking" model from the "routing" model.
- **Use A2A for agent-to-agent task handoffs.** A2A's capability negotiation lets agents discover what other agents can do before delegating. The agent card pattern lets each agent publish its own capabilities, supported skills, and communication preferences — enabling dynamic team assembly rather than hard-coded delegation trees.
- **Implement a shared context layer for multi-agent state.** MCP acts as the memory bus: agents read from and write to shared context resources that other agents can access. This avoids the "consultant who forgets everything between meetings" failure mode.
- **Design for complementary protocol use.** Critical operations requiring immediate feedback use A2A's synchronous collaboration model. Background or non-critical operations use MCP's resource-oriented patterns. A hybrid approach — A2A for agent negotiation, MCP for tool calls — is the emerging production pattern.
- **Build evaluation loops from day one.** Periodically validate that agent behavior still matches intent. Treat MCP as first-class engineering, not a plugin.

## Evidence

- **GitHub repo + HN:** `mcp-agent` by LastMile AI — implements all MCP patterns composably, ships with durable execution via Temporal for pause/resume/recover. 8,420 stars. — [github.com/lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent)
- **Research summary:** Zylos Research analysis of the MCP × A2A framework — MCP (Anthropic, Nov 2024) at 97M+ downloads, A2A (Google, Apr 2025) at 22K+ GitHub stars, 150+ orgs, v1.0 spec released early 2026. Documents the complementary stack pattern. — [zylos.ai](https://zylos.ai/zh/research/2026-05-16-agent-to-agent-communication-protocols-a2a-mcp/)
- **Arxiv research:** "A Study on the MCP × A2A Framework for Enhancing Multi-Agent Systems" — finds collaborative multi-agent systems have 3× higher problem-solving capability than single agents. Standardized protocols reduce development costs up to 60% and time-to-market by 40%. — [arxiv.org/pdf/2506.01804](https://arxiv.org/pdf/2506.01804)
- **Production deployment:** Plano (Brightstaff controller by Katanemo) — uses small LLMs (1–4B params) for routing decisions, falls back to static policies on failure. Envoy handles retries, timeouts, connection pooling. — [news.ycombinator.com/item?id=46517177](https://news.ycombinator.com/item?id=46517177)
- **Enterprise adoption signal:** Anthropic donated MCP to the Agentic AI Foundation (June 2025). Google contributed A2A to the Linux Foundation (June 2025). AWS and Microsoft both adopted A2A alongside MCP. — [news.ycombinator.com/item?id=46207425](https://news.ycombinator.com/item?id=46207425)

## Gotchas

- **Don't implement MCP without evaluating whether you need A2A too.** MCP handles tools and resources; it doesn't handle agent-to-agent negotiation, handoffs, or shared task state. If your agents are delegating work to each other, you need both layers.
- **MCP client diversity is a discoverability problem.** Every platform (Claude, ChatGPT, custom agents) has different MCP client behavior. A tool that works for one agent may not be discoverable by another. Build explicit capability manifests rather than relying on implicit discovery.
- **A2A's multi-agent coordination is still maturing.** Google explicitly marks multi-agent coordination as a research preview feature in some SDKs. Production multi-agent A2A deployments should expect instability and implement fallback handoff mechanisms.
- **Protocol standardization cuts both ways.** Early adoption locks you into a spec that may still shift. The v1.0 milestone for A2A reduces this risk but doesn't eliminate it — version your agent cards and negotiate protocol versions explicitly.
