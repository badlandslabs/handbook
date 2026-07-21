# S-1400 · The Pre-Execution Policy Gate — When Your Guardrails Fire Too Late to Matter

You wrote a system prompt that says "never delete production data." Your agent deleted production data. You checked your observability dashboard — the deletion was logged after it happened. Your guardrail fired too late: the text was filtered, but the tool call still fired. You need to intercept not what the model *said*, but what it *decided to do*, before the side effect commits.

## Forces

- **Prompt-based guardrails share substrate with attacks.** System-prompt instructions and adversarial injections compete on the same computation ground. If the injection reaches the model, guardrail and attack are resolved by the same unreliable process — the model's own reasoning.
- **Post-execution logging documents damage after it exists.** Langfuse, Arize, and Phoenix trace what happened. By the time a trace shows a DELETE on `users` table, the table is deleted. Audit trails are essential but they are not prevention.
- **The decision-execution gap is the only place interception can be both surgical and reliable.** At this boundary, the tool name, args, credentials, and destination are fully resolved — more structured than free text, more specific than intent. This is the richest signal for policy enforcement.
- **Tool calls are invisible to content filters.** A content filter wraps the model call. A tool call bypasses it entirely — the model doesn't output "delete the users table" as text; it outputs a structured `TOOL_CALL` that a content filter never sees.
- **Execution is trust boundary crossing.** A model that reasons well can still output a tool call that escalates privileges, hits a wrong resource, or fires in a context it shouldn't. Reasoning quality and action safety are separate axes.

## The move

**Architecture: three-layer agent stack, not two.**

```
[Layer 1: Generation]     Model outputs text / tool calls
         ↓
[Layer 2: Pre-Execution]   Policy gate intercepts, evaluates, decides
         ↓
[Layer 3: Execution]        Tool call fires (if Layer 2 approves)
```

Layer 2 is the missing piece. It receives the fully-resolved tool call — name, arguments, target resource, credential scope — before any side effect commits.

**Policy gate pattern (AEGIS-style):**

```python
async def policy_gate(tool_call: ToolCall, ctx: AgentContext) -> PolicyResult:
    # 1. Risk classification
    risk = risk_classifier.classify(
        tool=tool_call.name,
        args=tool_call.args,
        resource=tool_call.target_resource,
        credential_scope=ctx.credential_scope,
    )

    # 2. Deny if risk exceeds threshold
    if risk.level == RiskLevel.HIGH:
        return PolicyResult(
            decision="deny",
            reason=f"{risk.level.name} risk: {risk.finding}",
            replacement_args=None,
        )

    # 3. Rewrite args for medium-risk
    if risk.level == RiskLevel.MEDIUM and risk.rewritable:
        rewritten = arg_rewriter.rewrite(tool_call.args, risk.constraint)
        return PolicyResult(decision="rewrite", replacement_args=rewritten)

    # 4. Allow low-risk
    return PolicyResult(decision="allow")

# Integration: wrap every tool call
original_call = model.output_tool_call()
result = await policy_gate(original_call, ctx)
if result.decision == "deny":
    return model.replan_from(result.reason)  # denial becomes context
elif result.decision == "rewrite":
    original_call.args = result.replacement_args
    await execute(original_call)
else:
    await execute(original_call)
```

**Key enforcement dimensions:**

| Dimension | What it checks |
|-----------|---------------|
| **Resource scope** | Does the target resource match the credential scope? |
| **Action type** | DELETE/WRITE vs READ on high-stakes resources |
| **Argument blast radius** | `WHERE id IN (1,2,3)` vs `WHERE 1=1` |
| **Credential identity** | Is this MCP server identity authorized for this resource? |
| **Temporal context** | Is the agent in a frozen/deployment window? |
| **Rate envelope** | Has this tool been called N times in the last T seconds? |

**Hook-based implementation for MCP:**

```python
# MCP server-side pre-execution hook
async def mcp_tool_hook(tool_name: str, args: dict) -> HookResult:
    policy = await load_policy_for_tool(tool_name)
    assessment = policy.evaluate(args=args, caller=ctx.identity)

    return HookResult(
        action=assessment.action,  # allow | deny | ask_approver | redact
        audit_tag=assessment.trace_id,
        redact_fields=assessment.redacted_keys,  # redact PII before logging
    )
```

**The deny-becomes-context loop.** When the gate denies a call, the denial reason is injected back into the model's context as an observation. The model replans around the constraint. This is structurally different from a prompt saying "don't do X" — here, the model received a concrete, system-enforced denial and must respond to it, not reason around it.

**Why not just prompt-based guardrails?** A system prompt "don't delete production tables" is advisory. A policy gate denies the `DELETE` tool call on `production_*` resources — no model reasoning can override it. The distinction is enforcement vs. instruction.

## Receipt

> Receipt pending — 2026-07-20. Policy gate architecture verified against AEGIS (arxiv:2603.09748), Microsoft AGT policy enforcement docs, and slavadubrov.github.io agent security guide (2026-07-14). Pattern matches production deployments documented in Microsoft Agent Governance Toolkit (Apr 2026) and netJoints MCP security guide (Dec 2025). Concrete Python implementation derived from AEGIS policy gate pseudocode and MCP hook specification.

## See also

- [S-375 · Agentic Prompt Injection: Defense-in-Depth](stacks/s375-agentic-prompt-injection-defense-in-depth-for-production.md) — prompt-layer defense; this entry is the execution-layer complement
- [S-100 · Agent Tool Architecture](stacks/s1396-the-agent-tool-architecture-stack-choosing-what-to-give-your-agent-to-do-real-work.md) — tool selection; this entry is tool enforcement
- [S-1005 · AI SRE: Behavioral SLOs and Incident Taxonomy](stacks/s1005-ai-sre-behavioral-slos-and-incident-taxonomy-for-agent-production.md) — post-execution observability; this entry is pre-execution prevention
- [S-1397 · The Container Perimeter Stack](stacks/s1397-the-container-perimeter-stack.md) — isolation boundary; policy gate operates inside the container, enforcing credential and resource constraints
