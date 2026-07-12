# S-954 · The Policy Decision Point Stack — When Your Agent Authorizes Its Own Actions

The first time a regulator asks you to prove that your support agent did not access a Tier-2 customer's billing record on March 14th, you discover an unpleasant truth about your authorization architecture: the system prompt said "do not access billing for Tier-2," the YAML tool manifest listed `tools: [search_orders, refund_order, get_billing]`, and somewhere between those two artifacts, the model decided. There is no record of a decision — because no decision point existed. Whether the agent did the right thing is not auditable, only inferable from logs of what happened. This is the Policy Decision Point gap, and it is the difference between agent governance theater and agent governance engineering.

## Forces

- **System prompts are interpreted, not enforced.** A sufficiently tricky input, a chain of tool results that reframe the context, or a goal that drifts from the original intent can produce policy violations that are indistinguishable, to the tool loop, from legitimate actions.
- **YAML manifests stop scaling at conditions.** "This agent can call `refund_order` if the order belongs to the principal's tenant" requires runtime data — the tool manifest has no runtime. The gap between the manifest's allowed tools and the actual authorization logic is where policy violations live.
- **LLM-as-judge in the authorization layer amplifies both correctness and failure modes.** An LLM classifier can handle contextual nuance that static rules cannot, but it introduces non-determinism into what should be a boolean gate — and non-deterministic authorization is not authorization.
- **Compliance requires auditable decisions, not inferred compliance.** EU AI Act Article 12 requires demonstrable oversight. If you cannot produce a log entry for every authorization decision, you cannot produce an audit trail. A system prompt that says "behave ethically" satisfies no regulatory definition of oversight.
- **Agents compound authorization scope across tool chains.** A single authorized tool call can chain into three more tools, each of which crosses a trust boundary. Static tool-level permissions do not capture the authorization topology of a multi-step execution.

## The move

The fix is a **Policy Decision Point (PDP)** — a deterministic, auditable gate inserted between the LLM's tool call output and the tool's actual invocation. The PDP does not live in the system prompt. It lives in infrastructure code.

### The three-layer policy enforcement model

The Zylos research on policy engines for agent governance (2026-03-14) and Microsoft's Agent Governance Toolkit establish a three-layer model that composes with any agent framework:

**Layer 1 — Deterministic Policy Engine (ground truth)**
OPA/Rego or Cedar policies define the authorization surface: which principal can invoke which tool on which resource under which conditions. This is the enforcement boundary. Every policy evaluation produces a boolean and a log entry. This layer is always authoritative — when it says no, the tool does not execute.

```rego
# OPA/Rego example: Tier-based billing access control
package agent.authorization

default allow := false

allow if {
    input.tool == "get_billing"
    input.principal.tier != "tier2"
}

allow if {
    input.tool == "get_billing"
    input.principal.tier == "tier2"
    input.principal.flags[_] == "billing_exception"
}
```

**Layer 2 — LLM Advisory (classification, not decision)**
The LLM provides contextual classification that feeds into the policy engine: classify the user's intent, identify which resources the request targets, flag whether the request is in-scope for the current task. The LLM output is an input to Layer 1, not a replacement for it.

**Layer 3 — Audit and Provenance (the compliance layer)**
Every policy decision — allow or deny — is written to an immutable audit log with: timestamp, principal, requested tool, resource targets, session ID, task context hash, and the policy version used. This satisfies EU AI Act Article 12 oversight requirements.

### Inserting the PDP into the tool loop

The PDP wraps the tool call invocation. After the LLM outputs a tool call, before the tool executes:

```python
# Policy Decision Point — wraps every tool invocation
def invoke_tool(agent_id: str, tool: str, params: dict, session: Session) -> ToolResult:
    decision = policy_engine.evaluate(
        principal=session.principal,
        tool=tool,
        params=params,
        session_context=session.context(),
        policy_version=current_policy_version(),
    )

    audit_log.write(
        timestamp=datetime.utcnow(),
        agent_id=agent_id,
        principal=session.principal.id,
        tool=tool,
        params_hash=hash(params),
        decision=decision.allowed,
        reason=decision.reason,
        policy_version=current_policy_version(),
        session_id=session.id,
    )

    if not decision.allowed:
        return ToolResult(
            success=False,
            error=f"Policy denied: {decision.reason}",
            audit_ref=audit_log.last_entry_id(),
        )

    return actual_tool_invocation(tool, params)
```

### Fail modes and how to handle them

**Policy engine outage:** Define a fail-mode per tool. High-risk tools (financial transactions, data deletion, external communications) → fail-closed. Low-risk tools (read-only queries) → fail-open with alert. Never default to fail-open for high-risk surfaces.

**LLM advisory failure:** If the LLM classifier is unavailable, fall back to conservative defaults — classify as highest-privilege category, then evaluate against static policy rules only. The advisory layer is optional; the deterministic layer is not.

**Policy version drift:** Pin the policy version in the audit log entry. When policies update, existing sessions continue under the version they were granted under. New sessions use the new version. This prevents retroactive policy changes from invalidating running sessions in an un-auditable way.

**Tool chain authorization:** When a tool call triggers a secondary tool call, the PDP evaluates each leg independently. The authorization for `refund_order` calling `get_customer_balance` is not inherited — it is re-evaluated against the calling tool's declared scope and the principal's permissions for the secondary resource.

### The audit-ready deployment checklist

1. Enumerate every tool your agents can call and classify by risk level (financial / data-access / communication / destructive)
2. Write OPA or Cedar policies for every high-risk tool — "can this principal call this tool on this resource right now?"
3. Deploy the PDP in shadow mode first: log every decision without enforcing, measure false-negative rate against your eval set
4. Roll out enforcement gradually: low-risk tools first, with automatic rollback on error rate spike
5. Wire every decision to your immutable audit log with principal, session, policy version, and decision reason
6. Run monthly policy reviews: expired exceptions, orphaned policies, and shadow grants accumulate without active hygiene

## Receipt

> Verified 2026-07-11 — Architecture validated against OPA/Rego policy engine patterns documented in tianpan.co (2026-04-25) and Zylos Research (2026-03-14). Code example is a working Python skeleton. Fail-mode policies are the production-tested approach from Microsoft Agent Governance Toolkit (microsoft.github.io/agent-governance-toolkit, 2026). EU AI Act Article 12 compliance implications confirmed against CSA guidance (cloudsecurityalliance.org, 2026-03-19).

## See also

- [S-217 · Agent Capability Authorization](stacks/s217-agent-capability-authorization.md) — the authorization model; this entry fills the runtime enforcement gap
- [S-444 · The 97/12 Gap](stacks/s444-the-97-12-gap-agent-governance-discovery.md) — why most enterprises cannot answer "which agents can do what"; PDP provides the answer
- [S-454 · Agent Behavioral Contracts](stacks/s454-agent-behavioral-contracts-design-by-contract-for-the-autonomous-era.md) — declarative policy specification; PDP provides the runtime enforcement layer
- [S-535 · Agent Audit Trail Engineering](stacks/s535-agent-audit-trail-engineering-eu-ai-act-article-12.md) — the audit layer; PDP is the source of the events the audit layer records
