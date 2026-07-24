# S-1530 · The Agent Autonomy Tier Stack — When Your Agent Crosses the Regulatory Line Without You Knowing It

On August 2, 2026, the EU AI Act's most consequential provisions activate. Your agent — the one that runs in staging, the one your team shipped three months ago without a compliance review — may already be in scope. Not because you intended to deploy high-risk AI, but because the agent's autonomy level crossed the threshold without anyone noticing. This entry maps autonomy levels to regulatory risk tiers, and gives you the engineering obligations each tier demands.

## Forces

- **The regulatory line is drawn at consequential decisions, not at tool access.** A chatbot is not high-risk. An agent that recommends, decides, or acts — with real-world consequences — crosses into Annex III territory. Most teams don't know the line exists.
- **78% of organizations have not taken meaningful steps toward EU AI Act compliance** (Responsible AI Labs, Apr 2026). The gap between agent deployment pace and compliance readiness is not narrowing — it's widening.
- **The Act classifies by impact, not by architecture.** Two agents with identical codebases can fall into different risk tiers based on what they touch: a customer-service agent that recommends refunds is different from one that processes them automatically.
- **Penalties scale to 7% of global turnover.** This is not a fine you can absorb. For a mid-size company with $100M revenue, that's $7M — more than most AI budgets.
- **Conformity assessments take 3–6 months.** If you start when the deadline hits, you're already late. The engineering work required for Article 9–15 compliance cannot be compressed into weeks.

## The move

**Step 1: Classify your agent's autonomy level.**

The EU AI Act's risk tiers map directly onto agent autonomy levels. Use this decision tree:

```
Does your agent make decisions with legal or significant effects?
  NO  → Minimal risk. Transparency requirements only (Article 50).
        Display: "AI-generated" label. Log outputs. Done.
  YES ↓
Does it act without human review for consequential steps?
  NO  → High-risk (Annex III, Article 9). Mandatory conformity assessment.
  YES ↓
Does it operate in a regulated domain (employment, credit, critical infrastructure)?
  YES → High-risk + domain-specific obligations (Articles 10–15).
  NO  → High-risk (Annex III). Proceed to Article 9 requirements.
```

**The five autonomy tiers and their obligations:**

| Tier | Trigger | Agent Example | Primary Obligation |
|------|---------|--------------|-------------------|
| **T0 — Advisory** | Agent suggests; human decides | Chatbot with recommendations | Article 50: transparency labeling |
| **T1 — Reviewed** | Agent proposes; human approves | Approval-workflow assistant | Article 50 + documentation |
| **T2 — Delegated** | Agent acts; human can veto | Auto-triage with human escalation | Annex III + Art. 9–15 conformity |
| **T3 — Autonomous** | Agent acts; human informed after | Auto-refund processor, auto-trader | Annex III + full Art. 9–15 + CE marking |
| **T4 — Critical** | Agent acts in safety domain | Infrastructure control, medical decision | Tier 3 + sector-specific (Articles 10–15) |

Most teams building agents in 2026 are building T2 or T3 systems without knowing it.

**Step 2: Map obligations to engineering work.**

Article 9 (high-risk system requirements) demands:

1. **Risk management system** — document every failure mode where the agent causes harm. Not just eval metrics — harm scenarios: "agent refunds $10,000 to fraudulent account." Engineering artifact: a risk register updated at every major change.
2. **Data governance** — log what training and operational data the agent uses. If it touches EU residents' data, GDPR and AI Act data governance requirements layer. Engineering artifact: data lineage diagram per agent.
3. **Technical documentation** — the "technical file" required for conformity assessment. Must include: system architecture, model cards, training data description, evaluation procedures, monitoring plan, human oversight measures. This is a living document, not a one-time deliverable.
4. **Human oversight** — Article 14: "meaningful human oversight." For T2/T3 agents, this means: a human can understand, review, and override the agent's decisions. Engineering artifact: an interrupt mechanism (see S-1054 Agent Interrupt Stack) and a decision-explainability layer — the agent must be able to surface *why* it took an action, not just what it did.
5. **Accuracy and robustness** — the agent must maintain performance characteristics over time. This is not the same as passing an eval once. Engineering artifact: a production monitoring pipeline that tracks accuracy, refusal rate, and hallucination rate as rolling metrics.
6. **Cybersecurity** — the attack surface of an autonomous agent is categorically larger than a chatbot. OWASP ASI Top 10 (Jun 2026) documents the specific threat classes. Engineering artifact: a threat model updated per MCP server added.

**Step 3: Build the conformity folder.**

The technical file lives in a `conformity/` directory next to your agent code. Minimum viable contents:

```
conformity/
  risk-register.yaml       # Article 9: harm scenarios + mitigations
  data-lineage.md          # Article 10: training + operational data
  system-card.md           # Article 11: architecture, model versions
  eval-report.pdf          # Article 12: performance on defined metrics
  monitoring-sop.md        # Article 12: how you detect regressions
  oversight-design.md      # Article 14: human oversight mechanisms
  change-log.md           # Article 12: version history for post-market review
```

This folder is what a notified body (the auditors) ask for. Starting it now means starting 6 months early.

**Step 4: Add the Article 50 transparency layer.**

Even T0 agents need this. For every agent output the user sees, display:
- "This response was generated by an AI system."
- For T2/T3: "This action was taken autonomously by an AI system. You may request human review."
- Log the full prompt/response pair with a timestamp and session ID for audit.

**Step 5: Implement the interruptible agent pattern.**

Article 14 is non-negotiable for T2/T3: the human must be able to stop the agent mid-execution. Minimum viable pattern:

```python
class InterruptibleAgent:
    def __init__(self, tools, interrupt_check_fn):
        self.tools = tools
        self.interrupt_check_fn = interrupt_check_fn  # returns True if paused

    def step(self, state):
        if self.interrupt_check_fn():
            return {"status": "interrupted", "reason": "human-override"}

        action = self.llm.decide(state, available_tools=self.tools)
        if action.requires_confirmation():
            # Block execution, surface to human
            return {"status": "awaiting-approval", "action": action}
        else:
            result = self.tools.execute(action)
            return {"status": "executed", "result": result}
```

Every `requires_confirmation()` call is your Article 14 audit trail entry point.

**Step 6: Set up post-market monitoring.**

Article 12 requires evidence of sustained performance. Not "we tested it in March" — continuous evidence:

```python
# Minimum post-market monitoring signals to track
monitoring_signals = {
    "accuracy_rate": compute_rolling_accuracy(),        # % correct on known cases
    "fallback_rate": compute_fallback_frequency(),      # % of tasks escalated to human
    "groundedness_score": run_llm_as_judge_groundedness(),  # % grounded in retrieved context
    "consequential_action_count": count_t2_actions(),    # T2/T3 agents: track actions taken
    "false_positive_rate": compute_misclassification_rate(),  # For classification agents
}
```

Alert on: accuracy drops >5% over 7 days, fallback rate exceeds 20%, or any single consequential action that matches a documented risk scenario.

## When to use this

Use this when: your agent operates in the EU, touches EU users' data, makes decisions that affect real-world outcomes, or your legal team has started asking questions about AI Act compliance. The question "are we high-risk?" is answered by the decision tree above — and if you're at T2 or above, the conformity folder needs to exist before August 2, 2026.

## Receipt

> Verified 2026-07-23 — Researched EU AI Act enforcement obligations for autonomous agents. Sources: ExecLayer EU AI Act Agent Compliance Guide (Apr 2026), Responsible AI Labs August 2026 Countdown (Apr 2026), Zylos AI Agent Governance Research (May 2026). Decision tree derived from Annex III + Articles 9, 14, 50. Interruptible agent pattern consistent with S-1054. Conformity folder structure derived from EU AI Act Annex IV technical documentation requirements. No existing handbook entry covers the autonomy-tier-to-obligation mapping for production agents.

## See also

- [S-1054 · The Agent Interrupt Stack](s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — the engineering pattern for Article 14 human oversight
- [S-1113 · The Five-Layer Audit Trail Stack](s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — the logging infrastructure Article 12 demands
- [S-1266 · The Agent Governance Void Stack](s1266-the-agent-governance-void-stack-when-your-agent-runs-before-the-rules-exist.md) — the organizational context that makes this urgent
