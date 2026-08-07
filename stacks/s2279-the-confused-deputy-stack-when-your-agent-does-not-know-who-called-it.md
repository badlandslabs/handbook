# S-2279 · The Confused Deputy Stack — When Your Agent Does Not Know Who Called It

Your high-privilege orchestration agent has access to production data, user records, and billing systems. A low-privilege scraper agent — or an adversarial external caller — routes a request through the orchestrator, which dutifully executes it with full production authority. No credentials were stolen. No policy was violated. The orchestrator simply could not distinguish an authorized internal call from an unauthorized lateral request passing through the same interface. This is the confused deputy problem, reimplemented for agentic systems. It is the primary authorization failure mode in multi-agent meshes.

## Forces

- **Agents inherit privileges they do not originate.** When Agent A calls Agent B, Agent B executes with its own elevated permissions — not the caller's. An orchestrator with production read access will happily serve a request from a scraper agent with none. No credential is compromised; the trust boundary is simply absent.
- **Authorization decisions grow exponentially with agent count.** Two agents create three authorization decisions (who each is, what the other can do). Five agents in sequence create a chain of ten. Traditional IAM was designed for users and services, not for autonomous agents that decompose tasks, delegate subtasks, and call other agents mid-execution.
- **The caller is invisible to the executing agent.** Most agent frameworks pass results, not caller context. The executing agent has no way to verify whether the request originated from a privileged orchestrator or an adversarial lateral flow. Cryptographic identity of the calling agent is not transmitted across the delegation boundary.

## The move

**1. Tag every inter-agent call with a signed caller-claims token.**
Before Agent A calls Agent B, A signs a compact JWT (or SPICE/MintPki attestation) containing: caller agent ID, authorization tier, task scope, and expiry. B validates the token before executing — not just the result, the caller chain. This is analogous to a service mesh's mTLS + RBAC, applied at the agent layer.

```
python
import jwt, time

def create_agent_token(
    caller_id: str,
    tier: str,           # "orchestrator" | "worker" | "scraper"
    scope: list[str],    # ["read:production", "write:billing"]
    secret: str,
    ttl: int = 300,
) -> str:
    payload = {
        "sub": caller_id,
        "tier": tier,
        "scope": scope,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
        "jti": f"{caller_id}-{int(time.time())}",   # nonce for replay prevention
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def validate_agent_token(token: str, secret: str, max_tier: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise PermissionError("Token expired")
    except jwt.InvalidTokenError:
        raise PermissionError("Invalid token")
    
    tier_order = {"scraper": 0, "worker": 1, "orchestrator": 2}
    if tier_order.get(payload["tier"], -1) > tier_order.get(max_tier, -1):
        raise PermissionError(f"Tier {payload['tier']} exceeds max_tier {max_tier}")
    return payload
```

**2. Apply permission intersection at the delegation boundary.**
When Agent A (orchestrator, tier=orchestrator, scope=[read:*, write:billing]) delegates to Agent B (worker, tier=worker, scope=[read:reporting]), B's effective scope is the *intersection*: `[read:reporting]`. B can never inherit more privilege than it already holds. This is the "least delegation" principle — the orchestrator's elevated scope does not propagate downward.

```python
def intersect_scopes(caller_scope: list[str], agent_scope: list[str]) -> list[str]:
    """Return only operations both caller and agent are authorized for."""
    return list(set(caller_scope) & set(agent_scope))
```

**3. Log every cross-agent call to a tamper-evident audit trail.**
Every delegation event — caller, callee, scope granted, task outcome — is written to a Sigstore-signed or append-only log. On incident review, you can reconstruct the full delegation chain: who called whom, with what claimed authority, and what happened. This is the only way to investigate a confused-deputy incident after the fact.

**4. Enforce egress filtering at the agent boundary.**
Agents should not be able to spontaneously contact external endpoints unless those endpoints are in an explicit allowlist. This prevents a compromised low-tier agent from using the orchestrator as a relay to exfiltrate data to an external address. This is network-level confused-deputy prevention.

## Receipt

> Verified 2026-08-07 — CSA Zero-Trust AI Governance (Gentyala, Jun 2026) describes mutual cryptographic authentication at the agent-to-agent interface as the primary mitigation for spoofing and privilege escalation in multi-agent meshes. Security Boulevard (Gupta, Mar 2026) provides the exponential authorization complexity table (1 agent = 1 decision; 5 agents = 10 decisions; n agents = n×(n+1)/2 decisions) and recommends JWT-based caller-claims tokens with tier validation. Red Hat Emerging Technologies (May 2026) formalizes the "permission intersection" pattern as the alternative to OAuth2-style impersonation (which grants the agent the user's full identity). OWASP ASI Top 10 (Jun 2026) lists "Cross-Agent Authorization Failures" as a top-tier vulnerability class.

## See also

[S-1458](S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) · [S-2278](s2278-the-supervisor-stack-when-one-agent-is-not-enough-but-ten-is-chaos.md) · [S-200](f200-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md)
