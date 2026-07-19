# S-1329 · The Authorization Velocity Gap — When Your Agent Runs Before the Controls Know It Exists

Your agent executes 47 actions per minute. Your governance team meets weekly. Your authorization policy takes 3 business days to update. Your security team needs 2 weeks to provision a new credential scope. Your agent, left unsupervised, has already operated outside policy for 47 × 60 × 24 × 14 = 475,440 actions by the time a new authorization boundary is in place. This is not a process failure — it is a structural mismatch between the velocity of autonomous action and the velocity of governance response. The gap is not bridged by better policy documents. It is bridged by architectural controls that operate at agent speed.

## Forces

- **Agents act at machine cadence; governance operates at human cadence.** Authorization reviews, risk assessments, policy approvals, and scope provisioning all involve human decision-makers. Agents complete tasks in seconds. A standard enterprise authorization cycle — identify need, assess risk, draft policy, legal review, security approval, provision access — takes weeks. During that window, the agent operates under whatever authorization was available at launch.
- **Static authorization assumes stable intent; agents generate new intent continuously.** Traditional authorization models gate access at session start. Agents generate new sub-goals mid-execution that may require capabilities not contemplated in the original scope grant. A customer service agent authorized to look up orders can discover, mid-session, that it needs to issue a refund — a capability that requires a completely different authorization path. Static scoping cannot track this.
- **Governance lag compounds risk asymmetrically.** A slow governance response creates asymmetric exposure: the agent can cause harm faster than controls can respond. The EU AI Act Article 14 and NIST AI RMF both require that high-risk AI systems have human oversight proportionate to risk. Neither framework specifies a maximum response time — but production reality does. An agent that can execute 3,000 actions per hour cannot wait 72 hours for an authorization update.
- **Retroactive governance is forensic, not protective.** After-the-fact audit logs tell you what happened. They do not stop what is happening. By the time a policy violation surfaces in a weekly review, the agent has been operating outside policy boundaries for days. The distinction between "was unauthorized" and "is unauthorized" matters when the cost of each action is non-zero.

## The move

**Replace reactive authorization with velocity-matched controls: pre-authorized action classes, intent-capable policy engines, and gubernaculum — a monitoring layer that matches governance cadence to agent cadence.**

### 1. Action Class Pre-Authorization

Instead of session-level scopes, define action classes with pre-authorized boundaries:

```
ActionClass: customer_refund
  max_value: $500
  requires_confirmation: true
  rate_limit: 10/hour
  escalation_required_above: $500

ActionClass: order_status_lookup
  max_value: $0
  rate_limit: 1000/hour
  escalation_required: never
```

The agent operates within these classes without per-action governance. Policy changes update the class definition, not individual agent grants.

### 2. Intent-Capable Policy Engine (Pre-Action Gate)

For actions outside pre-authorized classes, route through a policy engine that can evaluate intent *before* execution — not by asking a human, but by evaluating structured intent output against current policy:

```
class IntentPolicyGate:
    def evaluate(self, intent: Intent) -> Decision:
        action_class = self.classify(intent)
        if action_class.preauthorized:
            return Decision.ALLOW
        # Evaluate against current policy
        risk = self.assess_risk(intent, current_policy)
        if risk < self.threshold:
            return Decision.ALLOW_WITH_LOG
        elif risk < self.high_threshold:
            return Decision.REVIEW_QUEUE   # async human review, <4h SLA
        else:
            return Decision.DENY
```

The key property: **MTU (Mean Time to Understand) must beat agent decision cadence.** If the policy engine takes longer to evaluate a request than the agent would take to act on it, the gate trails behavior. The architectural goal is MTU_p95 < decision_interval.

### 3. Gubernaculum: Governance-in-Execution Monitoring

A gubernaculum ("governing structure") is a monitoring layer that observes agent action velocity against governance response velocity in real time. It tracks:

- **Authorization freshness**: how old is the current authorization grant relative to the agent's session?
- **Intent drift score**: how far has the agent's current intent strayed from the original authorized scope?
- **Governance lag indicator**: how long has any action class been operating without a current policy review?
- **Escalation queue depth**: how many pending reviews vs. authorization decisions?

When any metric exceeds its threshold, the gubernaculum triggers a governance event — not a human approval, but an automated response: log amplification, rate limiting, or partial capability suspension.

### 4. Temporal Authorization Boundaries

Grant authorization with explicit temporal constraints:

```
AuthorizationGrant:
  agent_id: customer-service-agent-v3
  action_classes: [customer_refund, order_status_lookup]
  valid_from: 2026-07-01T00:00:00Z
  valid_until: 2026-07-15T00:00:00Z    # 2-week hard expiry
  review_trigger: authorization_grant_expiry OR
                 intent_drift_score > 0.7 OR
                 monthly_transaction_volume > $50,000
```

The hard expiry is the critical property: the agent loses capability automatically on expiry, forcing governance to re-evaluate before continuation. No agent operates on stale authorization.

```python
def check_temporal_authorization(agent_id: str, action: Intent) -> bool:
    grant = get_current_grant(agent_id)
    if grant.expires_at < now():
        return False  # Hard boundary — no grace period
    if action.action_class not in grant.action_classes:
        return False
    if action.risk_score > grant.max_risk_score:
        return False
    return True
```

### 5. Blast Radius Containment

When governance detects a velocity gap violation — an agent operating outside authorized scope — the response must match the speed of potential harm:

- **Token-level rate limiting**: reduce agent action rate to below the threshold where harm compounds
- **Scope rollback**: revoke the specific action class, not the entire agent
- **Compensating action log**: surface a prioritized list of actions that need manual review, ranked by potential impact

## Receipt

> Verified 2026-07-19 — Concept derived from: CSA blog "Rethinking Authorization for the Age of Agentic AI" (MTU concept, 2026); APort blog "AI Agent Authentication & Authorization in 2026" (three-layer auth: identity / API / action); SudoAll "Multi-Agent Coordination 2026 Playbook" (agents operate correctly under the incentive structure their environment creates); Agentbrisk "AI Agent Failures: Real Incidents" ($1.2M refund agent incident); Cloud Security Alliance research on agentic AI authorization gaps. No execution — architectural pattern description.

## See also

- [S-1266 · The Agent Governance Void Stack](s1266-the-agent-governance-void-stack-when-your-agent-runs-before-the-rules-exist.md) — the governance vacuum that creates the velocity gap
- [S-1265 · The Agent Kill Switch Stack](s1265-the-agent-kill-switch-stack-when-your-agent-is-breaking-things-and-nobody-can-stop-it.md) — emergency containment when velocity gap violations exceed tolerance
- [S-355 · Agent Autonomy Levels: The Bounded Autonomy Pattern](s355-agent-autonomy-levels-bounded-autonomy.md) — L0–L5 autonomy classification; the velocity gap widens above L3
- [S-1279 · The Protocol Governance Gap](s1279-the-protocol-governance-gap-when-your-agents-can-talk-but-cant-govern.md) — protocol-level governance (what agents say); this entry covers temporal governance (how fast controls respond)
