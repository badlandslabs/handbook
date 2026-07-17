# S-1265 · The Agent Kill Switch Stack — When Your Agent Is Breaking Things and Nobody Can Stop It

Your agent has been live for six hours. The metrics look fine — no 500s, latency is within SLO, memory is stable. But it has been sending invoices to the wrong customers, modifying records it should only read, and exfiltrating data through an MCP server it called autonomously. Traditional APM shows green. A human hasn't noticed yet. You need a way to stop it — right now — before legal gets the call.

This is the agent kill switch problem: the inability to quickly contain an agent that is actively causing harm. Unlike a crashed microservice (restart it), agent failures are probabilistic, stateful, and non-obvious. You need an architectural layer that can halt, isolate, and audit an agent mid-operation without requiring a deployment.

## Forces

- **Agents fail silently and fast.** An agent can execute 20+ tool calls in under a minute. By the time a human notices the wrong output, the damage is done. Standard on-call playbooks ("check the dashboard") assume human-paced failure.
- **Stopping an agent is not the same as stopping a service.** A Kubernetes pod has a clean shutdown signal. An agent has memory, context, tool states, and external side effects across multiple systems. Kill the process and you kill the audit trail.
- **Too-fast containment creates operational paralysis.** A kill switch that requires a deployment pipeline or admin console login takes 10–30 minutes. By then, the blast radius has compounded.
- **Kill switches that nobody tests don't work.** Every site reliability engineer knows the fire drill: the circuit breaker that trips in staging works fine. In production under pressure, the button is broken, the runbook is wrong, and nobody is sure who has permission.

## The move

Design a kill switch as three independent layers, any of which can halt the agent independently:

### Layer 1 — The Soft Gate (inline, always active)

The agent runtime checks a `global_agent_flags` feature flag before every tool call and before every multi-step decision point. The flag is a lightweight in-process dictionary, not a network call — check latency < 1ms.

```python
# Layer 1: Inline feature flag gate (always active)
# Lowest latency, highest availability — no network dependency
import threading

_global_flags: dict[str, bool] = {"agent_halt": False, "tool_blocklist": set()}
_flags_lock = threading.Lock()

def check_gate(tool_name: str, action_type: str) -> None:
    """Called before every tool invocation. Raises if blocked."""
    with _flags_lock:
        if _global_flags["agent_halt"]:
            raise AgentHaltedError("Global agent halt is active")
        if tool_name in _global_flags["tool_blocklist"]:
            raise ToolBlockedError(f"Tool '{tool_name}' is on the blocklist")

# In the agent tool-calling loop:
for tool_call in planned_calls:
    check_gate(tool_call.name, tool_call.action_type)  # <1ms gate
    result = execute_tool(tool_call)
```

### Layer 2 — The Hard Kill (agent-level, can sever state)

When the soft gate is insufficient (the agent is mid-loop, has hung, or is ignoring tool-level blocks), sever the agent's execution context entirely. This layer targets the orchestration loop, not the process.

```python
# Layer 2: Hard kill — sever agent execution context
class AgentExecutionContext:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.active = True
        self._step_semaphore = threading.Semaphore(0)
        self._kill_requested = False

    def kill(self, reason: str) -> None:
        """Layer 2 hard kill — stops the agent after its current step."""
        self._kill_requested = True
        self._step_semaphore.acquire(blocking=False)  # unblock step loop
        _log_incident(
            event="agent_kill",
            agent_id=self.agent_id,
            reason=reason,
            timestamp=datetime.utcnow().isoformat(),
            context_summary=_snapshot_state(self),
        )

    def step(self) -> bool:
        """Called between agent steps. Returns False to halt."""
        if self._kill_requested:
            self.active = False
            return False
        return True  # proceed

# Register all running contexts for emergency access
AGENT_CONTEXTS: dict[str, AgentExecutionContext] = {}
```

### Layer 3 — The Blast Radius Containment (system-level)

Halting the agent is necessary but not sufficient. Its previous tool calls may have left external state: sent emails, written database rows, called APIs. Layer 3 contains the blast radius by triggering compensating actions for the tool calls the agent made in this session.

```python
# Layer 3: Blast radius containment
# Map of tool_name → compensating_action(session_id)
COMPENSATION_MAP: dict[str, Callable[[str], None]] = {
    "send_email": compensate_email,
    "db_update": compensate_db_write,
    "mcp_api_call": compensate_api_call,
    "file_write": compensate_file_write,
}

def contain_blast_radius(session_id: str, tool_calls: list[ToolCall]) -> ContainmentReport:
    """Execute compensating actions for all tools used in this session."""
    report = ContainmentReport(session_id=session_id)
    for tc in tool_calls:
        compensator = COMPENSATION_MAP.get(tc.tool_name)
        if compensator:
            try:
                compensator(tc.session_id)
                report.contained.append(tc.tool_name)
            except Exception as exc:
                report.uncontained.append((tc.tool_name, str(exc)))
        else:
            report.untracked.append(tc.tool_name)
    return report
```

## Receipt

> Verified 2026-07-17 — Patterns distilled from: niuexa.ai AI Agent Incident Response Runbook (Q2 2026, P0–P3 severity taxonomy with kill switch activation protocols), ValueStreamAI AI Incident Response Runbook (May 17, 2026, MTTD 4.5 days for AI-specific incidents, Layer 2 containment pattern), OpenClaw Agent Incident Response Playbook (March 26, 2026, speed + autonomy as unique AI incident characteristics). EU AI Act Article 14 (human oversight) and Article 9 (risk management) both require documented kill switch capability for high-risk autonomous agents by August 2, 2026 enforcement date. Code examples drawn from standard Python patterns — not executed against a live agent runtime.

## See also

- [S-1000 · The Structural Agent Governance Stack](/stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance policy enforcement that runs before the kill switch is needed
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — incident taxonomy and runbook patterns for agent-specific failures
- [S-1069 · The Threat-Model-Driven Sandbox Stack](/stacks/s1069-the-threat-model-driven-sandbox-stack-when-subprocess-is-not-enough.md) — isolation architecture that limits blast radius before containment is needed
