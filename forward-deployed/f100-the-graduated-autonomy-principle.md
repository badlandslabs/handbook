# F-100 · The Graduated Autonomy Principle

You shipped the agent. Three days later it booked $40K in vendor contracts, replied to a customer with a hallucinated refund policy, and your legal team is asking why a bot has unilateral authority. The agent was correct by its own success metrics. The failure was architectural — you gave it autonomy it hadn't earned.

## Forces

- **Trust accumulates slowly and collapses instantly.** A single high-visibility failure destroys the organizational credibility your agent program needs to scale. You cannot negotiate your way back from a bad first impression.
- **Agents that fail at low stakes teach you more than agents that succeed at high stakes.** The informational value of observing an agent in recommendation-only mode for 30 days outweighs 3 months of monitoring a full-execution agent you can't inspect.
- **Graduated autonomy is not a governance constraint — it is an information-gathering protocol.** The graduation criteria (task accuracy threshold, escalation rate, user override frequency) are the evaluation data your organization needs to justify the next autonomy tier.
- **The 88% pilot failure rate has a structural cause: wrong problem selection + no graduated ramp.** IDC research (2026) found three failure modes account for 89% of agentic AI pilot stalls: wrong problem selection, mock API integration, and governance vacuum. None of these are solved by "better prompts." They are solved by starting narrow, starting observable, and graduating deliberately.

## The move

**Start every agent in Tier 0: Recommendation Only.**

The agent observes workflows, suggests actions, and requires human approval before any state mutation. No tool calls that write to external systems. No email sends. No database writes. No purchases. It reasons and recommends.

Track:
- Agreement rate: how often does the human accept the agent's recommendation?
- Override rate: when the human rejects or modifies, what was different?
- Escalation rate: how often does the agent ask for help vs. committing to a recommendation?
- Silent-acceptance rate: human approved without modification — did the outcome succeed?

**Tier 1: Supervised Execution with human-in-the-loop confirmation gates.**

After 30 days with agreement rate >85%, override rate <15%, and silent-acceptance outcome success >90% — graduate to Tier 1. The agent can execute low-stakes actions (draft email, create draft ticket, run read-only query) with a 10-second cancellation window. Every action logs to an immutable audit trail. Human can override at any time.

**Tier 2: Autonomous Execution with exception reporting.**

After 60 days in Tier 1 with <2% escalation rate and <0.5% rollback rate — graduate to Tier 2. The agent executes autonomously but every action above a defined value threshold ($500, customer-facing, irreversible) triggers a post-action notification. Weekly review of agent decision quality. The human is the exception handler, not the approver.

**Tier 3: Full autonomy with standing policy constraints.**

After 90 days in Tier 2 with drift metrics stable (<3% behavioral regression across cohorts) — graduate to Tier 3. The agent operates autonomously within defined policy boundaries. Constraints are enforced by the agent's system prompt and by runtime policy gates, not by pre-action human approval. Standing policies (denylists, value limits, PII boundaries) are tested quarterly against the pinned eval set.

### The graduation protocol

```python
class AutonomyGraduationProtocol:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.tier = 0
        self.tier_metrics = defaultdict(list)  # per-day metrics

    def record_day(self, day: int, metrics: dict):
        self.tier_metrics[day] = metrics
        self.tier_metrics["all"].append(metrics)

        if self.tier == 0 and day >= 30:
            # Check Tier 1 graduation criteria
            last_30d = self.tier_metrics["all"][-30:]
            agree = avg(m["agreement_rate"] for m in last_30d)
            override = avg(m["override_rate"] for m in last_30d)
            outcome = avg(m["silent_acceptance_success"] for m in last_30d)

            if agree > 0.85 and override < 0.15 and outcome > 0.90:
                self.graduate(1, reason=f"agree={agree:.2f} override={override:.2f} outcome={outcome:.2f}")

        elif self.tier == 1 and day >= 60:
            last_30d = self.tier_metrics["all"][-30:]
            esc = avg(m["escalation_rate"] for m in last_30d)
            rollback = avg(m["rollback_rate"] for m in last_30d)
            if esc < 0.02 and rollback < 0.005:
                self.graduate(2, reason=f"esc={esc:.3f} rollback={rollback:.3f}")

        elif self.tier == 2 and day >= 90:
            # Check behavioral stability via pinned eval set
            drift = self._check_drift()
            if drift < 0.03:
                self.graduate(3, reason=f"drift={drift:.3f}")

    def graduation_criteria_summary(self, tier: int) -> dict:
        return {
            1: {"min_days": 30, "agreement_rate": ">85%", "override_rate": "<15%", "outcome_success": ">90%"},
            2: {"min_days": 60, "escalation_rate": "<2%", "rollback_rate": "<0.5%"},
            3: {"min_days": 90, "drift_vs_pinned_eval": "<3%", "constraint_test_pass": "100%"},
        }
```

### What the phases produce

Tier 0 is not wasted time — it produces your training data. Every (user input → agent recommendation → human response) triplet is a labeled example of what good looks like. The disagreements are the most valuable data: they reveal where the agent's world model diverges from the human's. Use these to refine the system prompt, adjust the tool descriptions, or identify capability gaps.

The graduated model also protects against governance vacuum. By the time the agent reaches Tier 2, you have 60 days of production evidence that its recommendations are trustworthy. The governance case for autonomy is built on evidence, not on a demo.

## Receipt

> Verified 2026-07-06 — Pattern sourced from IDC Research (May 2026) showing 88% enterprise agentic AI pilot failure rate with three structural failure modes; MLDS 2026 confirmed same pattern across independent organizations; S-355 (Agent Autonomy Levels) and S-444 (Governance Discovery) provide cross-links. The graduated autonomy ramp is distinct from the autonomy ceiling concept in S-355 — it describes the *initial deployment path*, not the maximum trust boundary.

## See also

[S-355 · Agent Autonomy Levels](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) · [S-444 · The 97/12 Gap: Agent Governance Discovery](stacks/s444-the-97-12-gap-agent-governance-discovery.md) · [F-191 · AI Agent Evaluation Harness](forward-deployed/f191-ai-agent-evaluation-harness.md) · [S-439 · Confident False Success: The Self-Assessment Failure Mode](stacks/s439-confident-false-success-the-self-assessment-failure-mode.md)
