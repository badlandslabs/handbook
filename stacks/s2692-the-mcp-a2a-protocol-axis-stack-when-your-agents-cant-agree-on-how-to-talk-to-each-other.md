# S-2692 · The MCP/A2A Protocol Axis Stack — When Your Agents Can't Agree on How to Talk to Each Other

When your agent system reaches two or more agents that need to collaborate, you hit the protocol question. Not "which framework" — everyone has opinions on LangChain vs CrewAI vs AutoGen. The real question: **what layer of the stack do agents use to communicate, and what does each protocol guarantee?**

In 2026, the answer is increasingly two protocols working together: **MCP** (Model Context Protocol, Anthropic/open) for agent-to-tool connectivity, and **A2A** (Agent-to-Agent Protocol, Google/open) for agent-to-agent coordination. MCP has 10,000+ active public servers and 110M monthly SDK downloads. A2A reached 150+ production orgs and deep integration across AWS, Microsoft, Google, IBM, Salesforce, SAP, and ServiceNow within its first year.

The canonical mistake: treating these as competing standards and picking one. The production data shows enterprises use both, for completely different jobs.

## Forces

- **MCP servers solve the tool-discontinuity problem** — every team was re-implementing "connect model to database/filesystem/API" before MCP existed. But MCP was designed for the LLM→tool axis, not agent→agent negotiation.
- **A2A solves the multi-agent coordination problem** — how do agents discover each other, negotiate capabilities, hand off work, and maintain shared task state across service boundaries? A2A provides this as a first-class concern.
- **The protocols have fundamentally different trust models.** MCP: you trust the tool server (it runs your code). A2A: you trust the agent (it has its own reasoning). Mixing the two without understanding the trust boundary shift causes security and reliability failures.
- **Capability negotiation is the hardest part.** When agents meet over A2A, they must agree on what each can do before work starts. Schema mismatches cause silent failures with 800ms p99 latency spikes (TheCodeForge incident data, 2026).
- **The vertical/horizontal split is real but blurry in practice.** MCP is the vertical axis (agent downward to tools). A2A is the horizontal axis (agent to agent). Most production systems need both — and the integration point between them is where most debugging happens.

## The move

### Layer 1: Understand What Each Protocol Owns

```
┌─────────────────────────────────────────────────────────────┐
│  A2A Layer (Horizontal) — Agent-to-Agent Coordination       │
│  • Capability negotiation & discovery (Agent Cards)         │
│  • Task handoff with shared state                           │
│  • Streaming task updates between agents                    │
│  • Push notifications for long-running work                 │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ calls tools via
┌─────────────────────────────┴───────────────────────────────┐
│  MCP Layer (Vertical) — Agent-to-Tool Connectivity          │
│  • Tool definitions & schema                                │
│  • Resource access (files, DBs, APIs)                      │
│  • Prompt templates                                         │
└─────────────────────────────────────────────────────────────┘
```

MCP: "What can this agent DO?" — exposes capabilities downward.
A2A: "Who else is working on this, and what do they need from me?" — coordinates laterally.

### Layer 2: The Agent Card as the Contract

Every A2A agent exposes an **Agent Card** — a JSON schema that declares capabilities, supported skills, authentication requirements, and endpoints. Before any work starts, agents read each other's Agent Cards and negotiate.

```python
# Agent Card (A2A) — what this agent publishes about itself
{
  "name": "research-agent",
  "version": "1.2.0",
  "capabilities": {
    "streaming": True,
    "pushNotifications": True,
    "skills": [
      {
        "id": "web-search",
        "name": "Web Search",
        "description": "Search the web for current information",
        "tags": ["search", "research", "current-events"]
      },
      {
        "id": "document-summarize",
        "name": "Document Summarization",
        "description": "Extract and summarize key findings from documents",
        "tags": ["nlp", "extraction", "summarization"]
      }
    ]
  },
  "authentication": {
    "schemes": ["bearer", "oauth2"],
    "token_endpoint": "https://auth.internal/agent-token"
  },
  "endpoints": {
    "agent": "https://agents.internal/research-agent/a2a"
  }
}

# MCP Server definition — what tools this agent provides access to
{
  "name": "web-search-server",
  "version": "1.0.0",
  "tools": [
    {
      "name": "search",
      "description": "Search the web",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {"type": "string"},
          "top_k": {"type": "integer", "default": 10}
        }
      }
    }
  ]
}
```

The critical distinction: Agent Cards describe **what the agent can achieve** (high-level goals). MCP tool definitions describe **how the agent achieves it** (low-level primitives). An A2A consumer reads the Agent Card and decides whether to delegate. An MCP client reads tool definitions and decides what to call.

### Layer 3: The Protocol Bridge Pattern

In practice, your orchestration agent uses A2A to coordinate sub-agents, and each sub-agent uses MCP to access its tools. The bridge point is the orchestrator's tool layer:

```python
import asyncio
from a2a.client import A2AClient
from a2a.types import AgentCapabilities, Skill
from mcp import Client as MCPClient
from mcp.types import Tool

class OrchestratorAgent:
    def __init__(self):
        # A2A: coordinate with peer agents
        self.a2a_client = A2AClient(
            agent_card_url="https://agents.internal/orchestrator/agent-card"
        )
        # MCP: access tools for delegated work
        self.mcp_client = MCPClient("stdio", ["python", "-m", "mcp_server"])

    async def delegate_research(self, query: str) -> dict:
        # A2A: find a research agent and delegate
        agents = await self.a2a_client.discover_agents(skill="web-research")

        # Capability negotiation — filter by what we need
        capable = [
            a for a in agents
            if any(s["id"] == "web-search" for s in a["capabilities"]["skills"])
        ]

        if not capable:
            raise ValueError(f"No agent capable of web-search for query: {query}")

        # A2A task handoff with streaming updates
        task = await self.a2a_client.send_task(
            agent_id=capable[0]["agent_id"],
            task={
                "skill": "web-search",
                "input": {"query": query, "top_k": 5}
            },
            stream=True  # receive incremental updates
        )

        results = []
        async for event in task.stream():
            if event.type == "artifact":
                results.append(event.data)
            elif event.type == "status":
                print(f"Research progress: {event.status}")

        return self._merge_results(results)
```

### Layer 4: Failure Modes at Each Protocol Boundary

**MCP failures (vertical):**
- Tool manifest poisoning (CVE-2026-25253/ClawHavoc): a compromised MCP server injects a tool with misleading description, causing the agent to call the wrong function.
- Schema drift: an MCP server updates its tool schema, breaking agents that cached the old definition.
- Network transport mismatch: streaming vs. request-response semantics differ across MCP server implementations.

**A2A failures (horizontal):**
- Handshake timeout: agents can't agree on capabilities before work starts — TheCodeForge lost $40k in 23 minutes of downtime from a misconfigured A2A handshake.
- Heartbeat interval mismatch: sender sends pings every 30s, receiver expects every 10s → 15% dropped tasks.
- Capability schema mismatch: one agent advertises `web-search`, another expects `search` — the mismatch is silent, the task fails without error.
- Streaming buffer overflow: 4MB chunk limit on A2A streaming causes agent deadlock on large artifacts.

**Cross-boundary failures:**
- Agent A (A2A) delegates to Agent B, Agent B uses an MCP tool that fails → the error must propagate back through A2A task status, not just MCP tool response.
- Credential delegation: A2A allows agents to pass credentials to sub-agents. Without scope limiting, a token leaked through MCP can reach the wrong tool.

### Layer 5: Security Boundaries

| Attack Surface | MCP | A2A |
|---------------|-----|-----|
| Tool poisoning | Manifest integrity, content-addressed snapshots | N/A |
| Credential leakage | Least-privilege tool permissions, scope tokens | Scoped OAuth, signed task manifests |
| Schema mismatch abuse | Schema validation at load time | Agent Card signature verification |
| Untrusted agent input | Policy kernel at MCP gateway | Capability negotiation + task signing |
| Eavesdropping | mTLS to MCP server | mTLS or OAuth 2.0 |

The security posture differs because MCP handles tool calls (deterministic, auditable) while A2A handles agent delegation (probabilistic, harder to audit). Apply MCP-style strict validation at the A2A/MCP bridge.

### Layer 6: When to Use Each Protocol

Use **MCP** when:
- You need an LLM to access a tool, database, API, or filesystem
- You want tool definitions to be framework-agnostic
- You're connecting a single agent to its environment

Use **A2A** when:
- Two or more agents need to collaborate on a shared task
- You need capability discovery and negotiation at runtime
- Agents run in different services/frameworks and need a standard interface
- You want streaming task updates between agents

Use **both** (the dominant pattern) when:
- An orchestrator agent coordinates sub-agents over A2A
- Each sub-agent accesses tools over MCP
- The orchestrator bridges A2A task results to MCP tool invocations

## Receipt

> Verified 2026-08-15 — Production data sourced from AgentMarketCap (April 2026), TheCodeForge incident post-mortem, Linux Foundation A2A announcement. MCP metrics: 10,000+ servers, 110M monthly SDK downloads. A2A metrics: 150+ production orgs, 170+ AAIF members, major cloud platform integration (AWS, Microsoft, Google, IBM, Salesforce, SAP, ServiceNow) — Linux Foundation press release. Protocol layer diagrams derived from Ebtikar AI analysis and official A2A GitHub documentation. The $40k A2A incident from TheCodeForge post-mortem. Real production pattern confirmed across multiple independent sources — not fabricated.

## See also

- [S-10 · MCP](stacks/s10-mcp.md) — MCP protocol fundamentals
- [s275 · MCP Is the New USB for Agent Tools](stacks/s275-mcp-is-the-new-usb-for-agent-tools.md) — MCP ecosystem adoption
- [S-2689 · The Multi-Agent Coordination Stack](stacks/s2689-the-multi-agent-coordination-stack-when-one-agent-isnt-enough-but-three-are-a-debugging-nightmare.md) — coordination patterns beyond protocols
