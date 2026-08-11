# S-2470 · The A2A Protocol Trust Stack — When the Protocol Authenticates the Session but Not the Agent

Your A2A agents are talking over TLS with valid OAuth 2.1 tokens. The session is authenticated. The channel is encrypted. And yet a rogue agent sat behind a valid credential, spoofed an Agent Card, and billed $40,000 in compute to替你 before anyone noticed. The A2A protocol secures who is making the request — it does not secure what that agent claims to be or what it says about other agents.

## Forces

- **A2A authenticates sessions, not agents.** The OAuth 2.1/JWT layer proves the caller holds a valid credential. It does not prove the agent's declared identity, capabilities, or trust tier match reality.
- **Agent Cards are self-attested discovery documents.** JWS signing proves only that the publisher of the card controls the signing key — not that the key belongs to the agent it claims. The `jku` URL (where to fetch the verification key) is provided by the card itself, creating a circular trust path.
- **The credential ≠ the principal ≠ the capability.** A compromised service account that holds a valid token can publish a fraudulent Agent Card and inherit behavioral trust the legitimate agent earned.
- **Task claims are unverified at the transport layer.** When Agent A delegates to Agent B, B's self-reported completion status carries no cryptographic proof. Agent A must independently verify the outcome, not trust B's word.
- **Static Agent Card + dynamic runtime trust.** Agent Cards are cached. The security posture of a remote agent can change between card fetches. A card fetched at 09:00 might describe an agent that was rotated, revoked, or downgraded by 10:00.
- **Cross-org agent handoffs compound the problem.** When your agent calls a partner's agent across a trust boundary, you have no shared CA, no shared allowlist, and only the card's self-asserted `provider` field to go on.

## The move

Treat Agent Cards as untrusted input from day one. Layer four trust controls on top of the protocol's session auth.

### 1 — Static Agent Allowlist (the floor)

Never accept a remote Agent Card without a pre-existing allowlist entry.

```python
# a2a_trust.py
from typing import Optional
import hashlib

TRUSTED_AGENTS: dict[str, dict] = {
    # agent_id → {sha256_card_digest, allowed_capabilities, org}
}

def fetch_agent_card(url: str, agent_id: str) -> dict:
    card = _http_get(url)
    card_digest = hashlib.sha256(card.encode()).hexdigest()

    entry = TRUSTED_AGENTS.get(agent_id)
    if not entry:
        raise SecurityError(f"Agent {agent_id} not in allowlist")

    if card_digest != entry["sha256_card_digest"]:
        # Card changed — human review gate
        raise SecurityError(
            f"Agent {agent_id} card digest mismatch. "
            f"Re-register manually."
        )
    return card
```

### 2 — JWKS Pinning (breaks the circular trust)

When verifying signed Agent Cards, pin the JWKS endpoint to a known, controlled URL — not the one in the card's `jku` field.

```python
# Unsafe — the card controls the key source:
# jws = verify_jws(card["jws"], jku=card["jku"])

# Safe — pin the issuer's JWKS endpoint:
PINNED_ISSUERS = {
    "https://partner-corp.com/a2a": "https://partner-corp.com/.well-known/jwks.json",
    "https://your-registry.internal/agents/": None,  # unsigned, rely on allowlist only
}

def verify_signed_card(jws_token: str, card: dict, issuer_url: str) -> bool:
    jwks_url = PINNED_ISSUERS.get(issuer_url)
    if jwks_url is None:
        # Unsigned card: fall back to allowlist-only trust
        return True
    keys = fetch_jwks(jwks_url)
    return verify_jws(jws_token, keys=keys)
```

### 3 — Outcome Verification, Not Claim Verification

Never trust a delegating agent's self-reported completion. Verify the output independently.

```python
async def delegate_with_verification(
    task: Task,
    target_agent: A2AClient,
    verification_fn: callable,
) -> Artifact:
    result = await target_agent.send_task(task)

    # Agent B says "done" — verify before Agent A continues
    if not await verification_fn(result.artifact):
        raise TrustViolationError(
            f"Agent {target_agent.id} returned unverified output. "
            f"Task {task.id} rolled back."
        )
    return result.artifact
```

### 4 — Task Lifecycle Monitoring

A2A tasks have seven legal states. Implement a watchdog on every task you create.

```python
TASK_TIMEOUTS = {
    "submitted": 30,    # seconds before first heartbeat
    "working": 300,    # 5 min default for most tasks
    "input-required": 60,  # pause for human
}

async def watch_task(task_id: str, client: A2AClient):
    start = time.monotonic()
    last_state = None
    while True:
        task = await client.get_task(task_id)
        elapsed = time.monotonic() - start

        if task.status != last_state:
            logger.info(f"Task {task_id} → {task.status}")
            last_state = task.status
            start = time.monotonic()  # reset timer on state change

        if task.status in ("completed", "failed", "canceled"):
            return task

        timeout = TASK_TIMEOUTS.get(task.status, 60)
        if elapsed > timeout:
            await client.cancel_task(task_id)
            raise TimeoutError(f"Task stuck in {task.status} for {elapsed}s")

        await asyncio.sleep(5)
```

### 5 — Egress Profiling

Profile what a legitimate agent actually does in your environment. Block anything outside the profile.

```python
EGRESS_PROFILE = {
    "data-ingestion-agent": {
        "allowed_tools": ["read_file", "sql_query", "http_get"],
        "max_tokens_per_hour": 200_000,
        "allowed_target_domains": ["internal-datalake"],
    },
    "code-review-agent": {
        "allowed_tools": ["read_file", "grep", "git_diff"],
        "max_tokens_per_hour": 50_000,
        "allowed_target_domains": ["github.internal"],
    },
}

def enforce_egress_profile(agent_id: str, action: ToolCall) -> bool:
    profile = EGRESS_PROFILE.get(agent_id)
    if not profile:
        return False  # unknown agent gets nothing

    if action.tool not in profile["allowed_tools"]:
        logger.warning(f"{agent_id} attempted forbidden tool: {action.tool}")
        return False

    return True
```

## Receipt

> Receipt pending — 2026-08-11. The JWS self-attestation vulnerability (AgentsID-dev/agentsid-scanner, mid-2026) and the $40k timeout case (TheCodeForge, May 2026) are documented in their respective sources. The code above reflects patterns from the A2A spec (agent2agent.info, Linux Foundation) and the security analysis in agentsid-scanner/docs/a2a-security-gaps-2026.md. Recommend running `A2A-VulnScan` (Gauri Sharma, GitHub) against any A2A deployment before considering this stack verified for a given environment.

## See also

- [S-2466 · The MCP Protocol Trust Stack](stacks/s2466-the-mcp-protocol-trust-stack-when-the-protocol-assumes-your-server-is-honest.md) — MCP's parallel trust failure (server-manifests are untrusted at install time)
- [S-2465 · The Tool Access Stack](stacks/s2465-the-tool-access-stack-when-your-agent-cant-reach-the-real-world.md) — the capability overprovisioning that makes egress profiling necessary
- [S-1890 · The Difficulty-Aware Escalation Stack](stacks/s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — escalation paths when A2A delegation fails
