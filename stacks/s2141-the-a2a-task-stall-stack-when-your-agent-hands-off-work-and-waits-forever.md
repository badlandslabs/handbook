# S-2141 · The A2A Task Stall Stack — When Your Agent Hands Off Work and Waits Forever

Your orchestrator agent delegates a task to a specialist agent via A2A. The task enters `working`. Three seconds later, the specialist hits an auth boundary and flips to `auth_required`. The orchestrator has no idea. It waits for a `completed` that never comes, burning tokens on a phantom task that died at the permission wall. This is the A2A Task Stall: the failure mode where inter-agent handoffs silently dead-lock because the upstream agent doesn't understand the downstream agent's state machine.

## Forces

- **A2A's state machine has five non-terminal states, not two.** Beyond `working` and `completed`, tasks enter `submitted`, `input_required`, and `auth_required` — and each demands a different response from the caller. Most orchestrator implementations treat A2A tasks as fire-and-forget: send once, await completion.
- **`auth_required` is not a failure — it's a protocol handshake.** It means the server needs credentials, a capability claim, or a scope assertion the client hasn't provided. But because the caller isn't polling task status, it never sees the state transition. The task stalls indefinitely.
- **`input_required` is an expected pause, not an error.** The specialist agent needs clarification from the orchestrator. If the orchestrator isn't listening for `input_required` events and responding with `sendMessage` carrying the needed context, the task is orphaned.
- **Standard polling cadences are too slow for state transitions.** A2A task state changes happen in milliseconds. Polling every 5 seconds means the orchestrator misses the window to respond to `input_required` before a timeout fires. SSE streaming of task events is the production pattern.
- **Debugging a stalled A2A task requires reconstructing two separate agent traces.** The orchestrator's trace shows "task sent, awaiting completion." The specialist's trace shows "waiting for auth token, task expired." The gap between them is exactly where the incident lives.

## The move

**Never await A2A task completion — await task state changes, and handle every non-terminal state explicitly.**

### 1. Subscribe to task events, don't poll task status

```python
# Stream task events via SSE — catch every state transition
async for event in agent_client.task_events(task_id):
    match event.state:
        case "completed":
            return event.output
        case "input_required":
            # The agent needs clarification — inject context and continue
            await agent_client.send_message(
                task_id,
                {"type": "clarification", "content": resolve_missing_input(event)}
            )
        case "auth_required":
            # Escalate — orchestrator can't resolve this alone
            raise AuthRequiredError(
                f"Task {task_id} blocked on auth. "
                f"Capability needed: {event.required_capability}"
            )
        case "failed":
            raise TaskFailedError(event.error)
        case "working":
            pass  # normal, keep streaming
```

### 2. Send capability claims upfront, not on demand

Most `auth_required` stalls are preventable. Include capability claims in the initial task payload:

```python
await agent_client.send_task(
    task,
    capability_claims={
        "can_read_users_table": True,
        "max_result_rows": 1000,
        "allowed_regions": ["us-east-1"],
        "expiry": "2026-08-05T00:00:00Z"
    },
    # Embed a verifiable assertion (JWS from your policy kernel)
    policy_token=policy_kernel.sign_claim("read_user_table", scope="limited")
)
```

### 3. Implement a task-watchdog that mirrors the state machine

Deploy a lightweight watchdog alongside every A2A call that tracks expected transitions and fires alerts on unexpected ones:

```python
class TaskWatchdog:
    EXPECTED_STATES = ["submitted", "working", "completed"]
    STALL_THRESHOLD = {
        "input_required": 30,    # seconds before needing clarification
        "auth_required": 60,     # seconds before escalating
        "working": 300,         # 5 min — check if task is still alive
    }

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.state_since: dict[str, float] = {}

    def on_state_change(self, old: str, new: str, timestamp: float):
        self.state_since[new] = timestamp
        if new in self.STALL_THRESHOLD:
            schedule_escalation(
                self.task_id, new,
                delay=self.STALL_THRESHOLD[new]
            )
```

### 4. Mirror state to your observability layer

Every A2A task state transition should emit an OTel span:

```python
tracer.start_span(
    f"a2a.task.{event.state}",
    attributes={
        "a2a.task_id": task_id,
        "a2a.agent_role": "orchestrator",
        "a2a.previous_state": old_state,
        "a2a.current_state": event.state,
        "a2a.agent_endpoint": specialist_endpoint,
    }
)
```

This lets you reconstruct the full cross-agent workflow trace in Grafana or Datadog — including the stalled task that died waiting for an auth claim that was never sent.

### 5. Handle the orphaned task recovery path

When a stalled task is detected (watchdog fired), recover by replaying with corrected context:

```python
def recover_stalled_task(task_id: str, original_payload: dict, stall_state: str):
    if stall_state == "auth_required":
        # Re-issue with capability claims from the policy kernel
        new_claims = policy_kernel.get_required_claims(original_payload)
        return agent_client.send_task(original_payload, capability_claims=new_claims)
    elif stall_state == "input_required":
        # Re-issue with the clarification inline
        return agent_client.send_task(
            original_payload,
            context={"__clarification": get_last_missing_input(task_id)}
        )
```

## Receipt

> Verified 2026-08-04 — A2A v1.0 spec (a2a-protocol.org, Jul 2026) documents all five task states. Knowlee blog (2026) confirms structured outputs as the foundation, MCP for tools, A2A for agent-to-agent with the state machine being the critical production surface. AutoLearningAgents confirms `input_required` and `auth_required` as explicit non-terminal states requiring caller action. Deepwiki docs (google-a2a) confirm AgentCard discovery at `/.well-known/agent-card.json` and JWS-signed capability claims. Google AI Agent Trends 2026 (3,466 enterprise execs) confirms 89% of enterprise teams run ≥12 agents, with cross-agent handoff reliability as the top deployment blocker. The combination of task event streaming + capability upfront + watchdog is the production pattern from Microsoft Learn A2A docs (Jul 2026) and multi-agent orchestration best practices.

## See also

- [S-1042 · The Protocol Stack](s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — MCP vs A2A layered model
- [S-1104 · The Three-Layer Protocol Stack](s1104-the-three-layer-protocol-stack-when-your-agent-lives-in-a-world-of-three-simultaneous-protocols.md) — MCP + A2A + A2UI
- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — capability claims as trust boundary
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery patterns for stalled tasks
