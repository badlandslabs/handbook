# [S-1104] · The Three-Layer Protocol Stack — When Your Agent Lives in a World of Three Simultaneous Protocols

Your agent needs to call a tool, delegate to a colleague agent, and stream results to a user — simultaneously, reliably, across a process crash. In 2024, you could handle one of these with a custom integration. In mid-2026, you need all three protocols running at once, and they need to survive the same failure that kills a regular process. The reference architecture is a three-layer protocol stack, backed by durable execution, and teams that build it piece by piece without understanding the seams get systems that work in demos and fail in production.

## Forces

- **Agents now span three distinct communication dimensions simultaneously.** An agent calls tools (MCP), hands work to other agents (A2A), and reports back to users (A2UI) — all within a single task. Treating these as separate concerns means three independent failure modes per task.
- **Durable execution is the fourth layer nobody planned for.** A 10-step agent task that crashes at step 8 doesn't resume — it restarts from step 1, duplicating side effects and wasting tokens. Temporal, Inngest, and Azure Durable Task have emerged as the reliability substrate for agent runtimes, but they don't integrate with the protocols automatically.
- **The protocol trio (MCP, A2A, A2UI) is production-ready, but the seams are undocumented.** MCP reached ecosystem ubiquity in 2025. A2A hit v1.0 in April 2026 with 150+ orgs and native Google Cloud/Azure/AWS support. A2UI shipped v0.8 with a typed component catalog. They are individually stable. How they compose under failure is the hard part.
- **ACP is gone — A2A absorbed it in August 2025.** IBM's Agent Communication Protocol merged into A2A under the Linux Foundation. Any architecture still referencing ACP is building on deprecated spec. [S-414](s414-the-protocol-convergence-thesis.md) covers this convergence in detail.

## The Move

### Layer 1 — MCP: Agent → Tools

MCP is vertical, resource-oriented, stateless. An agent sends a JSON-RPC 2.0 request to an MCP server; the server queries a database, a Stripe API, a vector store, a filesystem. The agent waits synchronously for the response. MCP is the "hands" layer.

```python
# MCP client — agent calling a Stripe MCP server
from mcp import Client

async def get_customer_invoice(customer_id: str) -> dict:
    async with Client("stripe-mcp-server") as client:
        result = await client.call_tool(
            "stripe_get_invoice",
            arguments={"customer": customer_id, "status": "open"}
        )
        return result  # synchronous, stateless
```

MCP servers are NOT agents. They are tool facades. [S-10](s10-mcp.md) covers MCP in depth.

### Layer 2 — A2A: Agent ↔ Agent

A2A is horizontal, intent-oriented, stateful. An agent discovers another agent via a signed **Agent Card** (a JSON document published at a well-known endpoint), negotiates a task with capability matching, delegates work, and streams intermediate results back. A2A handles multi-turn handoffs, task state updates, and completion signals that MCP cannot model.

Key A2A v1.0 additions that changed production readiness:
- **gRPC transport** alongside HTTP — critical for high-throughput agent meshes
- **Signed Agent Cards** — cryptographically signed capability manifests that prevent agent spoofing
- **Python SDK** — mature enough for production use, not just experimentation

```python
# A2A client — planning agent delegating to a billing specialist agent
from a2a.client import A2AClient
from a2a.types import TaskSendParams, AgentCard

# Discover the billing agent via its signed Agent Card
billing_card: AgentCard = await A2AClient.discover_agent(
    "https://billing.internal/agent-card.json"
)

# Delegate a multi-step billing investigation
task = await client.send_task(TaskSendParams(
    task={
        "id": "investigation-0042",
        "type": "task",
        "intent": "Investigate why customer acme-corp was charged twice on 2026-07-10",
        "context": {"customer_id": "cus_acme_corp", "date": "2026-07-10"},
        "skill_requirements": ["stripe", "accounting", "refund-policy"],
        "priority": "high"
    },
    recipients=[billing_card.agent_id]
))

# Stream intermediate results back from the specialist
async for event in task.stream():
    if event.type == "artifact_update":
        print(f"[{event.source}] Partial result: {event.payload}")
    elif event.type == "task_complete":
        print(f"[{event.source}] Done: {event.payload}")
```

This is categorically different from an MCP tool call. The billing agent is an autonomous agent — it reasons, replans, calls its own MCP tools, and reports back with a structured finding. [S-1040](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) covers the distinction.

### Layer 3 — A2UI: Agent → User

A2UI is the missing user-facing layer. MCP gives agents tools; A2A gives agents colleagues; A2UI gives agents a structured way to talk to users — streaming progress, rendering interactive components, and receiving typed user actions without resorting to raw text or HTML injection.

The A2UI v0.8 spec introduced the **typed component catalog**: agents emit structured component descriptors (think "data table with sortable columns" or "form with validation") rather than raw HTML. Clients render with their own widgets. This eliminates the HTML injection surface while enabling rich interactive UIs.

```python
# A2UI — agent streaming a structured UI to the user
from a2ui import Server, component, A2UIEvent

async def run_billing_review(customer_id: str):
    server = Server(catalog="a2ui-components-v08")

    @component("billing_summary_table")
    def billing_table(charges: list[dict]):
        """Renders a table of charges with refund action buttons."""
        return {
            "type": "table",
            "columns": ["date", "amount", "status", "action"],
            "rows": charges,
            "interactive": True  # client renders clickable refund buttons
        }

    await server.emit(A2UIEvent(
        component=billing_table,
        arguments={"charges": await fetch_charges(customer_id)},
        stream_id="billing-review-0042"
    ))

    # Receive user action (refund button click) as a typed event
    user_action = await server.receive()
    if user_action.action == "request_refund":
        await process_refund(user_action.charge_id)
```

A2UI completes the three-layer reference architecture: MCP (tools) + A2A (agents) + A2UI (users). [S-789](s789-the-a2ui-protocol-the-missing-user-facing-layer.md) covers A2UI in depth.

### The Reliability Layer — Durable Execution

All three protocol layers share the same fundamental failure mode: the worker process dies mid-task. MCP calls timeout. A2A handoffs are interrupted. A2UI streams terminate. Durable execution (Temporal, Inngest) solves this by checkpointing progress and replaying deterministic control flow from the last successful step.

```python
# Temporal workflow wrapping the three-layer stack
from temporalio import workflow, activity
from temporalio.common import RetryPolicy

@workflow.defn
class BillingInvestigationWorkflow:
    @workflow.run
    async def run(self, customer_id: str) -> dict:
        # Step 1: Discover and delegate via A2A (deterministic — safe to replay)
        billing_task = await workflow.execute_activity(
            a2a_delegate_investigation,
            customer_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        # Step 2: Fetch Stripe data via MCP (idempotent with idempotency key)
        invoice_data = await workflow.execute_activity(
            mcp_fetch_invoice,
            billing_task.invoice_id,
            start_to_close_timeout=timedelta(seconds=30)
        )

        # Step 3: Stream summary to user via A2UI
        await workflow.execute_activity(
            a2ui_stream_summary,
            {"task_id": billing_task.id, "invoice": invoice_data},
            start_to_close_timeout=timedelta(seconds=10)
        )

        return billing_task.findings
```

If the Temporal worker crashes after step 1 but before step 3, Temporal replays steps 1–2 using cached outputs and resumes from step 3. No duplicate Stripe API calls. No duplicate A2A delegation. No wasted tokens.

This is the production pattern that transforms three useful protocols into a reliable system.

## The Three-Layer Seam Problem

The architectural mistake is building each layer independently and wiring them together with ad-hoc glue code. The real challenge is the seams:

| Seam | Problem | Solution |
|------|---------|----------|
| MCP → A2A | An A2A-handoffered agent's MCP calls inherit the outer task's auth context | Propagate scoped credentials through A2A task context; use short-lived MCP session tokens |
| A2A → A2UI | When A2A agents delegate subtasks, A2UI events need a correlated `stream_id` across agent boundaries | Emit `parent_stream-id` in A2UI events so the client can correlate multi-agent work |
| Any → Durable Execution | MCP calls and A2A handoffs inside a Temporal workflow need idempotency keys to survive replay | Attach `idempotency_key` to every external call; Temporal deduplicates on replay |
| A2A → MCP | The A2A spec allows agents to call MCP servers on behalf of the delegating agent — security boundary risk | Enforce least-privilege MCP scopes per A2A skill requirement; never propagate admin tokens across agent handoffs |

## Receipt

> Verified 2026-07-14 — Concept validated against: A2A Protocol v0.3 spec (WOWHOW Cloud, Apr 2026), A2A v1.0 production deployments (Extency blog, May 2026), A2UI v0.8 component catalog (github.com/a2ui-project), Temporal durable execution patterns (Zylos Research, Apr 2026; CallSphere blog, Mar 2026). Durable execution integration pattern is architectural reasoning rather than a runnable receipt — apply to your MCP+A2A stack and verify idempotency behavior empirically.

## See also

- [S-414 · The Protocol Convergence Thesis](s414-the-protocol-convergence-thesis.md) — MCP + A2A + AP2 convergence landscape
- [S-1042 · The Protocol Stack](s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — tool integrations vs. agent handoffs
- [S-789 · The A2UI Protocol](s789-the-a2ui-protocol-the-missing-user-facing-layer.md) — A2UI typed component catalog
- [S-824 · The Durable Session Stack](s824-the-durable-session-stack-when-your-agent-runs-that-outlive-their-connections.md) — durable sessions
