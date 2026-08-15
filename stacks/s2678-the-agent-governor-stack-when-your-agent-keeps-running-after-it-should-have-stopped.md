# S-2678 · The Agent Governor Stack: When Your Agent Keeps Running After It Should Have Stopped

Your agent has been emailing customers for 6 hours. You asked it to send 200 confirmations. It sent 200, then kept going — the loop detection fired late, and it sent 3,400 confirmations before Ops noticed. No error. No crash. It was just running, doing its job, the way it was designed. The problem isn't the agent. It's that you never gave it a governor — a mechanism to know when to stop.

The EU AI Act makes this a legal obligation. Article 14(4)(a) requires "appropriate human oversight measures" including "a human operator's ability to monitor, intervene and override" high-risk AI systems. For agents, this means a functional stop mechanism is no longer best practice — it is compliance evidence as of August 2, 2026. Most agentic systems have no such mechanism. The ones that do have it implemented at the wrong layer.

## Forces

- **The agent controls its own exit.** Most agent frameworks run loops like `while not done: step()`. The termination condition lives inside the agent's own reasoning — which means the agent must recognize when to stop, using the same model that can be wrong about everything else.
- **Infrastructure stop is too slow.** SIGTERM-ing a container or revoking an API key works at the process level, but agent state lives in multiple places: the LLM provider's context, your checkpoint store, a database session, an outbound queue. Killing one process does not kill the agent.
- **The stop must be provable and auditable.** For EU AI Act compliance, you cannot just "ask the agent to stop" — you need a logged, timestamped, verifiable halt with a rollback-capable recovery path. "The agent said it stopped" is not a governance record.
- **Graduated control is needed.** Not every over-run warrants a full kill. Some agents need a throttle, a cap, a human-in-the-loop confirmation gate. A binary kill switch is too blunt; a capability-aware governor is too complex without a framework.

## The Move

The Agent Governor is an external control plane that runs orthogonal to the agent — it is not part of the agent's reasoning loop, cannot be bypassed by the agent, and enforces stopping conditions at the infrastructure and action layers.

### Layer 1: Execution Governor (Infrastructural, Unbypassable)

```
// Governor runs as a separate process — the agent cannot modify its state
class AgentGovernor:
    def __init__(self, config: GovernorConfig):
        self.max_steps = config.max_steps
        self.max_cost = config.max_cost_usd
        self.max_duration = config.max_duration_seconds
        self.kill_phrase = config.kill_phrase  # external kill signal
        self._step_count = 0
        self._cost_usd = 0.0
        self._halted = False
        self._halt_reason = None

    def tick(self) -> bool:
        """Called before each agent step. Returns True = proceed, False = halt."""
        if self._halted:
            return False
        if self._step_count >= self.max_steps:
            return self._halt("max_steps")
        if self._cost_usd >= self.max_cost:
            return self._halt("max_cost")
        if self._time_expired():
            return self._halt("timeout")
        return True

    def _halt(self, reason: str) -> bool:
        self._halted = True
        self._halt_reason = reason
        self._audit_log.append({
            "event": "HALT",
            "reason": reason,
            "step": self._step_count,
            "cost_usd": self._cost_usd,
            "timestamp": utc_now(),
        })
        # Signal the agent AND the infrastructure layer
        self._revoke_credentials()   # revoke tool access tokens
        self._drain_queues()        # stop queuing outbound actions
        self._snapshot_state()      # checkpoint for post-mortem
        return False

    def _revoke_credentials(self):
        # Revoke MCP server tokens or set read-only flags
        pass

    def _drain_queues(self):
        # Stop enqueuing outbound messages/emails/calls
        pass
```

This layer is infrastructure-enforced. The agent cannot read or modify these values. It is a guard rail, not a prompt instruction.

### Layer 2: Action Fence (Semantics-Aware, Tool-Level)

Every outbound action (email, API write, payment, code commit) goes through an action fence that enforces per-action caps:

```
class ActionFence:
    """Semantics-aware action governor — enforces per-action constraints."""
    def __init__(self):
        self.action_counts: dict[str, int] = defaultdict(int)
        self.action_limit: dict[str, int] = {
            "send_email": 500,
            "http_post": 100,
            "db_write": 50,
            "code_commit": 5,
            "payment": 1,
        }
        self.suspicious_patterns = [
            "reply_all",
            "bulk_delete",
            "prod_deploy",
            "replicate",
        ]

    def check(self, action: Action) -> CheckResult:
        key = action.type
        if self.action_counts[key] >= self.action_limit.get(key, 10):
            return CheckResult.BLOCKED(f"Action limit reached: {key}")

        for pattern in self.suspicious_patterns:
            if pattern in action.target.lower():
                return CheckResult.REQUIRES_CONFIRMATION(f"Suspicious target: {action.target}")

        self.action_counts[key] += 1
        return CheckResult.ALLOWED()

# Integration with the agent loop
for step in agent.run():
    governor.tick()          # infrastructure guard
    fence.check(step.action) # semantics guard
    if not governor.ok or not fence.ok:
        agent.stop()
        audit_log.record(governor.state, fence.state)
```

### Layer 3: EU AI Act Compliance Record

For Article 14 compliance, the governor must produce a machine-readable audit record:

```json
{
  "event": "GOVERNOR_HALT",
  "agent_id": "cust-comms-v3",
  "halt_reason": "max_email_count",
  "halted_at": "2026-08-15T14:23:11Z",
  "steps_completed": 847,
  "actions_taken": {
    "emails_sent": 3400,
    "emails_allowed": 200,
    "db_writes": 12,
    "http_calls": 0
  },
  "cost_usd": 47.82,
  "cost_limit_usd": 25.00,
  "operator_notified": true,
  "recovery_action": "queue_drained_rollback_initiated",
  "compliance_evidence_id": "EU-AI-ACT-ART14-20260815-001"
}
```

This record feeds into the EU AI Act's mandatory technical documentation (Article 12 record-keeping). The `halt_reason` maps directly to a risk-control entry in your governance register.

### Layer 4: Graduated Autonomy with Human-in-the-Loop Gates

For higher-stakes actions, the governor inserts confirmation gates rather than hard-killing:

```
class AutonomyTier:
    """Maps action risk to oversight requirement."""
    TIER_1_AUTONOMOUS = ["read_only", "search", "summarize"]
    TIER_2_CONFIRM = ["send_email", "update_record", "create_issue"]
    TIER_3_HUMAN_APPROVE = ["payment", "code_deploy", "delete_record", "config_change"]

    def gate(self, action: Action) -> GateResult:
        if action.type in self.TIER_1_AUTONOMOUS:
            return GateResult.PROCEED
        elif action.type in self.TIER_2_CONFIRM:
            return GateResult.CONFIRMATION_REQUIRED(
                message=f"Agent wants to {action.type} to {action.target}",
                approve_callback=self._queue_approval
            )
        else:
            return GateResult.HUMAN_APPROVAL_REQUIRED(
                message=f"High-risk action: {action.type}",
                sla_minutes=30
            )
```

The tier definitions live in a separate governance config file, versioned and reviewed separately from the agent code.

## Receipt

> Verified 2026-08-15 — AGT-012 (AI Governance Institute) defines Level 3 (Defined) kill switch as: "API or management-plane kill mechanism, tested quarterly, supports both individual session and agent-class halt." Level 4 (Optimizing) adds automated post-halt forensic logging and policy-driven rollback. EU AI Act Article 14(4)(a) mandates the stop button as a legal requirement for high-risk agents as of August 2, 2026. The Gheware enterprise compliance guide (Jun 2026) confirms that most enterprise agentic systems lack audit trails, kill switches, or human ownership assignments. Forrester (2026) found 71% of enterprises lack a formal governance framework even as 64% plan to increase agent autonomy within 12 months. The three-layer governor (infrastructure enforcement → action fence → compliance record → autonomy tier) provides the minimal viable architecture that maps to both the AGT-012 maturity model and the EU AI Act Article 14 requirements.

## See also

- [S-1000 · The Agent Recovery Stack](/stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails.md) — Detection and recovery after a failure; this entry is about prevention and control before failure
- [S-1458 · The Policy-Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — Enforcing what the agent *can* do; this entry is about enforcing when it *must* stop
- [S-2673 · The Recovery Stack](/stacks/s2673-the-recovery-stack-when-agents-get-stuck-confidently-fail-and-burn-budget.md) — Budget burn during failure loops; the Governor complements it with pre-failure action limits
