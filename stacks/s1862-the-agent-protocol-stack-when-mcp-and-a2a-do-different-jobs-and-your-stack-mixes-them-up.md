# S-1862 · The Agent Protocol Stack — When MCP and A2A Do Different Jobs and Your Stack Mixes Them Up

You read that MCP won the protocol war. You deployed it everywhere — tools, data sources, *and* agent-to-agent communication. Your agents are calling each other over MCP. It works. Until it doesn't: bidirectional collaboration breaks, long-running negotiations hang, agent roles blur with tool roles, and your observability stack shows activity you can't attribute. The problem is not MCP. The problem is that MCP and A2A solve *different* communication problems, and the stack that works for model-tool integration is the wrong stack for agent-agent collaboration.

## Forces

- **MCP and A2A are not competitors — they operate at different layers.** MCP connects a model to external capabilities (tools, data, prompts). A2A connects agents to each other for negotiation, delegation, and shared-task execution. Conflating them is like using HTTP for peer-to-peer file sharing instead of BitTorrent: technically possible, structurally wrong.
- **Protocol selection is a composition decision, not a shopping decision.** Most production stacks need both — but at different boundaries. Using one protocol everywhere is the failure pattern that operators hit first.
- **The tooling ecosystem assumes you know which layer you're in.** MCP clients, A2A agents, and the servers that sit behind them have different capability expectations, state models, and failure semantics. Mixing them without awareness produces invisible semantic drift.
- **Governance consolidation clarifies but doesn't simplify.** ACP merged into A2A (September 2025, Linux Foundation), leaving two surviving protocols under AAIF and LF AI & Data. The choice is clearer; the composition is still non-trivial.

## The move

### Understand the two-layer model

| Layer | Protocol | Connects | Model |
|-------|----------|----------|-------|
| **Model → Capability** | **MCP** | LLM to tools, data, resources | Client-server: one caller, one or more servers |
| **Agent → Agent** | **A2A** | Agent to agent | Bidirectional negotiation: roles, task delegation, status push |

MCP is a **capability access protocol**. An agent uses MCP to call `search_database`, `create_issue`, `send_email`. The agent is the caller; the server is the tool.

A2A is a **collaboration protocol**. An agent uses A2A to hand a subtask to a peer, negotiate a shared context, or push status updates back to a coordinating agent. Both sides are agents with roles.

### The failure modes

**Conflation.** Using MCP for agent-agent handoffs. Works for one-shot tool-like calls but breaks for: bidirectional streaming, role negotiation, long-running task delegation, status push, and multi-turn collaboration where both sides contribute to the same task state.

**Over-deployment.** Running A2A for tool access. A2A has no tool-invocation semantics — it wraps capability in agent roles, which adds unnecessary ceremony for simple tool calls and makes schema negotiation harder.

**No protocol boundary.** When a system grows from single-agent-tool to multi-agent, teams retrofit MCP everywhere instead of identifying where the communication topology shifts from client-server to peer-to-peer.

### The decision tree

```
Does the capability live outside the agent?
  YES → Is the caller an agent delegating to another agent?
    YES → A2A (agent-agent collaboration)
    NO  → MCP (model-tool access)
  NO  → Is this a tool or data resource?
    YES → MCP
    NO  → Is this peer-to-peer collaboration?
      YES → A2A
      NO  → Re-examine the architecture
```

### The composition pattern

A production stack typically runs both:

```text
Agent (coordinator)
  ├── MCP client → Database server (read/write)
  ├── MCP client → GitHub server (code, PRs)
  ├── MCP client → Slack server (notifications)
  │
  ├── A2A client → Researcher agent (subtask: gather data)
  └── A2A client → Writer agent (subtask: draft report)
      │
      └── A2A client → Reviewer agent (subtask: quality check)
```

The coordinator uses MCP for capability access. It uses A2A for delegating to peers who have their own MCP connections. The two protocols compose at the agent boundary, not inside the same call chain.

### Implementation considerations

- **A2A requires role assignment.** Each agent announces its capabilities and accepts or declines tasks. MCP has no equivalent — a tool doesn't negotiate; it executes or errors.
- **MCP state is per-connection; A2A state is per-task.** MCP sessions are tied to the client-server pair. A2A task state follows the task across agents.
- **Observability surfaces differ.** MCP telemetry tracks tool call latency, schema drift, and response poisoning. A2A telemetry tracks delegation chains, role resolution, and inter-agent latency. Most APM tools conflate these unless you've labeled the protocol boundary.
- **Server count is not the same as agent count.** An MCP server can serve many agents. An A2A agent typically serves one task or role. Mixing these cardinalities in capacity planning produces false ceilings.

### The tell

Your stack is conflating protocols if you see: tool-like names in your agent delegation logs (`agent_B.call_tool(search_database)` inside an agent), agents calling other agents through MCP client libraries, or no distinction between "which tool was called" and "which agent was delegated to" in your traces.

## Receipt

> Receipt pending — 2026-07-30

## See also

- [S-10 — MCP](/opt/data/handbook/stacks/s10-mcp.md): The foundational tool-access protocol
- [S-1853 — The Handoff Contract Stack](/opt/data/handbook/stacks/s1853-the-handoff-contract-stack-when-your-agent-hands-off-confidence-without-evidence.md): Structured handoffs between agents — complements A2A
- [S-999 — The Silent Tool Catalog](/opt/data/handbook/stacks/s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-your-agent-breaks.md): MCP schema drift — related operational surface
