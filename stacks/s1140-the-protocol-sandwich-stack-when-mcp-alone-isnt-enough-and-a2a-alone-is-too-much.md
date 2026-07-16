# S-1140 · The Protocol Sandwich Stack — When MCP Alone Isn't Enough and A2A Alone Is Too Much

Your agent framework ships with a perfectly functional MCP integration. You connect it to your database, your Slack, your GitHub. Then a second team deploys a specialist agent built on a different framework. Now they need to talk. You spend three weeks building a custom JSON-RPC bridge, an agent registry, and a shared authentication layer — and you've just re-invented A2A from scratch, badly.

In 2026, the production answer is a stacked protocol architecture: **MCP inside each agent boundary, A2A at the orchestration boundary**. ACP (IBM's Agent Communication Protocol) merged into A2A in September 2025, leaving the field with a clear two-layer model. MCP handles vertical tool integration. A2A handles horizontal agent coordination. The sandwich has two distinct layers, and confusing which layer you're working in is the #1 protocol mistake teams make.

## Forces
- Every major framework (LangGraph, CrewAI, Claude Agent SDK, Microsoft Agent Framework) has its own tool-calling convention — without a standard, integrations don't port
- MCP hit 97M monthly SDK downloads and is production-stable under Linux Foundation governance (AAIF), making it the de facto tool-integration standard
- A2A hit v1.0 and 24,000+ GitHub stars, enabling agent-to-agent discovery via Agent Cards and long-running task delegation — problems MCP was never designed to solve
- The protocol landscape is consolidating, not fragmenting — teams building custom bridges in 2026 are paying a cost that the standards already cover
- Both protocols now live under Linux Foundation oversight, removing the "which vendor wins?" governance risk that stalled earlier standardization efforts

## The move

**The Protocol Sandwich: two distinct layers, never conflated.**

| Layer | Protocol | Solves | Lives |
|-------|----------|--------|-------|
| Vertical | **MCP** | Agent → tool / data / API | Inside each agent boundary |
| Horizontal | **A2A** | Agent → agent discovery, delegation, status | Between agent boundaries |

### Layer 1: MCP — the tool-access standard

MCP (Model Context Protocol, Anthropic, 2024) defines a client-server contract where an MCP client connects to MCP servers exposing tools, resources, and prompts. Every major framework ships MCP client support. The ecosystem has 18,000+ indexed MCP servers.

```
# MCP: every agent has an MCP client connecting to local/remote servers
# (stdio transport for local, SSE/HTTP for remote)
```

```python
from mcp.client import MCPClient
from mcp.protocol import Tool, Resource

# Inside your agent — MCP client connects to tools
async with MCPClient("http://mcp-server:3000") as client:
    tools = await client.list_tools()
    # Same interface regardless of which framework built the server
    result = await client.call_tool("search_database", {"query": "Q3 revenue"})
```

### Layer 2: A2A — the agent-coordination standard

A2A (Agent-to-Agent Protocol, Google, 2025) defines how agents discover each other via Agent Cards (JSON documents advertising capabilities), delegate tasks, and handle long-running work with push notifications. It was designed to complement MCP, not replace it.

```
# A2A: agents discover each other via Agent Cards and delegate work
# (JSON-RPC 2.0 over HTTPS)
```

```python
from a2a.client import A2AClient
from a2a.types import AgentCard, TaskPushNotificationConfig

# Discover a remote agent via its Agent Card
async with A2AClient("https://analytics-agent.example.com/a2a") as client:
    card = await client.get_agent_card()
    # AgentCard advertises: name, capabilities, skills, version
    assert "financial-analysis" in card.capabilities.skills

    # Delegate a long-running task
    task = await client.send_task({
        "task_id": "q3-report-001",
        "input": {"query": "Q3 revenue by region", "format": "pdf"},
        "push_notify": TaskPushNotificationConfig(
            url="https://orchestrator.example.com/webhook"
        ),
    })
    # A2A handles status updates, completion, errors — not the agent
```

### The stacked architecture — the production default

```
┌──────────────────────────────────────────────────────┐
│  Orchestrator Agent (LangGraph)                       │
│                                                      │
│  ┌─ MCP client ──→ Database MCP server               │
│  ├─ MCP client ──→ GitHub MCP server                │
│  ├─ MCP client ──→ Slack MCP server                 │
│  └─ A2A client ──→ Specialist Agent (Claude SDK) ────┼─ MCP client ──→ Search
│                        └─ MCP client ──→ Calculator  │
└──────────────────────────────────────────────────────┘
```

Each agent boundary is self-contained with its own MCP tool integrations. A2A connects the orchestration layer to specialist agents — no custom bridges, no bespoke JSON-RPC.

### The anti-patterns

**1. Forcing agent-to-agent through MCP.**
MCP is not a messaging protocol. If you find yourself routing agent messages as MCP tool calls, you're working against the protocol. A tool call is a request-response. An agent handoff is a long-running task with status, push notifications, and potential for the delegating agent to query progress. A2A models this. MCP doesn't.

**2. Building a custom agent registry when A2A has Agent Cards.**
Agent Cards are JSON documents — hosted at `/.well-known/agent.json` — that advertise an agent's name, version, capabilities, skills, and authentication requirements. A2A client SDKs handle discovery natively. Custom registry implementations re-implement what the standard covers.

**3. Ignoring the governance risk of non-standard protocols.**
Protocols without multi-vendor governance are single-vendor liability. MCP, A2A, and ACP all moved to Linux Foundation oversight by Q1 2026. A custom JSON-RPC bridge in 2026 carries the maintenance burden and vendor-lock risk that the standards have already solved.

## Receipt
> Verified 2026-07-15 — MCP spec (2026-07-28 RC), A2A v1.0 (24k+ stars), Linux Foundation governance convergence confirmed via swarmsignal.net (2026), Zylos Research (2026-03-26), AgenticWire (2026-06-13), SkillGen (2026-05-22). MCP 97M monthly SDK downloads confirmed via SkillGen. ACP merged into A2A September 2025 confirmed via swarmsignal.net. Agent Card discovery and A2A client SDK patterns verified against published specs. Production-stacked architecture pattern (MCP inside agent boundary, A2A across boundaries) confirmed as dominant approach across 4 independent sources.

## See also
- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — foundational fan-out, pipeline, and supervisor patterns
- [S-10 · MCP](s10-mcp.md) — MCP client-server architecture, tool schemas, and resource/prompt primitives
- [S-614 · The Authorized Intent Chain](s614-the-authorized-intent-chain-when-agents-bypass-every-security-control.md) — security boundaries between agent layers
