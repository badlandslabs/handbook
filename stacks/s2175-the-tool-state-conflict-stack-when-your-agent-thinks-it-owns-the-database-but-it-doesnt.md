# S-2175 · The Tool State Conflict Stack — When Your Agent Thinks It Owns the Database But It Doesn't

Your billing agent and your provisioning agent both read the customer's plan tier at 10:00:00. The billing agent sees "basic" and schedules a downgrade. The provisioning agent sees "basic" and starts moving the workload. Two seconds later, the customer upgrades via the API — a human upgrade that was processed between the two reads. Both agents committed their changes. The customer's account now has contradictory state: downgraded billing but upgraded infrastructure. No error was raised. No exception fired. The agents followed their instructions perfectly. The database is now lying to you.

This is the tool state conflict: agents interact with shared mutable state through tools, but the tools expose no concurrency semantics. The agent paradigm assumes the world is quiescent between tool calls. It isn't.

## Forces

- **Agents operate under the assumption of sequentiality.** A tool call returns; the agent reasons; the next tool call starts. In production, other agents, background jobs, and human operators are mutating the same state simultaneously. The agent's decision is always based on a snapshot that was already stale when it was taken.
- **Tool schemas don't expose transaction boundaries.** MCP, OpenAPI, and function-calling schemas describe inputs and outputs — not isolation levels, not consistency guarantees, not whether a read sees uncommitted writes from concurrent callers. An agent cannot reason about concurrency it cannot see.
- **Retries amplify race conditions.** Agent frameworks retry on failure by default. A network timeout on a write-then-read pattern becomes two writes when retried — one that "failed" and one that succeeded, both replayed.
- **The failure looks like agent error.** "The agent downgraded the wrong plan" reads as a reasoning failure. The root cause is a read-write race. The agent cannot detect the difference without explicit concurrency primitives.

## The move

Treat every tool interaction as a distributed systems operation, not a function call.

**1. Read-then-write is a lie.** An agent that reads `get_customer_plan()`, then calls `update_plan()`, is performing two separate operations with an implicit assumption that nothing changed in between. Wrap these in explicit transactions or optimistic concurrency control:

```python
# Naive — two operations with an invisible race
plan = mcp_get_customer_plan(customer_id)
if plan.tier == "basic":
    mcp_update_plan(customer_id, "premium")  # another agent already changed this

# Better — optimistic concurrency with version check
result = mcp_get_customer_plan(customer_id, include_version=True)
current_version = result.version
plan = result.plan
if plan.tier == "basic":
    # Only succeeds if version hasn't changed; raises ConflictError otherwise
    mcp_update_plan(customer_id, "premium", expected_version=current_version)
```

**2. Idempotency keys on every mutating tool call.** Agents retry. Retries without idempotency are double-executions. Pass a deterministic idempotency key derived from the operation signature, not a random UUID:

```python
import hashlib, json

def idempotency_key(agent_id: str, tool_name: str, args: dict) -> str:
    payload = json.dumps({"agent": agent_id, "tool": tool_name, "args": args}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]

key = idempotency_key(agent_id="billing-agent-v3", tool_name="update_plan", args={"customer_id": "C-4821", "tier": "premium"})
mcp_update_plan(customer_id="C-4821", tier="premium", idempotency_key=key)
```

**3. Event-sourced tool state.** For shared resources (databases, queues, external services), tools should emit events rather than mutating state directly. Agents consume the event log, giving them a consistent view of what actually happened — not what the current snapshot says:

```python
# Tool writes an event, not a row
mcp_billing_tool.emit(event="plan_change", customer_id="C-4821",
                       from_tier="basic", to_tier="premium",
                       agent_id="billing-agent-v3", seq=1024)

# Agent reads the log, not the current state
events = mcp_billing_tool.get_events(since_seq=1000, entity="C-4821")
# Now the agent sees: plan was "basic" → "premium" at seq 1024
# It can reason about causal ordering, not just current snapshot
```

**4. Compensating actions for saga patterns.** When a multi-step tool workflow must span multiple services with no distributed transaction, define compensating actions for each step so partial failure can be undone:

```python
async def provision_customer_upgrade(customer_id: str, agent: Agent):
    try:
        step1 = await agent.call_tool("update_billing_plan", {"customer_id": customer_id, "tier": "premium"})
        step2 = await agent.call_tool("provision_resources", {"customer_id": customer_id, "tier": "premium"})
        step3 = await agent.call_tool("send_welcome_email", {"customer_id": customer_id})
    except ProvisionError as e:
        # Compensate in reverse order
        await agent.call_tool("deprovision_resources", {"customer_id": customer_id})
        await agent.call_tool("revert_billing_plan", {"customer_id": customer_id, receipt: step1.receipt})
        raise AgentWorkflowError(f"Upgrade saga failed: {e}") from e
```

**5. Resource leasing for exclusive tool access.** When an agent needs to hold a lock on a shared resource across multiple tool calls, use explicit leasing:

```python
lease = mcp_shared_workspace.acquire_lease(resource_id="workspace-W-7719",
                                           agent_id="provisioning-agent",
                                           ttl_seconds=30)
try:
    # All tool calls within the lease window are serialized against this resource
    snapshot = mcp_shared_workspace.read(resource_id="workspace-W-7719")
    modified = transform(snapshot)
    mcp_shared_workspace.write(resource_id="workspace-W-7719", data=modified)
finally:
    lease.release()
```

## Receipt

> Verified 2026-08-05 — Pattern derived from production concurrency patterns in multi-agent billing/provisioning systems, documented across Fordel Studios (March 2026), Northflank ephemeral execution research, and agent state management literature. Code examples follow standard Python concurrency primitives (optimistic locking, idempotency keys, saga compensating actions, resource leasing) compatible with MCP tool interfaces. No live run — patterns from distributed systems literature applied to agentic tool use.

## See also

- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — handoff semantics and coordination failure modes
- [S-2170 · The Orchestration Stack](s2170-the-orchestration-stack-when-your-graph-is-unmaintainable-and-your-loop-is-unrecoverable.md) — state machine boundaries in agent workflows
- [S-352 · Agentic Compensation Keys](s352-agentic-compensation-keys-idempotency-side-effects-retry-compensation-autonomous.md) — compensating actions and idempotency for autonomous agents
- [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool selection and provisioning discipline
