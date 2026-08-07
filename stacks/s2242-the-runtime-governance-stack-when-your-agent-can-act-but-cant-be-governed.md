# S-2242 · The Runtime Governance Stack — When Your Agent Can Act but Can't Be Governed

Your agent completed a 12-step workflow. It read customer records, drafted a contract amendment, sent an approval email, updated a CRM, and scheduled a follow-up — all within scope. But nobody can prove what it did, who authorized each step, or whether the sequence of individually-permitted actions crossed an invisible business rule. Traditional security evaluates one request at a time. Production agents dissolve that model — they string together sequences of permitted actions that no individual guard caught. The architectural response is a runtime governance plane that governs agents from outside their execution path.

## Forces

- **Plan-level risk doesn't exist in traditional IAM.** A single API call to update a contract draft is permitted. Twelve such calls in sequence, culminating in an unsigned amendment sent to a counterparty, is a compliance violation. No request-level guard evaluated the plan.
- **Composite principals invalidate single-user authorization models.** When Agent A delegates to Agent B, who delegates to Agent C, the authorization chain involves three agents with different trust levels. Traditional RBAC has no vocabulary for this.
- **75% of companies plan to deploy agentic AI within two years, but only 21% have mature governance** — a gap that dashboards and monitoring alone cannot close.
- **Execution happens faster than human review.** An agent can complete a multi-step financial workflow in seconds. A compliance officer who needs to approve each step makes the agent useless. Governance must be real-time, not post-hoc.
- **Regulatory frameworks (EU AI Act, SOC 2, GDPR) are converging on mandatory agent audit trails.** As of 2026, verified enterprise-relevant AI incidents number 344 (Cyera, May 2026), with 43% lacking an audit trail that could establish accountability.

## The Move

### The Five Governance Planes

The five-plane reference architecture (Tallam, arXiv:2606.12320, 2026) decomposes runtime governance across five composable planes:

1. **Build Plane** — where agents are created, prompts are written, skills are installed, tools are registered
2. **Orchestration Plane** — where agents are wired into business workflows, task decomposition happens, handoffs occur
3. **Data Plane** — where agents execute, call tools, mutate state, produce outputs
4. **Control Plane** — where policy is enforced before execution, credentials are scoped, blast radius is bounded (independent of all three above)
5. **Oversight Plane** — where traces are recorded, audits are generated, anomalies surface

The key insight: governance must operate out-of-band from the three execution planes. An agent cannot be trusted to govern itself.

### Plan-Level Policy Evaluation

Instead of evaluating each tool call in isolation, the control plane evaluates the agent's intended plan before any execution begins:

```
python
def evaluate_plan(plan: AgentPlan, agent_principal: CompositePrincipal) -> PolicyResult:
    """Evaluate entire plan against policy before first step executes."""
    violations = []
    for step in plan.steps:
        # Check individual step permissions
        step_result = evaluate_step_permission(step, agent_principal)
        if not step_result.allowed:
            violations.append(step_result.denial)
        # Check cumulative risk of step sequence
        sequence_result = evaluate_sequence_risk(plan.steps[:plan.steps.index(step)+1])
        if sequence_result.exceeds_threshold:
            violations.append(sequence_result.compound_violation)
    
    if violations:
        return PolicyResult.denied(violations, requires_human_review=True)
    return PolicyResult.approved(policy_conditions=[...])
```

Policy conditions are the key output: approved execution with mandatory checkpoints, rate limits, or escalation triggers — not binary allow/deny.

### Composite Principal Authorization

When delegation chains exist, authorization must track the full delegation path:

```
python
class CompositePrincipal:
    def __init__(self, origin_agent: AgentId, delegation_chain: list[DelegationLink]):
        self.origin = origin_agent
        self.chain = delegation_chain  # [(delegator, delegatee, scope, expires_at), ...]
    
    def can_perform(self, action: Action, scope: Scope) -> bool:
        # Each link in the chain grants only the scope it explicitly delegated
        current_scope = scope
        for delegator, delegatee, granted_scope, expires_at in reversed(self.chain):
            if not self._within_delegation_window(expires_at):
                raise DelegationExpiredError(delegator, delegatee)
            if not granted_scope.covers(action):
                return False
            current_scope = granted_scope
        return True

class DelegationLink(NamedTuple):
    delegator: AgentId
    delegatee: AgentId
    granted_scope: Scope
    expires_at: datetime
```

This makes it possible to answer: "Can Agent C, delegated from Agent B (which was delegated from Agent A), send an email to an external address with attachment?" — a question RBAC cannot express.

### Pre-Execution Guardrails vs Post-Hoc Audit

The critical architectural decision is where governance runs:

| Approach | Latency | Coverage | Failure Mode |
|----------|---------|----------|-------------|
| Pre-execution gate | Adds ~50–200ms | Full plan visible | Blocks useful work if thresholds are wrong |
| Inline per-step | Minimal latency | Only per-call | Misses compound risk |
| Post-hoc audit | Zero latency impact | Full trail | No prevention, only detection |
| **Pre-execution + inline + post** | ~100ms total | All three | Complexity of three systems |

The working pattern: pre-execution policy evaluation gates the plan, inline guards handle runtime exceptions, and the oversight plane records the full trace for audit. Each layer corrects the blind spots of the others.

### The Audit Trail as First-Class Output

Every agent run must produce a non-repudiable execution record:

```python
@dataclass
class ExecutionAttestation:
    run_id: str
    principal_chain: list[DelegationLink]
    plan_summary: str
    steps_executed: list[StepRecord]  # action, timestamp, tool, inputs (sanitized), outputs (sanitized)
    policy_decisions: list[PolicyDecision]  # approved, denied, escalated at each checkpoint
    total_cost: TokenCost
    consent_evidence: str  # URI or reference to user/system consent record
```

This record must be tamper-evident (content-addressed storage or cryptographic chain) and must survive the agent process crashing. It is the legal instrument that proves what happened, not the agent's own output.

### Capability Lifetime Gating

Agents should not hold permanent credentials. The control plane enforces temporary, scoped delegation:

```
python
def scope_agent_credentials(agent: AgentId, task: TaskScope, ttl: timedelta) -> ScopedCredentialBundle:
    """Issue credentials valid only for this task, this scope, this duration."""
    return ScopedCredentialBundle(
        access_token=issue_token(scope=task.tool_scope, ttl=ttl, audience=task.resources),
        refresh_token=issue_token(scope="read_task_status", ttl=ttl * 1.1, audience="control-plane"),
        expiry_evidence=timestamp_proof()  # for non-repudiation
    )

def revoke_on_task_complete(task_id: str):
    """Called by orchestration plane when task reaches terminal state."""
    control_plane.revoke_credentials(task_id)
    control_plane.freeze_agent_state(task_id)
    oversight_plane.seal_attestation(task_id)
```

### Governance Maturity Ladder

Most teams start at Level 0 (no governance) and should climb deliberately:

| Level | What's in place | What it misses |
|-------|----------------|----------------|
| **0 — None** | Agent runs, nothing recorded | No accountability, no audit |
| **1 — Logging** | Execution traces captured | No enforcement, no policy |
| **2 — Policy** | Rules defined, violations flagged post-hoc | No pre-execution gate |
| **3 — Guarded** | Pre-execution evaluation on high-risk actions | Gaps on medium/low risk paths |
| **4 — Attested** | Full non-repudiable audit trail, credential scoping | No automated remediation |
| **5 — Adaptive** | Runtime policy adjustment based on trust signals, anomaly detection | — |

Most production systems in 2026 sit at Level 2–3. Level 5 requires a mature control plane vendor or significant custom build.

## Receipt

> Receipt pending — 2026-08-06. Verification: arXiv:2606.12320v1 five-plane architecture (Tallam, 2026) reviewed; Waxell.ai 2026 agent control plane survey (21% maturity stat, 75% deployment plan, 33 Forrester vendors, 344 Cyera incidents) confirmed. Key patterns: plan-level evaluation vs request-level gates, composite principal model, pre-execution guard + inline guard + post-hoc audit as complementary layers, capability lifetime gating as the credential answer to permanent tokens. Concrete implementation patterns drawn from the five-plane reference architecture. Production implementation guidance from Waxell, Drata Agent Control Plane guide, and Activant Capital research.

## See also

- [S-2102 · The Agent Credential Lifecycle Stack](/stacks/s2102-the-agent-credential-lifecycle-stack-when-your-agent-has-more-secrets-than-your-engineers.md) — non-human identity and credential scoping (complementary: this entry covers governance authority, S-2102 covers secrets management)
- [S-2234 · The Agent Governance Readiness Stack](/stacks/s2234-the-agent-governance-readiness-stack-when-your-pilot-wins-but-production-fails.md) — organizational and pilot-to-production governance gaps (organizational complement to this entry's runtime architecture)
- [S-1042 · The Protocol Stack](/stacks/s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — MCP/A2A protocol layer (this entry operates above the protocol layer, governing what agents do with the tools/protocols they access)
