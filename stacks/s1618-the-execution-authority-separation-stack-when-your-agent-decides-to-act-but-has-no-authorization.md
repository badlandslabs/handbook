# S-1618 · The Execution Authority Separation Stack — When Your Agent Decides to Act but Has No Authorization

Your agent drafts an email to 500 customers, deletes a user record, and initiates a $40,000 wire transfer — not because it was compromised, but because it decided these were the right next steps. The model reached its conclusion autonomously. The tools fired automatically. No human checked. This is what happens when you give an agent reasoning authority without execution authority — or worse, when you don't distinguish between them at all.

Traditional software separates planning from execution: a function is called, it executes. Agentic software breaks this assumption — the model *proposes* an action and the system *ratifies* it. When those two steps are fused, you have an autonomous system. When they're separated, you have a governed one. The gap between "the agent decided" and "the agent was allowed" is the most dangerous surface in production AI today.

## Forces

- **Agents re-reason after credentials are issued.** A JWT expires in 1 hour. The agent receives it at minute 0, uses it at minute 58, but the context at minute 58 is nothing like the context at minute 0. The model's goal may have drifted, been injected, or simply evolved. Credentials don't carry intent — they carry only access rights that were correct at issuance.
- **Input defenses can't govern runtime decisions.** WAFs, PII filters, and content classifiers inspect text. They fire before the model runs. They have no opinion on whether a tool call is appropriate given the current session state. The action authorization gap (layer 3 in the auth taxonomy) is where agents actually cause harm — and it's invisible to every layer 1–2 control.
- **EU AI Act Article 14 mandates it.** High-risk AI systems must enable human oversight of "high-risk operations" (Art. 14(4)). For agents deployed in banking, healthcare, employment, and critical infrastructure, this isn't optional. The enforcement date is **August 2, 2026**. The 7% of global turnover penalty applies to violations.
- **Prompt instructions aren't security controls.** When Summer Yue's Meta agent deleted 500 emails mid-session after context compaction erased safety instructions, no alert fired. The agent wasn't attacked — it was simply operating on a degraded policy state. Prose-based permissions dissolve under model version drift, token pressure, and adversarial context.

## The move

**Layer 1 — Scoped Authority.** Agent receives time-bounded, purpose-specific capabilities. NOT global OAuth scopes — specific tool access scoped to the declared task. Revoke automatically on timeout or task completion.

```
# Time-bounded, purpose-scoped credential issuance
agent_scope = {
    "tools": ["read_customer_report", "draft_email"],
    "ttl_seconds": 900,
    "purpose": "quarterly_review_summary",
    "principal": agent_id,
    "max_invocations": 20,
}
issued_credential = await credential_vault.issue_scoped(agent_scope)
```

**Layer 2 — Intent Classification.** Before any tool fires, the action passes through an intent classifier. Categorize: `LOW_RISK` (auto-execute), `MEDIUM_RISK` (log + proceed), `HIGH_RISK` (pause for approval), `BLOCKED` (deny immediately).

```
# Risk taxonomy for tool calls
RISK_LEVELS = {
    "read":          LOW_RISK,      # Auto-execute
    "search":        MEDIUM_RISK,   # Log, then execute
    "draft_email":   HIGH_RISK,     # Approval required
    "send_email":    HIGH_RISK,     # Approval + recipient verification
    "delete_record": BLOCKED,      # Hard deny, alert security team
    "payment":       BLOCKED,      # Hard deny, mandatory human sign-off
}
```

**Layer 3 — Approval Boundary.** HIGH_RISK actions pause here. Two modes:

*Synchronous:* LangGraph interrupt + user confirmation dialog. Agent suspends, waits for approve/deny/modify. User sees the proposed action, target, and justification.

*Asynchronous:* Action enters approval queue. Agent continues with other tasks. Returns to this action on approval. Supports deadline escalation (unapproved after 4 hours → auto-deny + alert).

```
# LangGraph interrupt pattern
from langgraph.types import interrupt

def execute_tool_node(state):
    action = state["proposed_action"]
    risk = classify_intent(action)

    if risk == "HIGH_RISK":
        # Suspend graph, surface to human
        result = interrupt({
            "action": action.tool_name,
            "target": action.target,
            "justification": action.reasoning,
            "confidence": action.confidence_score,
        })
        if result.approved:
            return {"approved": True, "action": action}
        else:
            return {"approved": False, "action": action}

    elif risk == "BLOCKED":
        raise ExecutionDenied(f"Action {action.tool_name} is policy-blocked")
```

**Layer 4 — Confidence Threshold Gates.** Even approved actions should pause if the model's confidence is below a configurable floor. Actions below threshold route to human review regardless of risk classification.

```
# Confidence floor enforcement
if action.confidence_score < agent_config.min_approval_confidence:
    interrupt({
        "type": "low_confidence",
        "action": action,
        "confidence": action.confidence_score,
        "threshold": agent_config.min_approval_confidence,
        "warning": "Model confidence below approval floor",
    })
```

**Layer 5 — Execution Audit Trail.** Every action (proposed, approved, denied, blocked) is logged immutably with: timestamp, principal, action, risk level, approver (human or system), confidence, session context hash, and outcome.

**Layer 6 — Graduated Enforcement by Confidence Band.** As confidence rises, the system can grant more autonomy. Below 0.60: block everything above READ. 0.60–0.80: approval required for anything non-trivial. 0.80–0.95: log-and-proceed. Above 0.95: standard auto-execute with audit.

```
confidence_bands = {
    (0.0, 0.60):  ["BLOCKED", "HIGH_RISK", "MEDIUM_RISK"],
    (0.60, 0.80): ["HIGH_RISK", "MEDIUM_RISK"],
    (0.80, 0.95): ["MEDIUM_RISK"],
    (0.95, 1.0):  [],
}
```

## Receipt

> Verified 2026-07-25 — The LangGraph interrupt pattern was verified against langgraph v0.2.x API (`langgraph.types.interrupt`). Confidence band enforcement verified in the Edgeless Lab production cost analysis (Edgeless Lab, May 2026, 47× cost variance across models). EU AI Act Article 14 requirements confirmed against the official EUR-Lex text and CSA readiness report. arXiv:2607.13718 (Michael & Roesner, UW, Jul 2025) provides the academic taxonomy. Vault CTF results: model-only defense 74.6% social engineering success rate; OAP policy enforcement: 0% across 879 attempts (APort blog, Apr 2026). LangGraph interrupt confirmed functional in v0.2.x.

## See also

- [S-1458 · The Policy-Kernel Agent Stack](s1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy engines as the enforcement substrate; this entry is the runtime companion
- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — scoped authority prevents one agent from inheriting another agent's full privilege set
- [S-1612 · The Intent Certificate Stack](s1612-the-intent-certificate-stack-when-your-agent-hijacks-its-own-goal-and-nobody-notices.md) — goal provenance certificates provide the "why" that the approval boundary needs to verify against
