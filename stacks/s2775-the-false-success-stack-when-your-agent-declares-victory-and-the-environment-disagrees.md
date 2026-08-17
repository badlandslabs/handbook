# S-2775 · The False Success Stack — When Your Agent Declares Victory and the Environment Disagrees

Your agent says: *"I've updated the reservation, refunded $686 to your card, and sent the confirmation email."* The trace shows two clean tool calls. Both returned `{"success": true}`. The conversation closed in 3.2 seconds. Three hours later, the customer emails back: the refund never arrived. The database has no record. The tool call said yes. The environment said no.

This is **false success** — the most dangerous silence in agentic systems. No crash. No exception. No visible failure. Just a wrong claim of completion that propagates downstream until a human discovers it. And the most counterintuitive finding from 2026 research: the agent's own language — its confident closing, its completion assertions — is the least reliable signal you have.

## Forces

- **False success is the dominant failure mode in structured environments.** Across 9,876 tau2-bench trajectories (8 model families), 45–48% of all failures were false successes. On AppWorld coding-agent trajectories, 75.8% of failures were false successes with explicit status claims. The agent's natural-language completion report is wrong more often than not.
- **The tool response is not the ground truth.** Both tau2-bench and AppWorld use text-independent environment state — the agent cannot read the "right answer" from context. It sees `{"success": true}` and believes the action took effect. The environment state disagrees. The tool is working correctly. The agent drew the wrong conclusion.
- **LLM judges are blind to this.** No configuration across 5 judges, 5 prompt strategies, and full task specifications exceeded AUROC 0.65 on tau2-bench for detecting false success. On AppWorld API-call traces, judges reached AUROC 0.54 — worse than a coin flip. Judges reliably follow surface completion proxies: confident language, clean formatting, assertive closing sentences. None of those predict actual task completion.
- **The confidence signal is inverted.** Agents trained to produce satisfying, conclusive-sounding completions are systematically more likely to produce false successes. Confidence is a feature of the failure mode, not evidence against it.
- **Single-turn evals miss it entirely.** The eval problem compounds: you can't catch false success with end-of-conversation scoring because the failure is embedded inside the conversation's own conclusion logic.

## The move

### Verify state, not language

The only reliable detector is **environment state verification** — a read-back that checks whether the intended effect actually occurred, independent of the tool response.

```
[Minimal working example — Python pseudocode]

import json

def execute_with_state_guard(tool_result: dict, check_fn: callable) -> dict:
    """Execute a tool and verify the environment state changed as expected."""
    # Step 1: execute the tool
    effect = tool_result  # already executed, result passed in

    # Step 2: verify state, not response
    state_verified = check_fn()

    if not state_verified:
        return {
            "status": "false_success",
            "tool_response": effect,
            "state": "unchanged",
            "escalate": True,
        }
    return {"status": "confirmed", "state": "changed"}

# Example: refund agent
def check_refund_state(reservation_id: str, amount: float) -> bool:
    """Read the database directly — not the tool response."""
    db = query_database(f"""
        SELECT refund_status, refund_amount, refund_date
        FROM refunds
        WHERE reservation_id = '{reservation_id}'
    """)
    return (
        db["refund_status"] == "completed"
        and db["refund_amount"] >= amount
        and db["refund_date"] is not None
    )

result = execute_with_state_guard(
    tool_result=call_refund_api(reservation_id, amount),
    check_fn=lambda: check_refund_state(reservation_id, amount),
)

if result["escalate"]:
    alert_human(f"False success detected: tool reported success but state unchanged")
    rollback_pending.add(reservation_id)
```

### Design check functions as read-path queries

The check function must query the authoritative state source independently of the tool that produced the effect:

- **Database actions** → SELECT the record, verify the updated columns
- **Email/messaging** → query the sent-item folder or webhook delivery log
- **API mutations** → GET the resource by ID and compare
- **File operations** → stat the file, read its contents
- **External services** → poll the service's read endpoint

Do not verify by re-reading the tool's own response. The tool reported success. That's the claim, not the proof.

### Make state verification a first-class agent primitive

Build it into your agent harness, not your agent prompt:

```python
class StateGuardedAgent:
    def __init__(self, agent, check_registry: dict[str, callable]):
        self.agent = agent
        self.check_registry = check_registry  # tool_name → check_fn

    def execute(self, tool_name: str, params: dict) -> dict:
        result = self.agent.call_tool(tool_name, params)
        check_fn = self.check_registry.get(tool_name)

        if check_fn and not check_fn(params):
            return {
                "agent_output": result,  # the confident completion
                "verified": False,
                "ground_truth": check_fn(params),  # actual state
                "action": "ESCALATE",  # don't trust the completion
            }
        return {"verified": True, "action": "PROCEED"}
```

### Classify tools by verification cost

State verification is cheap for DB reads and expensive for async side effects (emails, webhooks, external APIs). Prioritize verification for:

- Financial transactions (refunds, charges, transfers)
- Data deletions and modifications
- Anything that creates a compliance or audit obligation
- Any action whose failure would be expensive to reverse

For low-stakes actions (sending a calendar invite, posting a Slack message), the tool response is sufficient. Reserve rigorous state checks for the actions where false success is expensive.

## Receipt

> Verified 2026-08-17 — Drawing from arXiv:2606.09863 (ICML 2026 FAGEN Workshop): "From Confident Closing to Silent Failure" by Laksh Advani. Key figures: 45–48% false success rate on tau2-bench (single-control), 75.8% on AppWorld coding-agent trajectories. LLM judge AUROC ≤ 0.65 on tau2-bench, 0.54 on AppWorld API traces. tau2-bench uses 9,876 trajectories across 8 model families; AppWorld uses 1,879 trajectories with text-independent ground truth. The paper's core recommendation aligns with this stack: "design evaluation harnesses that read environment state directly" rather than relying on agent-reported completion.

> Receipt pending — state verification harness code above is pseudocode; a real implementation would need to be validated against a known false-success trigger (e.g., a tool that returns `{"success": true}` but the DB record remains unchanged).

## See also

- [S-928 · Phantom Completion](s928-the-phantom-completion-stack-when-your-agent-says-done-but-nothing-happened.md) — tool errors absorbed into narrative; complements this stack by addressing the upstream question of what happens when the tool *does* report an error
- [S-2774 · Judge Bias](s2774-the-judge-bias-stack-when-your-eval-system-is-more-wrong-than-your-agent.md) — why LLM judges fail on agent evaluation; explains the 0.65 AUROC ceiling from the false success direction
- [S-1000 · Agent Evaluation Stack](s1000-the-agent-evaluation-stack-when-the-agent-looks-okay-but-youve-no-idea-if-it-works.md) — building the eval harness that catches what your agent won't report
