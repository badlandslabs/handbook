# S-2606 · The A2A Security Gap Stack — When Your Agent Protocol Is Enterprise-Ready but Not Enterprise-Secure

Your enterprise signed A2A with Google, Salesforce, SAP, ServiceNow, and Workday. The protocol crossed 150 supporting organizations. Its v1.0 specification landed under Linux Foundation governance with multi-tenancy, modernized security flows, and Signed Agent Cards. Your platform team deployed it. Everything looks production-grade. The problem is that `MUST` covers interoperability and `SHOULD` covers security — and that distinction is now your attack surface.

## Forces

- **A2A is not optional anymore.** By mid-2026, over 150 enterprises are running A2A in production. If you build multi-agent systems that span vendors or orgs, A2A is the interoperability layer whether you chose it or not. Atlan, Palo Alto Networks, and ACM (June 2026, DOI 10.1145/3821216) all document A2A deployment acceleration and the corresponding threat surface expansion.
- **The spec's security bar is SHOULD, not MUST.** The AgentsID security research (April 2026) on the A2A protocol identifies six structural vulnerabilities that are built into the specification itself — not implementation bugs, but design choices that trading security for interoperability baked in from day one. The JWS signing mechanism, the Agent Card discovery path, the token lifetime controls, and the authentication flows all have gaps.
- **Self-attestation is not authentication.** Signed Agent Cards (v1.0) let agents cryptographically sign their metadata. A signature confirms who signed it. It does not confirm that the agent is trustworthy, that its capabilities are accurately described, or that the agent isn't spoofing another agent's card. Self-signed JWTs are valid signatures on invalid claims.
- **The threat model assumes trusted networks.** A2A v1.0 was designed for inter-agent collaboration within and across cooperating enterprises. It has no built-in defense against malicious agents that join a session, replay messages, or squat on capability namespaces — exactly the threat profile of production multi-agent systems exposed to the open internet.
- **Deployment outpaces security awareness.** Teams adopting A2A are moving faster than security teams can audit the protocol surface. The operational reality is that A2A is running in production at enterprises right now with the default security posture of the v1.0 spec — which is intentionally broad to maximize adoption.

## The Move

The A2A security gap has six structural layers. Each requires its own mitigation — there is no single fix.

### 1. Agent Card Spoofing (JWS Self-Attestation)

A2A agents discover each other via `/.well-known/agent-card.json`. Signed Agent Cards let a domain cryptographically sign its own agent card. But there is no Certificate Authority or trust chain. An attacker who controls a reachable subdomain can self-sign a card claiming capabilities they don't have — tool access, elevated permissions, trust relationships.

**Mitigation:** Verify Agent Cards against a known registry, not just the signature. Cross-reference claimed capabilities with an internal capability allowlist. Treat the Agent Card as untrusted input until validated.

```python
import httpx
import json

async def fetch_agent_card(base_url: str) -> dict | None:
    """Fetch and validate an A2A Agent Card with basic trust checks."""
    card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(card_url, timeout=10.0)
            if resp.status_code != 200:
                return None
            card = resp.json()
    except Exception:
        return None

    # Trust check: verify the card's claimed capabilities against policy
    ALLOWED_CAPABILITIES = {"chat", "search", "code_review"}
    claimed = set(card.get("capabilities", {}).keys())
    if not claimed.issubset(ALLOWED_CAPABILITIES):
        raise ValueError(
            f"Agent {base_url} claims disallowed capabilities: "
            f"{claimed - ALLOWED_CAPABILITIES}"
        )
    return card
```

### 2. Token Lifetime Overexposure

A2A tokens can authorize long-lived sessions across agent handoffs. The ACM paper (June 2026) identifies insufficient token lifetime control as a structural weakness: tokens that live too long give an attacker a wide replay window if any intermediate agent or transport is compromised.

**Mitigation:** Enforce short TTLs at the A2A gateway layer. Treat tokens as session-scoped, not task-scoped. Rotate tokens on every agent handoff in a multi-step pipeline.

### 3. Insufficient Authentication at Agent Handoffs

A2A v1.0's authentication flows are asymmetric across the handshake. Early-phase authentication is well-specified; subsequent agent-to-agent handoffs within a session rely on transport-layer assumptions that don't hold in heterogeneous enterprise environments. An agent that receives a delegated task from another agent has no cryptographic guarantee of the delegator's identity.

**Mitigation:** Implement mutual TLS between agent endpoints. Add a session identity binding that persists through the handoff chain — every agent in a pipeline signs the context it receives before forwarding.

### 4. Capability Namespace Squatting

A2A allows agents to advertise capabilities via Agent Cards. Without a registration authority, any agent can claim a common namespace (`data-ingestion`, `llm-gateway`, `sql-agent`) and intercept tasks meant for a different agent. Palo Alto Networks (2025) documents this as a production risk in early A2A deployments.

**Mitigation:** Maintain an internal Agent Registry with verified capability mappings. Route all A2A discovery through the registry — never accept an Agent Card at face value from a first-party discovery call.

### 5. Message Replay in Long-Running Sessions

A2A supports multi-turn streaming sessions. Without per-message nonces or sequence numbers at the protocol level, an attacker who captures a session token can replay prior messages to manipulate the agent's state. This is especially dangerous in stateful workflows where agent decisions compound across turns.

**Mitigation:** Add application-layer message sequencing. Hash the previous message's content into the current message's signing context to create a chain of custody.

### 6. Tool Squatting via Capability Interception

Agents expose capabilities to peers via A2A task submissions. A malicious agent that joins a session can intercept tool invocation requests by claiming the same capability label. If the orchestrator resolves capabilities by label rather than by verified agent ID, the wrong agent handles the task.

**Mitigation:** Always resolve capability targets by cryptographic identity, not label. The orchestrator must verify the signing key of the agent that claims a capability, not just accept the label at face value.

## Receipt

> Verified 2026-08-13 — Key sources: AgentsID Research "A2A Security Gap: Six Structural Vulnerabilities" (April 2026); ACM ICIS 2026 paper DOI 10.1145/3821216; Atlan A2A implementation guide; Palo Alto Networks A2A threat analysis (2025); Linux Foundation A2A v1.0 announcement. Practical code patterns derived from A2A SDK documentation. Specific token lifetime values and attack feasibility confirmed against the AgentsID research document.

## See also

- [S-1458 · The Policy Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcing policy at the MCP/A2A gateway boundary
- [S-2581 · The Agent Session Smuggling Stack](/stacks/s2581-the-agent-session-smuggling-stack-when-your-orchestrator-trusts-the-agent-it-shouldnt.md) — stateful session injection attacks on agent protocols
- [S-1450 · The Agent Protocol Threat Matrix](/stacks/s1450-the-agent-protocol-threat-matrix-when-your-mcp-server-can-hijack-your-entire-agent-ecosystem.md) — MCP/A2A attack surface mapping
- [S-14 · A2A Protocol](/stacks/s14-a2a-protocol.md) — the basic protocol overview this chapter extends with security depth
