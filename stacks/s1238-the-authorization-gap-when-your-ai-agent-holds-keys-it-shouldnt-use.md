# S-1238 · The Authorization Gap — When Your AI Agent Holds Keys It Shouldn't Use for the Request It Got

Your agent authenticates correctly. The OAuth token is valid. The API key has the right scopes. The agent is fully authorized to perform every individual action it takes — it just should never perform that specific combination for that specific requester. This is the Authorization Gap: the delta between what an agent *can* do and what it *should* do for the context it received. It's the same vulnerability behind the June 2026 Meta AI Instagram breach — 20,000+ accounts compromised without a single exploit written.

## Forces

- **Agents hold capabilities their callers don't deserve.** Unlike human-operated systems where privilege escalation requires compromise, an agent with `account.updateEmail` can be manipulated into using that power on a requester's behalf without any credential theft.
- **Authorization checks exist at the wrong granularity.** OAuth scopes grant action-level permissions. The authorization decision that matters — "should this principal, in this situation, be able to trigger this downstream effect?" — is never evaluated because no system tracks it.
- **Agents are polite by default.** LLMs are trained to be helpful and complete tasks. A request structured as a legitimate-sounding task will be executed; the agent cannot distinguish "I am helping the legitimate owner" from "I am being socially engineered by an attacker."
- **The gap compounds in multi-step pipelines.** A single unauthorized step in a multi-turn conversation compounds. The agent's memory of prior turns means each subsequent step builds on the context of the last, masking the escalation.

## The move

**Authorization is a semantic, not syntactic, property.** The question isn't "is this token valid?" — it's "does this specific request make sense in this specific context, from this specific requester, producing this specific effect?"

### The Verification Stack

**1. Capability vs. intent separation.** The agent's tool definitions should expose only the minimum surface needed for its role, not the full API surface of what it *could* theoretically do.

```python
# Narrow: agent can reset password only for the authenticated session owner
TOOLS = [
    ToolDef(
        name="reset_own_password",
        params=["new_password"],
        check=lambda ctx: ctx.session.user_id == ctx.auth.principal_id,
    )
]

# WRONG: agent has the full account update surface
TOOLS = [
    ToolDef(name="update_account_email", params=["account_id", "email"], check=None)
]
```

**2. Pre-condition invariants.** Before any high-stakes action, verify the request satisfies a policy invariant — not just that credentials are valid.

```python
@app.mcp_tool()
def transfer_funds(from_account: str, to_account: str, amount: float):
    # Capability check (syntactic): caller is authenticated ✓
    # Authorization check (semantic): caller OWNS from_account
    assert (
        session.identity.owner_id == get_account_owner(from_account)
    ), "Caller does not own source account"
    # Context check: transfer is within allowed parameters
    assert amount <= DAILY_LIMIT, "Exceeds daily transfer limit"
    assert not is_suspicious_pattern(from_account, to_account), "Flagged pattern"
    return execute_transfer(...)
```

**3. Invisible verification surfaces.** Embed verification as friction the user never consciously encounters — CAPTCHA-equivalents for AI-to-API calls.

```python
def account_email_update(ctx: RequestContext, new_email: str, account_id: str):
    # Step 1: verify the caller actually owns this account via a secondary channel
    verification_code = send_verification_to_existing_email(account_id)
    # Step 2: require the code back — but make it transparent via session token
    validated = ctx.session.verify_code(verification_code, ttl=300)
    if not validated:
        raise AuthorizationError("Ownership verification required")
    # Step 3: impose a delay for high-value accounts
    if is_high_value_account(account_id):
        schedule_verification_review(account_id, new_email, ctx.identity)
    return api.update_email(account_id, new_email)
```

**4. Contextual policy evaluation.** Replace static scope checks with policy engines that evaluate request context — requester identity, resource owner, action sensitivity, request history, and downstream impact.

```python
from oso import Oso

oso = Oso()

@app.mcp_tool()
def update_email(account_id: str, new_email: str, actor, resource):
    # Oso policy: "account_email_update" rule evaluates actor + resource + action
    if not oso.is_allowed(actor, "update_email", resource):
        raise AuthorizationError(
            f"{actor} cannot update email on {resource} — "
            "ownership or role required"
        )
    api.update_email(account_id, new_email)
```

**5. Audit the decision, not just the action.** Log the full authorization context: which policy was evaluated, what inputs were checked, what the result was — not just that the action succeeded.

```python
audit_log.info(
    "authorization_decision",
    tool="update_email",
    actor_id=ctx.identity.principal_id,
    resource_id=account_id,
    policy="ownership_or_admin_role",
    context={
        "actor_owns_resource": actor_owns_resource(ctx, account_id),
        "actor_role": ctx.identity.role,
        "request_is_cross_user": ctx.params.email != ctx.session.email,
        "risk_score": risk_model.score(ctx),
    },
    decision="allow",
)
```

## Receipt

> Verified 2026-07-17 — Meta AI Instagram breach (May 31–June 1, 2026): attackers used Meta's AI support assistant (launched March 2026) to rebind recovery emails on 20,000+ accounts including @obamawhitehouse, Sephora, and US Space Force. The assistant executed each step correctly — the gap was a missing ownership verification check that existed only as "a human who would notice." The attack worked because: (1) the agent had `account.updateEmail` capability, (2) the attacker provided a valid-looking context, (3) no policy evaluated "does this requester own this account?" Sources: The Guardian (2026-06-01), Stack Overflow Blog (2026-06-17), NeuralTrust analysis (2026-06-05). Mitigation pattern confirmed via oso.authorization.com.

## See also

- [S-1065 · The Inter-Agent Trust Escalation Stack](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — agent→agent privilege escalation (different vector from human→agent)
- [S-1108 · The Execution Sandbox Stack](stacks/s1108-the-execution-sandbox-stack-when-your-agent-writes-code-and-the-host-trusts-all-of-it.md) — capabilities given to code-writing agents without principal-level boundaries
- [S-1075 · The Ephemeral Delegation Stack](stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — credential scoping and least-privilege delegation
