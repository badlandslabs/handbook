# S-1335 · The Blast Radius Formula Stack — When a Single Agent Can Take Down Your Entire Infrastructure

Your multi-agent system handles 200 requests per hour. One agent receives a manipulated input — a prompt injection, a corrupted memory fetch, or a bad tool response from a dependency. Within four hours, 87% of downstream decisions are affected. You had no containment architecture in place. This is the default behavior of multi-agent systems, not an edge case. The fix starts with quantifying blast radius as a first-class design metric before you deploy the first agent.

## Forces

- **Blast radius compounds across the trust graph.** A single agent with access to shared memory, downstream agents, and external tools can propagate failure through all three channels simultaneously. Galileo AI's 2026 research found 87% of downstream decision contamination within 4 hours of a single compromise — in systems that hadn't hardened the inter-agent boundary.
- **Traditional security monitoring is blind to this.** A compromised agent uses legitimate credentials on legitimate APIs. The actions look authorized — because they are. The breach lives in the input that drove the decision, not in the action itself. Access logs show valid calls; they don't show that a manipulated agent made them.
- **Operating velocity amplifies everything.** Agents execute multiple actions per second. A human security team responding to a breach moves at human speed. An agentic incident doubles or triples its blast radius while the team is still writing the first Slack message.
- **Detection window is the third variable you ignore at your peril.** Average AI incident detection time is 4.5 days (GLACIS 2025). In that window, an autonomous agent with broad tool access has ample time to propagate failures across the full system.

## The Move

Treat blast radius as a three-variable formula, not a binary risk:

**Blast Radius = Access Scope × Operating Velocity × Detection Window**

Reduce any variable to reduce the maximum possible damage.

### The Five Containment Patterns

**1. Least-Privilege Tool Scoping**
Each agent gets exactly the tools it needs for its specific task — not the full tool registry. Scope credentials per endpoint, not per role. Time-limit grants. Enforce allowlists for high-risk actions (delete, export, privilege change) with JIT elevation. This controls **Access Scope**.

```python
from dataclasses import dataclass
from enum import Enum

class RiskLevel(Enum):
    LOW = "low"      # read-only, no side effects
    MEDIUM = "medium"  # write operations within owned resources
    HIGH = "high"    # cross-boundary or destructive actions

@dataclass
class ToolPolicy:
    name: str
    risk_level: RiskLevel
    requires_approval: bool = False
    time_limit_seconds: int | None = None
    scope: list[str] | None = None  # allowed resource patterns

# Example: a data-query agent gets read tools only
QUERY_AGENT_POLICIES = [
    ToolPolicy("search_kb", RiskLevel.LOW),
    ToolPolicy("read_customer", RiskLevel.LOW),
    ToolPolicy("write_draft", RiskLevel.MEDIUM, scope=["drafts/*"]),
    ToolPolicy("delete_record", RiskLevel.HIGH, requires_approval=True),
    ToolPolicy("export_data", RiskLevel.HIGH, requires_approval=True),
]
```

**2. Operating Velocity Caps**
Limit actions per agent per minute. Cap workflow depth. Set maximum chain length before a human checkpoint. This controls **Operating Velocity** — even a compromised agent can only move so fast.

```python
import time
from collections import deque

class VelocityGovernor:
    def __init__(self, max_actions_per_minute: int = 30, max_chain_depth: int = 10):
        self.max_per_minute = max_actions_per_minute
        self.max_depth = max_chain_depth
        self.action_timestamps: deque = deque(maxlen=max_actions_per_minute)
        self._chain_depth = 0

    def check(self, agent_id: str) -> tuple[bool, str]:
        now = time.time()
        # Evict old timestamps
        while self.action_timestamps and now - self.action_timestamps[0] > 60:
            self.action_timestamps.popleft()

        if len(self.action_timestamps) >= self.max_per_minute:
            return False, f"Rate limit: {self.max_per_minute} actions/min exceeded"

        if self._chain_depth >= self.max_depth:
            return False, f"Chain depth limit: human checkpoint required at depth {self.max_depth}"

        self.action_timestamps.append(now)
        self._chain_depth += 1
        return True, "OK"

    def reset_chain(self):
        self._chain_depth = 0
```

**3. Workload Isolation**
Each agent runs in its own container or microVM. Peer agents cannot access another agent's memory, credentials, or execution context. A compromised agent cannot read the state of agents it hasn't been explicitly handed work by. This breaks the propagation path for **Access Scope** and **Detection Window**.

Use Firecracker microVMs (Firecracker-vmm.io, <125ms boot, <5MB overhead) for agents that execute code. Use gVisor user-space kernels for agents that call external processes. Network-isolation via service mesh (Istio, Linkerd) to prevent lateral movement.

**4. Out-of-Band Circuit Breakers**
Every agent-to-agent call has a parallel safety check that runs independently — not in the agent's execution path. If the downstream agent's behavior deviates from expected parameters (too many calls, too fast, wrong tool sequence), the circuit breaker fires and cuts the connection. This reduces **Detection Window** by catching anomalies at the boundary.

```python
from enum import Enum

class AgentState(Enum):
    HEALTHY = "healthy"
    SUSPECTED = "suspected"
    ISOLATED = "isolated"

class InterAgentCircuitBreaker:
    def __init__(self, call_rate_threshold: float = 2.0, error_rate_threshold: float = 0.3):
        self.call_rate_threshold = call_rate_threshold  # calls per second
        self.error_rate_threshold = error_rate_threshold
        self.state = AgentState.HEALTHY
        self.consecutive_errors = 0
        self.total_calls = 0

    def record_call(self, succeeded: bool, agent_id: str):
        self.total_calls += 1
        if not succeeded:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = max(0, self.consecutive_errors - 1)

        error_rate = self.consecutive_errors / max(1, self.total_calls)

        if self.state == AgentState.HEALTHY:
            if error_rate > self.error_rate_threshold:
                self.state = AgentState.SUSPECTED
                self._isolate(agent_id, reason=f"error_rate={error_rate:.2f}")
        elif self.state == AgentState.SUSPECTED:
            if error_rate > self.error_rate_threshold * 2:
                self.state = AgentState.ISOLATED
                self._isolate(agent_id, reason="confirmed_anomaly")

    def _isolate(self, agent_id: str, reason: str):
        # Block the agent from receiving new tasks
        print(f"CIRCUIT BREAKER: Isolating agent {agent_id} — {reason}")
        # Notify the orchestrator to drain the agent's queue
```

**5. Zero-Trust Inter-Agent Communication**
Never trust a message because it came from an internal agent. Every inter-agent call is authenticated, authorized against the same policy as external requests, and logged with correlation IDs that span the full chain. This prevents the "trust because internal" assumption that lets Agent B execute Agent A's instructions without independent verification. See also S-1065 (Inter-Agent Trust Escalation).

### The Blast Radius Audit

Before deploying any multi-agent system, answer these five questions in writing:

1. **Access Scope**: What is the maximum set of tools, data stores, and downstream agents any single agent can reach? (If "everything," deployment is not ready.)
2. **Velocity Cap**: What is the maximum actions-per-minute the system allows per agent? Is there a circuit breaker?
3. **Detection Window**: How long would it take to detect a compromised agent? Can you measure this today, or are you guessing?
4. **Containment Trigger**: What is the procedure for isolating an agent? Who has authority? How fast can it happen?
5. **Recovery Path**: What is the state-recovery procedure after an incident? Can you replay from a known-good checkpoint?

If you cannot answer all five, the deployment is not ready for production.

## Receipt
> Receipt pending — 2026-07-19. Run the blast radius audit checklist against a live deployment. Validate: (1) identify the agent with the highest access scope, (2) measure the detection window via a synthetic incident drill, (3) confirm the containment trigger can be executed in under 60 seconds by an on-call engineer who has never seen this checklist before.

## See also

- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — the "trust because internal" failure mode this stack addresses architecturally
- [S-1265 · The Kill Switch Stack](s1265-the-agent-kill-switch-stack-when-your-agent-is-breaking-things-and-nobody-can-stop-it.md) — containment trigger and recovery; complements the pre-incident blast radius audit
- [S-1083 · The Platform Credential Boundary](s1083-the-platform-credential-boundary-when-your-agent-has-a-secret-second-identity-on-the-cloud-platform.md) — the credential scoping dimension of access scope control
- [S-1108 · The Execution Sandbox Stack](s1108-the-execution-sandbox-stack-when-your-agent-writes-code-and-the-host-trusts-all-of-it.md) — container isolation as workload isolation implementation
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — behavioral SLOs as the detection layer for blast radius expansion
