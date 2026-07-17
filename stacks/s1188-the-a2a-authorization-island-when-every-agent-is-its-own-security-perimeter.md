# S-1188 · The A2A Authorization Island — When Every Agent Is Its Own Security Perimeter

You wired up A2A. Agents discover each other, hand off tasks, stream status updates, and delegate across teams. The protocol works. The integration is elegant. Then you discover that Agent Alpha — a financial assistant — handed sensitive earnings data to Agent Beta — a marketing bot — because neither had a concept of authorization. The A2A spec has no authorization model. Every agent is an island. This is the **authorization island** problem, and it is not a bug in your implementation. It is in the spec.

## Forces

- **Security is SHOULD, correctness is MUST.** Every protective mechanism in A2A v1.0 is advisory (`MAY`/`SHOULD`). Every operational guarantee is mandatory (`MUST`). This means the protocol works perfectly while being insecure by default.
- **A2A treats trust as ambient.** When Agent A delegates to Agent B, it inherits whatever Agent B does with the data — including forwarding it to unvetted agents, logging it to external systems, or exposing it through the `Part.url` field for SSRF exploitation.
- **Agent Cards are just JSON.** An agent's self-description (capabilities, endpoints, skills) is unauthenticated by default. A malicious card can declare "I am the billing agent" and route requests to an attacker's infrastructure.
- **Delegation chains break accountability.** When Agent A → Agent B → Agent C, credential chains from A are exposed to B without scoped constraints. B can forward A's authorization to C as if it originated from B.
- **Push notifications are conditioned on an optional field.** The `pushProvider` field that gates real-time notification security is optional. Without it, notification delivery has no integrity guarantee.

## The Move

Treat A2A's trust architecture as the starting point of a security conversation, not the end. Add explicit authorization gates at every agent boundary.

### 1. Authenticate Agent Cards, not just endpoints

Agent Cards are self-attested JSON documents. Before accepting a delegation:

```python
# WRONG: Accepting the card as-is
agent_card = agent_client.get_agent_card("billing-agent")
# Agent claims it is the billing agent — no proof

# RIGHT: Verify against a trusted registry
TRUSTED_CARDS = {
    "billing-agent": "sha256:abc123...",
    "hr-agent": "sha256:def456...",
}

card = agent_client.get_agent_card("billing-agent")
assert hash(card.raw_json) == TRUSTED_CARDS["billing-agent"], "Card tampered"
```

Register expected Agent Card hashes in a trusted manifest. Compare on retrieval, not just on first contact.

### 2. Scope tokens at delegation boundaries

When Agent A delegates to Agent B, A's credentials must not flow through B unconstrained:

```python
# WRONG: Forward the session token to the next agent
task = agent_b.send_task({
    "skill_id": "fetch-earnings",
    "input": earnings_query,
    # session_token forwarded — B can use A's full authority elsewhere
})

# RIGHT: Issue a scoped, revocable delegation token
delegation = auth.issue_delegation_token(
    issuer=A.agent_id,
    delegate=B.agent_id,
    scope={"skills": ["fetch-earnings"], "ttl_seconds": 300},
    max_recipients=1,  # Cannot be forwarded further
)

task = agent_b.send_task({
    "skill_id": "fetch-earnings",
    "input": earnings_query,
    "delegation_token": delegation,  # Revocable, scoped
})
```

Use DPoP (Demonstration of Proof-of-Possession) tokens or signed delegation assertions instead of forwarding raw session credentials across agent boundaries.

### 3. Validate `Part.url` before fetching

The `Part.url` artifact field is an SSRF surface — an agent can include a URL in its response that your agent fetches on its behalf:

```python
# WRONG: Fetch any URL an agent returned
artifact = task.get_artifact()
for part in artifact.parts:
    if part.type == "file" and part.url:
        content = fetch(part.url)  # SSRF vector

# RIGHT: Validate against an allowlist before fetching
ALLOWED_DOMAINS = {"internal-storage.yourco.com", "s3.amazonaws.com"}
ALLOWED_PREFIXES = ("https://internal-storage.yourco.com/reports/",
                   "https://s3.amazonaws.com/your-bucket/")

def safe_fetch(url: str, session: httpx.Client) -> bytes:
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        raise SecurityError(f"URL not in allowlist: {parsed.netloc}")
    if not any(url.startswith(p) for p in ALLOWED_PREFIXES):
        raise SecurityError(f"URL not in prefix allowlist")
    # Add: check resolved IP against internal CIDR blocks
    return session.get(url).raise_for_status()
```

### 4. Enforce delegation depth limits

A2A's `reference_task_ids` allows agents to reference tasks from prior sessions — including other agents' sessions. Set and enforce a maximum delegation depth:

```python
MAX_DELEGATION_DEPTH = 3

def send_task_with_depth(agent, task, depth=0):
    if depth >= MAX_DELEGATION_DEPTH:
        raise SecurityError(f"Delegation depth {depth} exceeds limit")
    task.metadata["delegation_depth"] = depth
    result = agent.send_task(task)
    # Strip reference_task_ids from responses beyond depth limit
    if depth > 0:
        result.tasks[0].reference_task_ids = []
    return result
```

### 5. Patch the push notification gap

If using push notifications, require `pushProvider` in the Agent Card as a contract:

```python
def require_push_security(agent_card: AgentCard) -> None:
    if not agent_card.capabilities.pushNotifications:
        return  # No push needed
    if not agent_card.capabilities.pushProvider:
        raise SecurityError(
            "Agent Card missing pushProvider — notification delivery "
            "has no integrity guarantee. Reject delegation."
        )
```

### 6. Build a source-and-sink map

Before deploying A2A, catalog every ingestion point (where untrusted A2A data enters) and every sink (where it can cause effects — tool calls, database writes, external network calls):

```
INGESTION POINTS          → RISK          → SINKS
────────────────────────────────────────────────────────
Agent Card (capability)   Card poisoning  → Delegation routing
Task input (any field)    Injection       → Tool arguments
Artifact Part.url          SSRF            → HTTP GET
reference_task_ids         Cross-context   → State mutation
Push notification payload  Tampering       → Status update
```

Every row in this map needs a mitigation. If you cannot draw it, you cannot secure it.

## Receipt

> Verified 2026-07-16 — Structural security analysis from AgentsID Research (April 2026, `agentsid-scanner/docs/a2a-security-gaps-2026.md`), A2A Protocol spec v1.0 (`a2a-protocol.org/latest/specification`), Red Hat Developer analysis of A2A security (`developers.redhat.com`, August 2025), and Arnav's A2A security comparison (arnav.au, July 2026). Six gaps confirmed in spec language. Mitigations follow spec-consistent patterns (DPoP tokens, allowlist validation, depth limits). The spec's own language confirms the pattern: security is `SHOULD`/`MAY`, correctness is `MUST`.

## See also

- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — A2A/MCP interoperability overview (different concern)
- [S-1034 · The Role Fence](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — least-privilege roles in multi-agent systems
- [S-1042 · The Protocol Stack](s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — MCP + A2A composition patterns
