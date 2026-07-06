# S-689 · The Agent Interoperability Layer Has Arrived

MCP and A2A have moved from proposals to production plumbing. The two-protocol stack (vertical tool integration + horizontal agent coordination) is now the default enterprise architecture — and it's governed by the Linux Foundation.

## Forces

- **Protocol fragmentation was the #1 inhibitor to multi-agent production systems.** Every team built custom transport layers for agent-to-agent communication. A2A changes this — but only because it landed alongside governance.
- **MCP's 18,000+ server registry made it the de facto tool-integration standard before any committee ratified it.** Adoption outpaced standardization, which forced institutional alignment rather than creating it.
- **The two-layer model (MCP + A2A) mirrors the cloud IaaS/PaaS split.** Vertical integration (tool→agent) and horizontal coordination (agent→agent) have different requirements and different optimal designs. Confusing them creates overengineered stacks.
- **OpenAI Agents SDK (Swarm successor) and LangGraph both added native MCP support before A2A support stabilized.** This signals where the market momentum is.

## The move

- **Default to MCP for every agent→tool boundary.** It auto-generates JSON-RPC schemas from Python decorators (FastMCP), eliminates custom REST wrappers, and gives structured outputs for free. One registry to search instead of one-off integrations.
- **Reserve A2A for agent→agent handoffs in multi-agent systems.** The protocol handles capability negotiation, task handoff, and state passing — replacing ad-hoc message passing and shared-memory hacks.
- **Use Anthropic's Claude Agent SDK or OpenAI Agents SDK as your base.** Both now have first-class MCP support. OpenAI's SDK is the Swarm successor (handoffs, guardrails, tracing as primitives). Anthropic's SDK is the canonical MCP reference implementation.
- **Look for Linux Foundation AAIF governance as a signal of long-term viability.** Founding members (Anthropic, OpenAI, Google, Microsoft, AWS, Block, Cloudflare, Bloomberg) means the protocol won't disappear from under your stack.
- **For the agent-to-agent handoff schema: version every message contract.** Untyped handoffs kill multi-agent workflows faster than any other issue. Every boundary needs a validated schema with version numbering.
- **Composite cost model for multi-agent: $5–8 per complex task on a 4-agent workflow.** Model inference economics before committing to architecture — costs compound across agents.

## Evidence

- **Zylos Research (Q1 2026):** MCP has 18,000+ community-indexed servers, tens of millions of monthly SDK downloads, and 15 months from launch to enterprise infrastructure status. A2A has 21,900+ GitHub stars. Both now under Linux Foundation AAIF governance with Anthropic, OpenAI, Google, Microsoft, AWS, Block, Cloudflare, and Bloomberg as founding members. — [zylos.ai/research/2026-03-26-agent-interoperability-protocols-mcp-a2a-acp-convergence](https://zylos.ai/research/2026-03-26-agent-interoperability-protocols-mcp-a2a-acp-convergence)
- **Raft Labs (2025):** Multi-agent inference cost compounds to $5–8 per complex task on a 4-agent orchestrator-worker workflow. Untyped handoffs between agents identified as the #1 reliability killer. 89% of teams have observability but only 52% have evals — explaining why multi-agent debugging is mostly guesswork. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **HN/Opensoul (2025):** Open-source marketing agent stack using 6 agents (Director/Strategist/Creative/Producer/Growth/Analyst) built on Paperclip orchestration platform. Each agent runs on scheduled heartbeats, checks work queues, executes tasks, and delegates to teammates. Demonstrates the heartbeat + queue model as the practical alternative to real-time agent messaging. — [news.ycombinator.com/item?id=47336615](https://news.ycombinator.com/item?id=47336615) + [github.com/iamevandrake/opensoul](https://github.com/iamevandrake/opensoul)

## Gotchas

- **MCP and A2A solve different problems — don't conflate them.** MCP is for tools and data sources. A2A is for inter-agent coordination. Using MCP for agent-to-agent handoffs works but is the wrong abstraction; using A2A for tool calling is awkward. Pick the right protocol for the boundary type.
- **"Context noise" beats "context starvation."** MCP provides the transport pipes, but teams still need orchestration valves — intent routing, relevance filtering, and priority queuing — to prevent the LLM from being overwhelmed with tool output. Build the intelligent orchestration layer on top of the protocol, not instead of it.
- **Protocol ratification ≠ production readiness for your use case.** The Linux Foundation governance reduces abandonment risk, but MCP's SDK ecosystem (especially for niche enterprise systems) is still maturing. Check SDK language support (Python dominant, TypeScript growing, Go sparse) before committing.
