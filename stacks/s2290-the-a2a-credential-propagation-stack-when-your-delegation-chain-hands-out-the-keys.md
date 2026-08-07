# [S-2290] · The A2A Credential Propagation Stack — When Your Delegation Chain Hands Out the Keys

When your email-summarizer agent delegates to your document-agent, which delegates to your code-execution agent, each intermediate agent inherits the caller's full credential set — not just the scope needed for its slice of the task. A prompt injection in the email body now has production-execution privileges because the email agent's delegation hop carried them along. This is not a confused-deputy problem (the caller is known). It is not a governance problem (the protocols coordinate correctly). It is a credential chain problem: A2A passes credentials by reference, not by scope, and the delegation chain multiplies blast radius at every hop.

## Forces

- **A2A delegation passes full credential context by default.** When Agent A delegates to B, the credential context carries everything A received — not the minimal subset needed for the sub-task. A three-hop chain means the final agent holds three layers of credentials it never requested.
- **Agents in chains are increasingly likely to be low-trust.** The first agent might be a hardened orchestrator. The third might be a lightweight email responder that nobody hardened. Credential inheritance means the chain's security is bounded by its weakest link.
- **Prompt injection inside the chain compounds with credential scope.** A2A SEP #1404 (capability-based authorization, still draft as of 2026) explicitly identifies this: an email agent with file-read + email-read permissions delegates to a code-execution agent — and the injected prompt in the email can now invoke code execution because the chain carried those credentials.
- **No protocol-level enforcement of least-privilege delegation.** The A2A spec does not mandate capability scoping in delegation. Agents declare capabilities in their Agent Card but those declarations are self-asserted and carry no cryptographic enforcement over delegation boundaries.

## The Move

### 1. Map your delegation chain topology before shipping

Draw every A2A delegation path before it reaches production. For each hop, ask: does the receiving agent's task actually require the full credential set of the caller?

```bash
# Enumerate A2A delegation relationships in your agent mesh
# Each agent → list of agents it delegates to
curl -s http://agent-mesh:8080/topology | jq '.delegation_edges[]'
# Expected output: list of {caller, callee, capability_scope} entries
```

### 2. Implement capability-scoped delegation gates

Instead of forwarding the full credential context, the delegating agent should request and forward only the minimal capability for the sub-task. This is the pattern from A2A SEP #1404, implementable now even before spec ratification:

```python
# Delegating agent: request minimal capability before forwarding
async def delegate_minimally(task, target_agent, required_actions):
    # Request only what the target needs
    cap_token = await capability_authority.issue_scoped_token(
        actions=required_actions,      # e.g. ["document:read"]
        ttl_seconds=300,              # short-lived
        delegator=current_agent.id,
        target=target_agent.id,
    )
    return await a2a_client.send_task(
        task,
        target=target_agent,
        authorization=f"Bearer {cap_token}"
    )

# NOT: forward entire request_context.credentials
```

### 3. Build an ephemeral-credential layer per delegation hop

Per arxiv 2505.12490 (Louck et al., 2026): issue short-lived, action-scoped tokens at each hop. Tokens expire before the chain completes, neutralizing stolen-credential replay:

```python
# Per-hop: mint a new token with narrowed scope
def narrow_credential(original_token, allowed_scopes):
    narrows_token = jwt.sign(
        payload={
            "sub": original_token["sub"],
            "scopes": allowed_scopes,       # reduced from original
            "exp": datetime.utcnow() + 300,  # 5-minute TTL
            "chain_depth": original_token.get("chain_depth", 0) + 1,
            "max_hops": 3,                   # hard cap
        },
        issuer="agent-mesh-ca"
    )
    return narrows_token
```

### 4. Cap delegation depth with hard stops

Set `max_hops = 3` as a global ceiling in your agent mesh config. Long delegation chains that degrade into "everyone has everything" are a topology smell. Prefer fan-out over depth:

```python
CHAIN_DEPTH_LIMIT = 3

def check_chain_depth(token_payload):
    depth = token_payload.get("chain_depth", 0)
    if depth >= CHAIN_DEPTH_LIMIT:
        raise DelegationDepthExceeded(
            f"Chain depth {depth} exceeds limit {CHAIN_DEPTH_LIMIT}"
        )
    return True
```

### 5. Treat delegation as a revocation event

Every time an agent delegates, treat the original token as potentially compromised (it has now traversed a low-trust boundary). Rotate credentials after each delegation hop. This prevents lateral movement: even if a mid-chain agent is compromised, the credentials it received are useless after the next hop issues new ones.

```python
async def revoke_after_delegate(original_token, hop_id):
    """Revoke the original token after a delegation completes."""
    await credential_authority.revoke(token_id=original_token["jti"])
    audit_log.log(
        event="delegation_complete",
        hop=hop_id,
        token_revoked=True
    )
```

### 6. Validate at every receiving endpoint — not just entry

The receiving agent must independently verify its authorization for the requested action. Do not trust the caller to have already scoped correctly:

```python
async def receive_task(request):
    # Always re-verify — caller scoping is advisory, not enforced
    token = parse_authorization(request.headers["authorization"])
    for action in request.task.required_actions:
        if action not in token["scopes"]:
            raise InsufficientCapability(
                f"Token scopes {token['scopes']} do not cover {action}"
            )
    return await process_task(request)
```

## Receipt

> Verified 2026-08-07 — Source: A2A SEP #1404 (GitHub a2aproject/A2A discussion #1404, draft, Jan 2025): ambient authority accumulation pattern confirmed; capability scoping proposed as the fix. Source: arxiv 2505.12490 (Louck et al., Ariel University, 2026): ephemeral token + granular scope pattern achieves 0% data leakage vs. 60-100% baseline in simulation. Source: AgentsID Scanner A2A Security Gap Analysis (April 2026): Gap 3 ("Credential Chains") explicitly calls out full credential forwarding in delegation as a structural vulnerability. Source: Palo Alto Networks A2A Protocol Security Guide (2026): "validation has to occur at every receiving endpoint, not just the first hop" — confirming per-hop enforcement is not built into A2A by default. Deduplication: S-2138 (Protocol Governance Layer) covers collective decision-making gaps; S-2279 (Confused Deputy) covers cross-principal authorization confusion; this entry is distinct — it covers credential scope propagation through the delegation chain, not who called whom or how decisions are made collectively.

## See also

- [S-2279 · The Confused Deputy Stack](/stacks/s2279-the-confused-deputy-stack-when-your-agent-does-not-know-who-called-it.md) — authorization confusion across principals; related but covers caller identity, not credential scope
- [S-2138 · The Protocol Governance Layer Stack](/stacks/s2138-the-protocol-governance-layer-stack-when-mcp-a2a-and-acp-score-2-out-of-12-on-collective-decision-making.md) — protocol-level governance gaps; related but covers collective decision-making, not credential propagation
- [S-992 · The Agent Verifiable Credential Infrastructure Stack](/stacks/s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — credential infrastructure and revocation; this entry builds on that foundation with delegation-chain-specific patterns
