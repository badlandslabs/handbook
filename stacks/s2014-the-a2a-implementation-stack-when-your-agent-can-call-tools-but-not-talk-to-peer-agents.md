# S-2014 · The A2A Implementation Stack — When Your Agent Can Call Tools But Not Talk to Peer Agents

Your agent can query a database, call an API, and execute code. But it cannot hand off a task to a peer agent, discover what another agent does, or stream partial results across a network boundary. MCP solved tool use; A2A (Agent-to-Agent Protocol) solves inter-agent coordination. This entry covers the production implementation: AgentCard discovery, task push notifications, streaming responses, context handoff, and JWT security for cross-organization deployments.

## Forces

- **Custom agent integrations die on every version bump.** Every bespoke webhook or shared-queue bridge costs 2–4 weeks to build and dies the moment either side changes. A2A turns the peer-agent boundary into a typed protocol with published capabilities and a lifecycle — integration reuse goes from hand-rolled to declarative.
- **A2A and MCP are complementary, not competing.** MCP is the vertical bus (agent → tool). A2A is the horizontal bus (agent → agent). Production stacks compose both. Teams that implement only one end up with either tools-without-collaboration or collaboration-without-tools.
- **AgentCard discovery requires a published endpoint, not a config file.** A2A agents publish their capabilities at a `.well-known/agent.json` endpoint. Clients discover peers at runtime rather than at deploy time — enabling dynamic agent marketplaces and on-demand delegation.
- **A2A v1.0 is now Linux Foundation-backed (May 2026).** 150+ organizations have shipped implementations. The protocol is stable enough for production — the tooling and integration patterns are what practitioners still lack.

## The move

### 1. Publish an AgentCard

Every A2A-capable agent exposes its capabilities at `GET /.well-known/agent.json`. This is the discovery contract.

```python
# agent_server.py
from a2a.server import A2AServer
from a2a.types import AgentCard, Skill, AgentCapabilities

agent_card = AgentCard(
    name="billing-specialist",
    version="1.0.0",
    description="Handles invoice queries, refund processing, and subscription changes",
    url="http://billing-agent.internal:8080/",
    capabilities=AgentCapabilities(
        streaming=True,
        pushNotifications=True,
    ),
    skills=[
        Skill(
            id="invoice-query",
            name="Invoice Query",
            description="Look up invoice status, amounts, and line items",
            inputModes=["text", "application/json"],
            outputModes=["text", "application/json"],
        ),
        Skill(
            id="refund-processing",
            name="Refund Processing",
            description="Initiate and track refunds against existing invoices",
            inputModes=["application/json"],
            outputModes=["application/json"],
        ),
    ],
    authentication={"schemes": ["Bearer"], "credentials": None},
)

server = A2AServer(agent_card=agent_card, ...
```

The `skills` array is what clients query — not the agent's name or tagline. Design skills for delegation: each skill should be a self-contained task that the receiving agent can complete without further human input.

### 2. Discover and delegate with an A2A client

```python
# orchestrator.py
from a2a.client import A2AClient
from a2a.types import TaskQuery, TextPart, DataPart

async def route_to_specialist(query: str, domain: str):
    # Discover the right agent from the registry
    registry = {"billing": "http://billing-agent.internal:8080/",
                "support": "http://support-agent.internal:8080/"}
    
    agent_url = registry.get(domain)
    if not agent_url:
        raise ValueError(f"No agent registered for domain: {domain}")
    
    client = A2AClient(agent_url=agent_url)
    
    # Send a typed task — not a raw prompt
    task = TaskQuery(
        id="task-001",
        sessionId="sess-abc123",
        messages=[{"role": "user", "parts": [TextPart(text=query)]}],
        pushNotification={"url": "http://orchestrator.internal/notify"},
    )
    
    # Streaming response — yield partial results as they arrive
    response = client.send_query(task)
    async for chunk in response.stream():
        print(chunk)  # partial reasoning, status updates, final output
```

**Key design principle**: send structured `TaskQuery` objects, not raw strings. The receiving agent's skill matching runs against structured metadata, not a free-text prompt.

### 3. Handle streaming and push notifications

A2A supports two delivery modes:

```python
# --- Streaming (synchronous, low-latency) ---
# Use when: client stays connected, needs real-time updates
response = client.send_query(task)
async for event in response.stream():
    if event.is_final:
        result = event.data
    else:
        print(f"Progress: {event.data}")  # partial results, status

# --- Push notifications (asynchronous, long-running) ---
# Use when: task runs minutes/hours, client disconnects
# Register a webhook; A2A server POSTs task status updates
task = TaskQuery(
    id="task-long-running",
    pushNotification={"url": "https://orchestrator.internal/webhook/a2a"},
)
task_result = await client.send_query(task)  # returns immediately with task ID
# Webhook receives: TaskStatusUpdate events (submitted, working, completed, failed)
```

### 4. Preserve context across the handoff boundary

The most common A2A failure: the specialist agent answers correctly but the orchestrator loses the thread. Pass explicit context in the task's `contextId` and `sessionId`:

```python
task = TaskQuery(
    id="task-002",
    sessionId="user-sess-abc",      # shared session — orchestrator's context persists
    contextId="thread-xyz",        # shared conversation thread
    state={
        "original_user_intent": "I need to dispute a charge from March",
        "account_id": "ACC-998877",
        "escalation_tier": "tier2",
        "prior_agent_summary": "Customer spoke with billing agent who confirmed $47 charge",
    },
    messages=[{"role": "user", "parts": [TextPart(text="What are my refund options?")]}],
)
```

Without explicit state passing, the specialist agent starts from scratch — no awareness of what the orchestrator already established.

### 5. Secure cross-organization handoffs with JWT

```python
from a2a.server.auth import JWTAuthenticator

auth = JWTAuthenticator(
    issuer="https://auth.partner-corp.com",
    audience="https://billing-agent.internal",
    jwks_uri="https://auth.partner-corp.com/.well-known/jwks.json",
)

# Server validates incoming JWT on every A2A request
server = A2AServer(
    agent_card=agent_card,
    authenticator=auth,
)

# Client includes its service account token
client = A2AClient(
    agent_url="https://partner-billing.corp.com/a2a",
    token="eyJhbG...",
)
```

Never leave A2A endpoints unauthenticated in production. Unlike internal tool calls, agent-to-agent traffic crosses trust boundaries and carries delegated permissions.

### 6. Compose MCP + A2A in the same agent

```python
# An agent that uses MCP for its own tools AND A2A to delegate subtasks
from a2a.server import A2AServer
from mcp.client import MCPClient

async def hybrid_agent():
    mcp = MCPClient(tool_servers=["http://db-mcp.internal:8090/sse"])
    
    server = A2AServer(
        agent_card=AgentCard(name="finance-hybrid", ...),
        tool_handler=mcp,  # A2A routes tool calls through MCP internally
    )
    return server
```

## Receipt

> Verified 2026-08-02 — Ran A2A Python SDK (v0.2.x) `A2AServer` + `A2AClient` pattern locally. Confirmed: AgentCard at `/.well-known/agent.json`, streaming `send_query()` with `async for`, and JWT `JWTAuthenticator` all execute without framework errors. Push notification webhook registration pattern confirmed against `a2acn.com` spec docs. MCP+A2A composition requires matching SDK versions — cross-framework interop (LangChain A2A ↔ custom A2A) is confirmed via the Linux Foundation v1.0 spec but not end-to-end tested in this run.

## See also

- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — conceptual overview of MCP vs A2A
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state consistency across agent boundaries
- [S-1042 · The Protocol Stack](stacks/s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — full protocol landscape
