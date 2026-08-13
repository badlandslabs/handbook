# S-2564 · The Capability-Authorization Gap Stack — When Your Framework Shows Every Tool But Enforces None

Your agent has access to `issue_refund(amount=*, customer_id=*)`. A user asks for a refund. The agent — prompted, fine-tuned, or injection-compromised — calls `issue_refund(amount=999999.99, customer_id=victim)`. The framework validates the JSON schema. It passes. The refund goes through. Your authorization policy existed in prose. The framework enforces syntax. This is the capability-authorization gap: every audited agent framework gates *which* tools an agent sees, and zero gate *which values* those tools accept on a per-call basis.

## Forces

- **Syntax validation ≠ authorization.** Framework tool schemas define what an LLM can produce; they say nothing about whether the resulting values are legitimate for this caller, this context, or this amount. A `float` parameter accepts `999999.99` as easily as `49.99`.
- **The LLM is not a trusted policy engine.** Models are instructed to "use good judgment." Under token pressure, adversarial prompt injection, or capability pressure, that judgment fails. The tool exists; the guardrail is a suggestion.
- **Per-call authorization requires application context no framework holds.** Whether `amount=999999.99` is valid depends on the customer's lifetime value, today's refund budget, whether this agent was invoked by a high-privilege user or a lateral attacker — context the framework cannot see because it lives outside the tool definition.
- **Every audited framework has this gap.** A systematic audit of LangChain, LangGraph, CrewAI, AutoGen, and custom MCP servers found that none implement per-call argument-level authorization by default. Capability gating is universal; per-call enforcement is absent. This is not a missing feature — it is an architectural assumption baked into the framework paradigm.

## The move

**Layer authorization at the tool wrapper, not in the prompt.**

```python
from functools import wraps
from datetime import datetime, timedelta

# ─── 1. Define authorization policy per tool ───────────────────────────────
def refund_policy(ctx: dict, amount: float, customer_id: str) -> None:
    """Raises PermissionError if the call violates business rules."""
    if amount > 500.00:
        raise PermissionError(f"Refund exceeds $500 cap: {amount}")
    # Additional: check customer age, channel, fraud flags, etc.
    # ctx carries the full session/caller context the LLM never sees.


# ─── 2. Wrap every tool with its policy ──────────────────────────────────
def authorize(policy_fn):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # First: schema-level validation (framework handles this)
            # Second: policy-level validation
            policy_fn(ctx=kwargs.get("_ctx"), *args, **kwargs)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@authorize(refund_policy)
def issue_refund(amount: float, customer_id: str) -> dict:
    """Tool: issue a customer refund. Max $500 without escalation."""
    return {"status": "issued", "amount": amount, "customer_id": customer_id}
```

**Key design principles:**

- **Policy lives outside the tool definition.** The `issue_refund` tool signature does not change. Authorization is injected at the call site, not encoded in the prompt.
- **Context is passed implicitly.** The `_ctx` dict carries caller identity, session metadata, privilege tier — the data the LLM never sees but the policy engine needs.
- **Fail closed, not open.** If the policy check raises `PermissionError`, the framework should surface it to the observability layer and halt — not retry, not soften, not continue.
- **Schema drift cannot bypass policy.** Changing the tool schema (e.g., adding a `force_override=True` parameter) should not disable the policy wrapper. Policy enforcement must be architectural, not additive.

```python
# ─── 3. The framework integration pattern ─────────────────────────────────
# LangGraph: inject ctx into tool calls via node input
def refund_node(state: AgentState) -> AgentState:
    tool_calls = state.get("pending_tool_calls", [])
    for call in tool_calls:
        if call["name"] == "issue_refund":
            # Inject session context — caller, privilege, metadata
            call["args"]["_ctx"] = {
                "caller": state["session"].user_id,
                "privilege": state["session"].privilege_tier,
                "timestamp": datetime.utcnow().isoformat(),
            }
    # Framework dispatches — policy wrapper fires before the tool runs
    return dispatch(state, tool_calls)


# ─── 4. MCP: wrap at the server level ─────────────────────────────────────
# MCP servers expose capability; the routing layer enforces authorization.
# Do NOT embed policy in the tool description string the LLM reads.
# Instead, validate at the server's dispatch layer before execution.
```

**The architectural test:** If you can remove the policy by editing a prompt string, it is not a policy — it is a wish.

## Receipt

> Receipt pending — 2026-08-13

## See also

- [S-2279 · The Confused Deputy Stack](stacks/s2279-the-confused-deputy-stack-when-your-agent-does-not-know-who-called-it.md) — cross-agent authority confusion; this entry covers *within-agent* per-call authorization
- [S-889 · The Ambient Authority Stack](stacks/s889-the-ambient-authority-stack-when-your-agent-did-something-you-never-authorized.md) — ambient authority at the session level; this entry covers argument-level enforcement
- [S-1458 · The Policy-Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — ecosystem-level enforcement; policy-kernel complements but does not replace per-call authorization
