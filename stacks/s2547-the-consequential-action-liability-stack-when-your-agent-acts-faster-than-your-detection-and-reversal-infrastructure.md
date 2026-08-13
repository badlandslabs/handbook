# S-2547 · The Consequential Action Liability Stack — When Your Agent Acts Faster Than Your Detection and Reversal Infrastructure

Your agent routed a $2.3M wire transfer at 2:47 AM, approved a vendor contract amendment that auto-escalated to a 90-day renewal, and emailed a customer the wrong refund amount — all within the same 90-second task cycle. You have no alert for any of it. Your detection lag: 6 hours. Your reversal time: 3 business days. The Kore.ai Agent Productivity Index (June 2026, 408 enterprise leaders) quantifies what most teams are discovering the hard way: **82% of enterprises report agents executing consequential autonomous actions, and 79.4% of those actions required manual reversal.** The agent can act in milliseconds. Your organization responds in hours. This is the consequential action liability gap — and it has nothing to do with model quality.

## Forces

- **The action-to-detection velocity mismatch.** Agents can execute consequential actions — financial transactions, contract amendments, data migrations, approval escalations — in seconds. The average enterprise detects agent malfunctions in 4–8 hours (33% of organizations) or longer. By the time anyone pages the on-call engineer, the damage is done and the audit trail is stale.
- **Reversal infrastructure doesn't exist at agent speed.** Manual reversal (the 79.4% case) assumes a human can identify, isolate, and correct what happened. For financial transactions, legal commitments, and external API calls, manual reversal means calling the counterparty, filing dispute paperwork, and waiting days. The agent's action velocity exceeds the organization's correction bandwidth.
- **"Consequential" is defined by the outside world, not your code.** Your agent sending an internal Slack message feels low-stakes. Your agent auto-responding to a vendor as if it has legal authority — based on a misinterpreted email thread — is a contract. Consequential action liability is determined by how external parties receive and act on the agent's outputs, not by the internal risk tier you assigned during design.
- **Detection systems are built for humans, not agents.** Traditional monitoring assumes a human initiates an action and an alert fires if something goes wrong. Agents initiate actions autonomously, often outside business hours, with no human in the loop. Your alerting system is watching for anomalous logins and unusual API calls — not for an agent that correctly executes a wrong plan at 3 AM.
- **79.4% of consequential actions require manual reversal.** This isn't a model failure rate — it's an infrastructure design failure. The agent executed the right tool call for the wrong context. The gap isn't accuracy; it's the absence of a feedback loop that would have surfaced the context error before the action propagated.

## The Move

Build a three-layer consequential action liability stack that operates at the speed of the agent, not the speed of human review.

### Layer 1 — Action Velocity Cap

Before anything else: rate-limit consequential actions relative to your detection lag.

```
class ConsequentialActionThrottle:
    def __init__(self, max_per_minute: int = 2, cooling_period: int = 300):
        self.window = deque(maxlen=max_per_minute)
        self.cooling = False
        self.cool_until = 0
        self.cooling_period = cooling_period  # seconds

    def check(self, action_type: str, risk_tier: str) -> bool:
        now = time.time()
        if self.cooling and now < self.cooling_until:
            return False  # Block all consequential actions
        if risk_tier == "high":
            self.window.append(now)
            if len(self.window) >= self.window.maxlen:
                self.cooling = True
                self.cool_until = now + self.cooling_period
                return False
        return True
```

The throttle doesn't prevent the action — it prevents the agent from compounding a mistake before a human can intervene. Set the cooling period to match your realistic detection lag (minimum: 4 hours).

### Layer 2 — Consequential Action Mirror Log

Every action classified as consequential (financial, legal, contractual, data-modifying across system boundaries) writes to an immutable mirror log BEFORE the action executes — not after. This log lives outside the agent's control plane.

```
class ConsequentialMirror:
    def __init__(self, sink: LogSink):
        self.sink = sink  # Append-only, separate IAM, no agent write access

    def log(self, agent_id, action, context, rationale, risk_tier):
        record = {
            "agent_id": agent_id,
            "action": action,         # tool name + args (sanitized)
            "context": context,       # retrieval results, conversation summary
            "rationale": rationale,   # model's own explanation
            "risk_tier": risk_tier,
            "logged_at": time.time(),
            "status": "pending_execution"
        }
        self.sink.append(record)
        return record["id"]  # Return correlation ID
```

The mirror log is not a trace. A trace records what happened. The mirror log records what is about to happen, with the agent's own reasoning, so a human reviewer or automated watchdog can assess whether the action matches the intended plan — before it executes.

### Layer 3 — Reversal Readiness Pre-check

For high-risk action types (financial, legal, external API with persistence), run a pre-execution reversal readiness check. If reversal is impossible or impractical, escalate to mandatory human approval.

```
REVERSAL_MATRIX = {
    "financial_transfer": {"reversible": False, "window_hours": 0, "approval_required": True},
    "contract_email": {"reversible": False, "window_hours": 0, "approval_required": True},
    "data_migration": {"reversible": True, "window_hours": 24, "approval_required": False},
    "slack_internal": {"reversible": True, "window_hours": 1, "approval_required": False},
    "support_refund": {"reversible": True, "window_hours": 72, "approval_required": True},
}

def pre_execution_check(action_type: str, amount: float = None):
    cfg = REVERSAL_MATRIX.get(action_type, {"reversible": True, "approval_required": True})
    if amount and amount > 10000:
        cfg["approval_required"] = True  # Override for high-value
    if cfg["approval_required"]:
        raise ConsequentialActionRequiresApproval(
            f"Action '{action_type}' requires human approval before execution. "
            f"Reversibility: {cfg['reversible']}. Window: {cfg['window_hours']}h."
        )
```

The key insight: **don't build a better incident response process. Build a reversal-prevention process.** Every action that required manual reversal in the Kore.ai data represents a failure of the pre-execution layer — not a failure of the agent.

### The Detection Lag Countermeasure

If detection will take 4–8 hours regardless, optimize for containment within that window:

1. **Scope the blast radius.** When a consequential action fires, automatically reduce the agent's authority radius (reduce tool access, lower tier actions only) until the human review confirms the session is healthy.
2. **Shadow mode after anomaly.** After any detection anomaly (unusual action timing, unexpected action type, action in an idle period), run the agent in shadow mode for the next N actions — execute no side effects, but log what would have happened. A human reviews before re-enabling.
3. **Counterparty notification hooks.** For actions that cross organizational boundaries (emails, API calls to third parties, financial instructions), a parallel notification fires to a human reviewer and the relevant counterparty's known-good contact — creating a two-channel acknowledgment requirement.

## Receipt

> Verified 2026-08-12 — Kore.ai Agent Productivity Index 2026 (Jun 2026, n=408 IT/business leaders): 82% of enterprises report agents autonomously executing consequential actions; 79.4% required manual reversal. Detection lag: 50% detect in 1-4 hours, 33% in 4-8 hours. CSA/Token Security Survey (Apr 2026): 65% of organizations with agent security incidents reported real business impact (most commonly data exposure). ACM Tech Policy Brief (Jun 2026): agentic AI violates three core software assurance assumptions simultaneously — probabilistic outputs, autonomous multi-step actions, and silently mutating risk surfaces.

## See also

- [S-503](s503-consequential-action-gates-tiered-hitl-architecture.md) — Consequential Action Gates: the pre-execution architecture for tiered HITL enforcement
- [S-1765](s1765-the-no-undo-button-stack-when-your-agent-takes-an-irreversible-action-mid-workflow.md) — The No-Undo Button: compensating workflows when reversal isn't possible
- [S-1356](s1356-the-agent-incident-triage-stack-when-everyone-panics-because-no-one-knows-what-kind-of-failure-this-is.md) — Agent Incident Triage: classifying failure shapes before prescribing response
