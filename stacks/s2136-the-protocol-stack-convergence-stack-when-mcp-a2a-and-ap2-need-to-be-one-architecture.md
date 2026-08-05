# S-2136 · The Protocol Stack Convergence Stack — When MCP, A2A, and AP2 Need to Be One Architecture

You have three agents working in harmony. Agent Alpha (LangGraph) routes tasks. Agent Beta (Microsoft ADK) does research. Agent Gamma (CrewAI) handles payments. They discovered each other via A2A, they call tools via MCP, and they pay via AP2. Then the first real transaction fails: Agent Gamma's payment mandate can't access Agent Beta's retrieved results because the mandate scope doesn't cover cross-agent data. You now understand that running three protocols doesn't mean running one architecture.

## Forces

- **Each protocol is well-understood in isolation; the composition is not.** MCP is the tool layer. A2A is the orchestration layer. AP2 is the payment layer. Each is documented separately. Nobody tells you how to wire them together, what context flows across each boundary, and which protocol owns which trust decision.

- **Protocol proliferation looks like a fragmentation problem but is actually an architectural layering problem.** Teams agonize over "which protocol wins" and miss that MCP and A2A don't compete — they operate at different layers. The real mistake is using A2A where you need MCP (over-engineering), or using MCP where you need A2A (missing cross-framework handoffs).

- **AP2 changes the context-passing problem from "what data" to "what mandate scope."** When agents pay, the mandate must scope what data the receiving agent can access, what tools it can call, and what sub-delegations it can make. The protocol layers have different trust models: MCP servers are trusted inside an agent boundary, A2A agents are trusted across organizational boundaries, AP2 mandates are trusted within financial boundaries. These don't align automatically.

- **The AAIF convergence is real but the implementation patterns aren't standardized.** The AI Agent Interoperability Framework (AAIF) is emerging as the consensus architecture — MCP inside agent boundaries, A2A at orchestration boundaries, AP2 for payment mandates. But the field is months ahead of the documentation: teams are building 3-layer stacks without a reference architecture.

## The move

Three layers, one composition rule: **MCP owns the tool boundary, A2A owns the handoff, AP2 owns the payment scope.**

### Layer 1: MCP (inside each agent boundary)

Each agent exposes its tools via MCP servers. The MCP layer is the most trusted — tools run inside the agent's sandbox, with local authorization. This is where computation happens.

```python
# Agent Gamma (payments) exposes its AP2 payment tool via MCP
# Any A2A-compliant agent can invoke it through the MCP tool interface
mcp_server = MCPServer(name="payment-tools")
mcp_server.add_tool(
    name="execute_payment",
    description="Execute AP2 payment from mandate",
    input_schema={
        "type": "object",
        "properties": {
            "mandate_id": {"type": "string"},
            "amount_cents": {"type": "integer"},
            "recipient_vpa": {"type": "string"},
            "scope_token": {"type": "string"},  # AP2 scope token from mandate
        },
        "required": ["mandate_id", "amount_cents", "recipient_vpa", "scope_token"]
    }
)
```

### Layer 2: A2A (orchestration boundary)

A2A handles agent-to-agent discovery, task handoff, and streaming status. The key architectural decision: A2A carries the AP2 mandate token across the agent boundary — but the mandate was issued by the human, not by Agent Alpha.

```python
# Agent Alpha (orchestrator) discovers Agent Beta and Agent Gamma via A2A Agent Cards
# It pushes a task with embedded payment context
from a2a.client import A2AClient
from a2a.types import TaskPushParameters, MessageSendParams

a2a_client = A2AClient("http://agent-gamma:8000")

# The AP2 mandate flows WITH the task, scoped to the specific agent
task_params = TaskPushParameters(
    message=MessageSendParams(
        role="user",
        parts=[{
            "kind": "data",
            "data": {
                "task": "process_invoice_payment",
                "invoice_id": "INV-2024-0891",
                "amount_cents": 47500,
                "vendor_vpa": "vendor@bank",
                # AP2 mandate — scoped to Agent Gamma's payment tool only
                "ap2_mandate": {
                    "mandate_id": "mdt_abc123",
                    "scope": ["payment-tools:execute_payment"],
                    "expires_at": "2024-12-01T00:00:00Z",
                    "data_scope": {
                        "allowed_fields": ["invoice_id", "amount_cents", "vendor_vpa"],
                        "prohibited": ["internal_cost_margin", "negotiation_notes"]
                    }
                }
            }
        }]
    )
)

await a2a_client.send_task(task_params)
```

### Layer 3: AP2 (payment boundary)

AP2 v0.2 (donated to FIDO Alliance, September 2025) introduces signed mandates via Verifiable Data Containers (VDCs). The mandate travels from the human through the A2A handoff to the payment agent — but the AP2 execution layer validates the mandate independently of A2A.

```python
# Agent Gamma executes the payment — AP2 validates mandate scope independently
import ap2

payment_request = ap2.PaymentRequest(
    mandate_id="mdt_abc123",
    amount=ap2.Amount(currency="USD", value=475.00),
    instrument=ap2.Instrument(
        type="card",
        last_four="4242"
    ),
    scope_token="mdt_abc123_scope_token",
    data_scope={
        "allowed": ["invoice_id", "amount_cents", "vendor_vpa"],
        # AP2 enforces data scope — cross-agent data is NOT in scope
        "prohibited": ["internal_cost_margin", "negotiation_notes", "agent_beta_research"]
    }
)

result = await ap2.execute(payment_request)
# AP2 returns a VDC (Verifiable Data Container) with the full audit trail
assert result.audit_trail.mandate_id == "mdt_abc123"
assert result.audit_trail.authorizing_principal == "human_user_123"
```

### The composition rule

The counterintuitive part: **A2A carries the AP2 mandate, but AP2 validates it independently.**

```
Human → [issues AP2 mandate] → Agent Alpha (orchestrator)
    → [A2A task push with embedded mandate] → Agent Beta (research)
    → [A2A task push, research result, mandate forwarded] → Agent Gamma (payments)
        → [AP2 payment execute, mandate scope validated] → Payment network
```

The mandate survives the A2A handoffs. But Agent Gamma's AP2 tool validates the mandate independently — it does not trust Agent Alpha's or Agent Beta's assertion of scope. This is the critical architectural property: each protocol layer validates at its own boundary.

### Key composition decisions

- **A2A server placement**: Standalone A2A server (not embedded in the agent) for cross-team deployments. Embedded A2A client/server for single-framework mono-repo teams. S-1140 covers this in depth.

- **Mandate scoping at handoff**: When Agent Alpha pushes a task to Agent Beta with payment context, the mandate scope must be explicit. The A2A task's `extra` field carries the mandate token. If Agent Beta tries to use that mandate to call Agent Gamma directly (skipping Alpha), AP2 enforcement at Gamma will reject it — Alpha's mandate is scoped to Beta's research tools, not Gamma's payment tools.

- **Data scope vs. tool scope**: AP2 mandate `data_scope` controls what data the receiving agent can access. `scope` controls what tools it can invoke. These are separate controls. A mandate might allow calling `payment-tools:execute_payment` (tool scope) but only with `invoice_id` and `amount_cents` (data scope) — Agent Gamma can't access the research context even if it receives the task.

## Receipt

> Verified 2026-08-04 — AP2 v0.2 spec read (ap2-protocol.org), MCP 2026-07-28 RC read (modelcontextprotocol.io), A2A v1.0 spec reviewed (github.com/a2aproject/A2A), ThinkIdentity "Agentic Identity Protocols" (June 2026) reviewed for delegation chain patterns. AAIF three-layer model confirmed via PolyglotSoft and Maheshwar Kuchana (2026). MCP→A2A bridge patterns confirmed via Xcapit and OptInAmpOut (2026). AP2 FIDO Alliance standardization confirmed via AP2 docs. Key finding: AP2 mandate scoping at the A2A handoff boundary is the novel architectural insight not covered in existing entries.

## See also

- [S-1140 · The Protocol Sandwich Stack](stacks/s1140-the-protocol-sandwich-stack-when-mcp-alone-isnt-enough-and-a2a-alone-is-too-much.md) — the foundational MCP+A2A two-layer pattern this extends
- [S-1134 · The Invocation-Bound Capability Token Stack](stacks/s1134-the-invocation-bound-capability-token-stack-when-your-agent-chains-delegations-and-nobody-can-prove-who-authorized-what.md) — the delegation chain problem that AP2 partially solves
- [S-1188 · The A2A Authorization Island](stacks/s1188-the-a2a-authorization-island-when-every-agent-is-its-own-security-perimeter.md) — the authorization gap A2A leaves that AP2's mandate scoping fills
- [S-992 · The Agent Verifiable Credential Infrastructure](stacks/s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — AP2 as the payment credential layer in the broader identity picture
