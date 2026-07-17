# S-1226 · The Trust Budget Stack — When Your Agent Asks for Permission on Everything, or Nothing

Your agent is in one of two failure modes. Mode one: it asks for human approval on every non-trivial action — a 47-step workflow requires 23 confirmations, operators ignore half of them, and the agent is effectively a chatbot with extra steps. Mode two: it has full autonomy on day one and nobody knows what it did last Tuesday. Both failures share a root cause: nobody built the accounting system for trust. Trust budget thinking changes the equation — treat autonomy as a currency the agent earns, spends, and replenishes at runtime.

## Forces

- **Trust is binary when it should be metered.** The default mental model for agent autonomy is either supervised or autonomous — a switch, not a dial. This forces teams into an impossible choice: over-control (agents that can't act) or under-control (agents that act without bounds). Neither matches how autonomous systems actually behave.
- **Design-time trust doesn't survive production.** You can write policy for tasks you anticipated. You cannot write policy for every task the agent encounters at runtime. The gap between "we trust the agent to do X" and "the agent encounters X in the wild" is where failures live.
- **80% of organizations report unintended agent actions** (Tian Pan, 2026). This is not a capability problem — it's a trust governance problem. Teams give agents autonomy before earning it because there's no framework for earning it incrementally.
- **Trust has dimensions.** The risk of spending $1,000 is categorically different from the risk of sending an email or deleting a record. A single trust budget collapses these into one number, hiding the real exposure. Dimensions — monetary, operational, informational — must be tracked separately.
- **Trust decays.** An agent that was reliable last month may be operating on degraded context or a drifted model today. Trust earned at T₀ is not valid at T₀ + 30 days without evidence of continued reliability.

## The move

**Define trust as a multi-dimensional budget.** Track three separate pools:

| Dimension | What it governs | Cost of failure |
|-----------|-----------------|-----------------|
| **Monetary** | Spend actions — payments, purchases, resource creation | Financial loss |
| **Operational** | Write actions — data mutations, external API calls, state changes | Operational disruption |
| **Informational** | Read/export actions — data access, report generation | Confidentiality breach |

Each pool has a threshold and a decay rate. The agent can act autonomously within a pool when its balance is above the threshold. Actions draw from the budget; successful completions replenish it.

**Track trust in two modes: statistical and verified.**

```python
class TrustBudget:
    def __init__(self):
        # Three pools: monetary, operational, informational
        self.pools = {
            "monetary": Pool(balance=0.0, threshold=100.0, decay=0.02),
            "operational": Pool(balance=0.0, threshold=50.0, decay=0.05),
            "informational": Pool(balance=0.0, threshold=30.0, decay=0.10),
        }
        # Track two types of trust separately
        self.statistical_trust = 0.0   # Earned from task outcomes
        self.verified_trust = 0.0       # Earned from cryptographic proofs

    def can_act(self, action_type: str, cost: float) -> bool:
        pool = self.pools[action_type]
        return pool.balance >= cost and pool.balance > pool.threshold * 0.3

    def spend(self, action_type: str, cost: float) -> None:
        if not self.can_act(action_type, cost):
            raise TrustBudgetExceeded(f"Insufficient trust for {action_type}")
        self.pools[action_type].balance -= cost

    def replenish(self, action_type: str, cost: float, verified: bool = False) -> None:
        multiplier = 1.5 if verified else 1.0
        self.pools[action_type].balance = min(
            self.pools[action_type].balance + cost * multiplier,
            self.pools[action_type].threshold * 2.0  # Cap at 2x threshold
        )
        if verified:
            self.verified_trust = min(1.0, self.verified_trust + 0.01)
        else:
            self.statistical_trust = min(1.0, self.statistical_trust + 0.005)

    def apply_decay(self) -> None:
        for pool in self.pools.values():
            pool.balance *= (1 - pool.decay)
```

**Earn trust through tiered actions.**

| Action tier | Trust cost | Example |
|-------------|-----------|---------|
| **Tier 0 — Read** | Free | Query a database, read a file |
| **Tier 1 — Suggest** | 5 ops budget | Propose a response, generate an outline |
| **Tier 2 — Non-destructive write** | 20 ops budget | Draft an email, create a draft record |
| **Tier 3 — Destructive write** | 50 ops budget | Delete a record, revoke access |
| **Tier 4 — Spend** | 50 monetary budget | Process a payment, create a resource |
| **Tier 5 — Escalate** | Requires human approval | Nuclear option, untested domain |

Each successful Tier 2+ action adds to the trust balance. A failed action — caught by a canary probe or behavioral drift detector — subtracts 3× the earned trust. A cascade of failures triggers automatic downgrade to a lower tier.

**Verify trust where stakes are high.** For Tier 4 and Tier 5 actions, require verified trust. "Verified" means: the output was checked against an independent oracle (a second agent, a rule-based validator, a cryptographic commitment). Verified trust grows 1.5× faster than statistical trust but requires actual proof.

**Decay unexercised trust.** If the agent hasn't performed a Tier 3+ action in 7 days, its monetary and operational trust pools decay by 2–5% per day. This prevents the "earned forever" trap where an agent's trust budget reflects stale evidence.

**Gate autonomy on trust tier, not on human approval.** Instead of a human confirming every action, the agent's trust tier determines what it can do autonomously:

```python
def execute_action(agent, action, trust_budget):
    tier = classify_action(action)  # 0-5

    if tier <= trust_budget.current_tier:
        if trust_budget.can_act(action.pool, action.cost):
            return agent.act(action)
        else:
            return escalate(action, reason="trust_budget_insufficient")

    # Above current tier: always escalate
    return escalate(action, reason="tier_exceeded")
```

The trust tier itself is a runtime variable — not hardcoded. An agent starts at Tier 1. As it completes tasks in a domain without incident, it earns toward Tier 2. Crossing a tier boundary triggers a human review checkpoint, not a continuous approval gate.

## Receipt

> Receipt pending — 2026-07-16
> Tian Pan's "Earned Autonomy" framework (tianpan.co, April 2026) provides the conceptual foundation. S-1059 covers the enterprise phase-gate deployment model. This entry covers the runtime trust accounting mechanism — a distinct contribution. Cloudflare Durable Agents (developers.cloudflare.com, 2026) implement hibernation-based state persistence that maps to the "trust survives hibernation" requirement. Production implementation of the token bucket model has not been run; the Python example above is architectural.

## See also

- [S-1059 · The 88% Chasm](s1059-the-88-percent-chasm-why-ai-agent-pilots-stall-and-the-graduated-autonomy-playbook.md) — Enterprise phase-gate model for pilot-to-production graduation (this entry's runtime counterpart)
- [S-1225 · The Grounded Recovery Stack](s1225-the-grounded-recovery-stack-when-your-agent-fails-but-cannot-tell-success-from-failure.md) — Failure detection primitives that feed the trust replenishment signal
- [S-992 · Agent Verifiable Credential Infrastructure](s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — Credential layer that could serve as the "verified trust" oracle
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet-yet.md) — Operational discipline that enforces the trust decay and escalation policies
