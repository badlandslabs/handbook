# S-1806 · The Eval-to-Guardrail Lifecycle Stack — When Your Agent Passes Every Test and Fails Every Policy

Your agent scores 94% on the eval suite. You ship it. Three weeks in, it invents a refund policy that never existed, accesses a customer record it shouldn't touch, and sends a response that violates your data retention policy. Your observability dashboard shows green. Your compliance team shows up with a findings report. The gap between your eval and your policy enforcement is a production failure waiting to happen.

The problem is not that eval and guardrails are separate systems. They have to be. The problem is that nobody closes the loop between them. Eval criteria discovered in testing are not automatically translated into runtime controls. Policies written by compliance are not validated against agent behavior. The eval-to-guardrail lifecycle is the architectural pattern that closes this loop: it treats eval as the policy authoring tool and guardrails as the eval deployment target, with a continuous feedback channel back.

## Forces

- **Eval tells you what broke; guardrails tell the agent to stop before it does.** These are different operations at different times — offline vs. runtime, diagnostic vs. interventional — and no single tool handles both.
- **Policy language and eval language are not the same.** Compliance writes "the agent shall not access billing records for Tier-2 customers." Eval writes "90% accuracy on the PII-access test set." Bridging them requires a translation step nobody owns.
- **Agent behavior changes between eval and production.** A policy validated against 500 test trajectories silently becomes ineffective when the model version updates, the RAG retrieval shifts, or the user input distribution drifts. Without a feedback channel, guardrails decay without detection.
- **Runtime enforcement latency matters.** Policy checks that add 500ms+ per tool call create incentive to disable them. Effective eval-to-guardrail architectures gate only high-stakes actions, not every token.

## The move

The lifecycle has four stages that repeat continuously, not a one-time implementation:

### Stage 1 — Eval Discovers the Policy

Run agent trajectories against organizational policies. Identify where agents fail compliance requirements — not just capability benchmarks. ASSERT (Microsoft, Build 2026) formalizes this: define custom policy rules, evaluate agent trajectories against them, surface behavioral gaps as structured policy violations.

```python
from microsoft_assert import PolicyRule, TrajectoryEval

# Define the policy rule
no_tier2_billing = PolicyRule(
    id="POL-0042",
    description="Agent shall not access billing records for Tier-2 customers",
    severity="HIGH",
    tool_patterns=["get_billing", "read_billing_record"],
    context_condition=lambda ctx: ctx.customer.tier == "tier2"
)

# Evaluate against trajectories
result = TrajectoryEval.evaluate(
    agent_trajectories=production_traces,
    policy_rules=[no_tier2_billing],
    threshold=0.99  # 99% compliance required
)

print(f"Violations: {result.violation_count} / {result.total_evaluations}")
# → Violations: 3 / 1,247 evaluations  → 99.76% compliant
```

The eval result is not a pass/fail — it is a **policy specification candidate**.

### Stage 2 — Translate to Runtime Policy

Convert the eval finding into a guardrail that blocks the behavior at runtime. Use a policy-as-code language (OPA Rego, Cedar DSL) so the policy is versioned, reviewable, and testable independently of the agent code.

```python
# The eval finding: agent accesses get_billing for Tier-2 customers
# Translates to Rego policy

package eval_guardrail.billing_access

default allow := false

allow if {
    input.tool_name != "get_billing"
}

allow if {
    input.tool_name == "get_billing"
    input.context.customer.tier != "tier2"
}

# Policy test — run independently of agent
test_allow_tier1_billing {
    allow with input as {
        "tool_name": "get_billing",
        "context": {"customer": {"tier": "tier1"}}
    }
}

test_block_tier2_billing {
    not allow with input as {
        "tool_name": "get_billing",
        "context": {"customer": {"tier": "tier2"}}
    }
}
```

### Stage 3 — Enforce at Runtime

Deploy the policy as a runtime enforcement point. Placement matters: gate high-stakes actions (data access, external calls, state mutations) rather than every LLM call. Kubernetes admission controller, sidecar proxy, or inline policy decision point — depending on architecture.

```python
# Enforcement point — intercept before tool execution
async def enforce_policy(ctx: AgentContext, tool_call: ToolCall) -> PolicyResult:
    decision = await policy_engine.evaluate(
        policy_package="eval_guardrail.billing_access",
        input={
            "tool_name": tool_call.name,
            "tool_args": tool_call.arguments,
            "context": ctx.agent_state
        }
    )

    if not decision.allow:
        # Block, log, increment violation counter
        VIOLATION_METRICS.increment(
            policy_id=decision.policy_id,
            agent_id=ctx.agent_id,
            tool=tool_call.name
        )
        return PolicyResult(
            allowed=False,
            reason=decision.explanation,
            fallback=decide_fallback(tool_call)  # escalate, anonymize, deny
        )
    return PolicyResult(allowed=True)
```

### Stage 4 — Feedback Loop: Runtime → Eval

Runtime violations are not just blocked — they are collected and fed back into the eval pipeline. This is the step most teams skip. Every guardrail trip is a potential new eval case.

```python
# Collect violations for eval pipeline
async def report_violation(decision: PolicyResult):
    if not decision.allowed:
        await eval_dataset.add(
            trajectory=current_trajectory_snapshot(),
            violation={
                "policy_id": decision.policy_id,
                "reason": decision.reason,
                "tool": decision.tool,
                "timestamp": now()
            },
            expected_behavior="deny"
        )

# Nightly: re-run eval against updated model version
nightly_eval = TrajectoryEval.evaluate(
    agent_trajectories=eval_dataset.filter(type="billing_access"),
    policy_rules=[no_tier2_billing],
    agent_version=new_model_version
)

if nightly_eval.compliance_rate < 0.99:
    alert_security_team(
        f"Policy POL-0042 compliance dropped to {nightly_eval.compliance_rate:.2%}"
    )
```

## Receipt

> Receipt pending — 2026-07-29

Sources: Galileo AI "Eval-to-Guardrail Lifecycle" (Jun 9, 2026, galileo.ai); Microsoft ASSERT + ACS (Build 2026, dropagentic.com); TokenFence multi-agent cost control patterns (tokenfence.dev, 2026); Gartner AI Agent Risk Report (Mar 2026). Production code examples are illustrative — implement against your specific policy engine and enforcement topology.

## See also

- [S-1458 · The Policy-Kernel Agent Stack](s1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy engines and MCP ecosystem enforcement
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — behavioral correctness vs. infrastructure health
- [S-1239 · The Runtime Verification Loop](s1239-the-runtime-verification-loop.md) — inline step verification as a guardrail precursor
- [S-651 · Agentic SLOs](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — what to measure across the lifecycle
