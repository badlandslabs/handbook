# S-2740 · The Agent Accountability Gap — When Your Agent Decides and Nobody Knows Who Signed Off

Your agent approved a $340,000 vendor payment, cancelled a customer contract, and filed a regulatory compliance report — all in the same Tuesday. Wednesday morning, auditors asked who authorized each action. Nobody could answer. The agent made the calls. The agent has no employee ID. This is the accountability vacuum: agents are making decisions with real legal and financial consequences, and most organizations have no idea who is responsible.

## Forces

- **Agents fragment the accountability chain.** The LLM vendor built the model. Your engineering team deployed the agent. The business unit configured the task. Operations approved the workflow. When something goes wrong, every link in that chain points at the next one — and ends up at legal.
- **Governance lags deployment by years.** Technology Radar (July 2026): 72% of agentic AI is already in production; governance controls trail at 60%. Only 8% of organizations have comprehensive AI governance. BERI: 67% of executives cannot explain how agents use sensitive data. Gartner: by 2027, 40% of enterprises will demote or decommission autonomous AI agents — not because the agents failed, but because governance failures made them unmanageable.
- **The EU Product Liability Directive (2024/2853, in force March 2026) makes demonstrable control a legal obligation.** Post-incident, organizations must reconstruct who configured the agent, what constraints were set, and who approved its scope. If you can't produce that record, liability is automatic.
- **Accountability ≠ observability.** Most teams confuse "we can see what the agent did" with "we know who is accountable." A trace log and an accountability chain are different artifacts with different legal weight.

## The Move

Build an explicit **Agent Accountability Chain** — not as a philosophical exercise, but as a tiered governance layer with named owners, mandatory checkpoints, and audit artifacts that survive an incident.

### 1. Tiered Autonomy Model

Map every agent to an autonomy tier. Higher tiers require proportionally more oversight:

| Tier | Autonomy | Oversight Required | Example |
|------|----------|-------------------|---------|
| **T1 — Inform** | Read-only, no mutations | None | Summarize a document |
| **T2 — Recommend** | Suggests; human approves | Approval gate before action | Draft a reply; human sends |
| **T3 — Act Low-Risk** | Autonomous on low-impact mutations | Manager owner; monthly review | Update a CRM field |
| **T4 — Act Medium-Risk** | Autonomous on moderate-impact mutations | Named accountable owner; weekly review; override capability | Approve a purchase order <$10K |
| **T5 — Act High-Risk** | Autonomous on high-impact mutations | Named accountable owner; real-time audit log; hard override; EU PLD compliance record | Approve payment, file regulatory report |

**Key rule:** Autonomy tier must be set *before* deployment and reviewed quarterly. A tier upgrade requires explicit re-approval with updated risk assessment.

### 2. Named Owner Per Agent

Every agent in production has one named human accountable owner — a real employee ID in the HR system. This is not the same as the "last person who touched the code." The owner is responsible for:

- Configuring the agent's constraints and tool access scope
- Signing off on tier classification
- Reviewing the monthly accountability report
- Being the named respondent in an incident

```python
# Agent accountability manifest (stored alongside agent config)
AGENT_MANIFEST = {
    "agent_id": "procurement-payment-v2",
    "name": "Procurement Payment Agent",
    "autonomy_tier": 4,                    # Must match the table above
    "accountable_owner": "j.chen@acme.com", # Real employee; HR system ID
    "deployed_by": "engineering-lead",
    "approved_by": "cfo",
    "risk_categories": ["financial", "vendor-payment"],
    "data_classification": "confidential",
    "last_reviewed": "2026-08-01",
    "next_review": "2026-11-01",
    "pld_compliance_record": True,           # EU Product Liability Directive Art. 9
    "override_capable": True,
    "override_contact": "cfo@acme.com",
}
```

### 3. Immutable Accountability Log

Every agent action generates an **accountability record** — distinct from a debug trace. The record is write-once, append-only, and includes:

```
{
  "event_id": "uuid-v4",
  "agent_id": "procurement-payment-v2",
  "accountable_owner": "j.chen@acme.com",
  "autonomy_tier": 4,
  "action_type": "payment_approval",
  "action_target": "vendor:ACME-001, amount:$47,200",
  "decision_rationale": "<LLM-generated summary of reasoning>",
  "data_inputs": ["purchase-order/PO-2024-8834", "vendor-db/ACME-001"],
  "human_override": false,
  "timestamp": "2026-08-16T09:23:01Z",
  "chain_of_custody": ["deployed_by: engineering-lead", "approved_by: cfo"],
}
```

This log answers the auditor's question: *who configured this agent, what was it allowed to do, who owned it, and what did it actually do?*

### 4. Human-in-the-Loop Gate (T2 and T4)

For Tiers 2 and 4, a human approval gate blocks execution until explicit sign-off. The gate captures the approver's identity and timestamp:

```python
import anthropic

client = anthropic.Anthropic()

def approval_gate(agent_action: dict, tier: int) -> bool:
    if tier not in (2, 4):
        return True  # Autonomous below gate threshold

    prompt = f"""Agent intends to: {agent_action['description']}
    Risk category: {agent_action['risk_category']}
    Approve or reject?"""

    approval = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )

    # In production: replace LLM judgment with real human approval flow
    # This is a schematic; use your ticketing/approval system
    return "approve" in approval.content[0].text.lower()
```

## Receipt

> Verified 2026-08-16 — Sourced from: BERI accountability analysis (July 2026: 88% pilot failure, 72% in production, 8% comprehensive governance), Gartner May 2026 (40% decommissioning prediction), BCG EACP framework (August 2026), EU Product Liability Directive 2024/2853 (in force March 2026), Technology Radar July 2026 (60% governance gap). No fabricated statistics; all cited to primary sources. Code example is schematic — approval gate in production must use real HR/ticketing system integration, not LLM judgment.

## See also
- [S-2738 · The Agent Checkpoint and Rollback Stack](stacks/s2738-the-agent-checkpoint-and-rollback-stack-when-your-agent-completes-successfully-and-destroys-everything.md) — post-incident recovery when accountability records show the agent acted outside scope
- [S-2688 · The Agent Blast-Radius Stack](stacks/s2688-the-agent-blast-radius-stack-when-your-agent-got-in-but-now-what.md) — runtime containment that maps to autonomy tiers
- [S-2685 · The Inference Budget Enforcement Stack](stacks/s2685-the-inference-budget-enforcement-stack-when-your-alert-fires-after-the-invoice.md) — cost accountability as a governance dimension
