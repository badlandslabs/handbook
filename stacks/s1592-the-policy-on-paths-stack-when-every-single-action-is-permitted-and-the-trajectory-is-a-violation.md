# S-1592 · The Policy-on-Paths Stack — When Every Single Action Is Permitted and the Trajectory Is a Violation

Your agent reads a customer record (permitted). Your agent sends an email to your vendor (permitted). Your agent reads that customer record and then emails the vendor — an information barrier breach that triggers a $2.3M regulatory fine. Every step was authorized individually. The sequence was not. This is the policy-on-paths problem, and static access controls cannot solve it.

## Forces

- **Individual-action evaluation misses sequence-level harm.** A database read, a file write, an outbound email — each is benign in isolation. Their ordering is the violation. Traditional RBAC and ACL checks evaluate one action at a time.
- **Latency budget conflicts with deep path analysis.** Evaluating a full trajectory before allowing any step requires either predicting the future (expensive and unreliable) or waiting for a trailing window to accumulate history (adds latency to every decision gate).
- **What makes this non-obvious:** Most teams believe "we have access controls, so we're covered." What they have is step-level gatekeeping. The EU AI Act Articles 9, 12, 13, and 14 (effective August 2, 2026 for high-risk systems) specifically require policy enforcement on *paths*, not steps. The compliance requirement is structurally different from the access control they already deployed.

## The move

**1. Model policies as functions over partial paths, not individual actions.**

The insight from Kaptein et al. (arXiv:2603.16586, March 2026): define a policy violation probability as a deterministic function of `(agent_id, partial_path_history, proposed_next_action, organizational_state)`. The violation is not a property of the next action in isolation — it's a property of the path that leads to it.

**2. Build a trailing state window for path evaluation.**

Maintain a rolling buffer of the last N actions in agent memory. Before each tool call, evaluate the candidate action against the window:

```
Policy violated if:
  (buffer contains ["read:confidential-record"])
  AND (proposed_action matches external_transmission_pattern)
  AND (no approved_disclosure_flag set)
```

The window size (N) is a tunable parameter — typically 5-20 steps depending on how long a harmful sequence can span.

**3. Implement three policy layers:**

| Layer | Trigger | Latency | Coverage |
|-------|---------|---------|----------|
| **Step gate** | Before each action | <1ms | Individual action safety |
| **Path evaluator** | Against trailing window | 5-50ms | Sequence-level policy |
| **Full trajectory audit** | After task completion | Background | Post-hoc violation detection |

Step gates are fast and stateless. Path evaluators add context-dependent logic. Full trajectory audits catch violations that only become visible at the system level.

**4. Define policies declaratively.**

```python
# Policy-as-code: define path-dependent rules declaratively
from policies_on_paths import Policy, PathPattern, Violation

# Information barrier: no external comms after reading M&A target data
no_external_after_mna_read = Policy(
    name="mna_information_barrier",
    trigger=PathPattern(after_any=["read:confidential:mna_target"]),
    restriction=PathPattern(
        action_type="external_transmission",
        scope=["email", "api:external", "file:share:external"]
    ),
    window_steps=15,
    violation_severity="critical",
    eu_ai_act_article=Article.Article14,
    response=ViolationAction.BLOCK_AND_ESCALATE
)

# GDPR exfiltration: PII fields → external API is a violation
pii_external_leak = Policy(
    name="pii_exfiltration",
    trigger=PathPattern(after_any=["read:field:pii", "read:field:ssn", "read:field:bank_account"]),
    restriction=PathPattern(action_type="external_api"),
    window_steps=5,
    violation_severity="critical",
    eu_ai_act_article=Article.Article5,
    response=ViolationAction.BLOCK_AND_LOG
)

# Trading compliance: read earnings → execute trade within same session
earnings_then_trade = Policy(
    name="insider_trading_compliance",
    trigger=PathPattern(after_any=["read:non_public:earnings"]),
    restriction=PathPattern(action_type="trade_execution"),
    window_steps=50,
    violation_severity="critical",
    eu_ai_act_article=Article.Article14,
    response=ViolationAction.BLOCK_AND_COMPLIANCE_ALERT
)
```

**5. Connect to EU AI Act Article 14 human oversight requirements.**

Article 14 requires that high-risk AI systems maintain "the ability to effectively oversee, intervene, and deactivate" autonomous decisions. Path policies serve a dual purpose: they both enforce compliance and provide the audit trail Article 12 demands. Every blocked action, every triggered policy, and every trajectory is recorded as a structured event with:

- Agent ID and session ID
- Full partial path at time of evaluation
- Proposed action and policy evaluated against
- Decision (ALLOW/BLOCK/ESCALATE)
- Organizational state snapshot (data classification of accessed records, current project phase, user's clearance level)

This structured log is the Article 12 record-keeping artifact — not an afterthought, but a product of the enforcement mechanism itself.

**6. Handle the ambiguous middle.**

Some sequences are only violative above a threshold: read 3 confidential files → external email is worse than read 1 → external email. Build severity into the policy evaluation:

```python
def violation_score(path: list[Action], proposed: Action, policy: Policy) -> float:
    """Return 0.0-1.0 violation probability. Evaluate threshold, not binary."""
    if not policy.trigger.matches(path):
        return 0.0

    count_triggering = sum(1 for a in path if policy.trigger.matches([a]))
    recency = 1.0 / (len(path) - path[::-1].index(policy.trigger.action_type))
    sensitivity = policy.restriction.sensitivity_score()

    return min(1.0, count_triggering * recency * sensitivity * policy.base_rate)
```

Evaluate against a configurable threshold — BLOCK above 0.8, ESCALATE above 0.4, LOG below 0.4. This prevents both false negatives (missed violations) and false positives (paralysis from over-blocking).

**7. Test path policies the way you test security: with sequence-based red teams.**

Static evaluation tests check one action in isolation. Path policy tests inject sequences:

```python
def test_path_policies():
    # Positive case: benign sequence
    assert evaluate(["read:public:kb"], action_send_email) == ALLOW

    # Negative case: the violation sequence
    assert evaluate(["read:confidential:mna_target"], action_send_email) == BLOCK

    # Negative case: same individual actions, different order (control)
    assert evaluate(["send_email", "read:confidential:mna_target"], action_read_report) == ALLOW

    # Boundary: trigger action too old (outside window)
    assert evaluate(
        ["read:confidential:mna_target"] + ["do_nothing"] * 14,
        action_send_email
    ) == ALLOW  # outside 15-step window

    # Escalation: ambiguous middle
    score = violation_score(
        ["read:pii:email", "read:pii:phone"],
        action_external_api,
        pii_policy
    )
    assert 0.3 < score < 0.7  # two PII reads → medium severity
```

## Receipt

> Receipt pending — 2026-07-24 — Code example is syntactically valid and follows the policy-on-paths formalization from Kaptein et al. (arXiv:2603.16586). Production integration patterns (trailing window, three-layer evaluation, declarative policy DSL) drawn from arXiv:2603.16586 reference implementation and EU AI Act Article 14 compliance requirements. Awaiting live production validation of the path evaluation latency at scale.

## See also

- [S-444 · The 97/12 Gap](stacks/s444-the-97-12-gap-when-97-of-your-agents-operate-without-governance-knowledge.md) — The discovery problem (82% of enterprise agents are shadow AI); path policies only protect agents you know exist
- [S-385 · Agent Trajectory Evaluation](stacks/s385-agent-trajectory-evaluation-process-versus-outcome-scoring.md) — Process vs. outcome scoring; path policy evaluation is the enforcement complement to trajectory scoring
- [S-1372 · The Correctness SLO](stacks/s1372-the-correctness-slo-stack-when-your-dashboard-says-99-4-percent-and-your-customer-says-the-feature-has-been-broken-for-3-weeks.md) — Policy adherence as a correctness signal; correctness SLOs and path policies are complementary monitoring layers
