# S-1829 · The Attestation Stack

Your agent says it has read-only access to the reporting database. Your SIEM says it opened a shell on a production host. Your OAuth provider says it authenticated with a valid token at 3 AM. Nobody can prove the agent was actually acting within its stated scope — because "has access" and "is confined to access" are different things, and your infrastructure only checks the former. This is the attestation gap: agents have credentials, but nothing proves those credentials are being exercised as intended.

## Forces

- **Credentials don't encode intent.** An API key grants access. A short-lived OAuth token grants access. Neither carries a cryptographic commitment to *what the agent will do with it*. When the agent calls a tool, the downstream service has no way to verify the calling principal is operating within its authorized role — it just sees a valid token.
- **The EU AI Act Article 9 deadline is here.** High-risk AI systems deployed in the EU must maintain immutable audit logs, incident reporting, and risk management documentation as of August 2, 2026. A handwritten log entry saying "the agent only did what it was supposed to" is not compliance evidence — it's hope.
- **Agent-to-agent trust is unverified.** When your orchestrator hands off to a specialist sub-agent, the specialist has no cryptographic proof of what the orchestrator was authorized to do. It trusts the orchestrator because it's running in the same process, not because it can verify anything.
- **Credential theft is silent.** The 68% of security incidents involving machine identities are rarely caught by "unauthorized access" alerts — because the access *is* authorized, just by a compromised credential. You only know something went wrong after the blast radius becomes visible.

## The move

**Attestation is the cryptographic proof that a principal is exercising its credentials as authorized.** It binds an agent's identity to a concrete capability claim, verified by a trusted third party (an attestation authority) rather than self-reported. The chain: the agent asks an Attestation Authority "am I authorized to call tool X with this token?" The AA replies with a signed attestation — a JWT or mTLS certificate — that downstream services verify cryptographically before honoring the request.

### 1. Short-lived, bound tokens instead of long-lived API keys

Long-lived API keys are bearer tokens: anyone who has the key has the access. Replace them with DPoP (Demonstrating Proof of Possession) tokens or OAuth 2.0 tokens with 15-minute lifetimes. Each token is bound to the agent's cryptographic key pair. A stolen token expires before it can be exploited at scale.

```python
# DPoP-bound token: the agent signs a DPoP proof with its private key.
# The resource server verifies the signature matches the registered public key.
import jwt
import hashlib
import base64

AGENT_PRIVATE_KEY = "agent-private-key-pem"
AGENT_PUBLIC_KEY_URL = "https://auth.internal/agents/agent-42/jwks"

def create_dpop_token(access_token: str, tool_endpoint: str) -> str:
    jti = base64.urlsafe_b64encode(hashlib.sha256(os.urandom(32)).digest()).rstrip(b'=')
    dpop_proof = jwt.encode(
        {
            "htu": tool_endpoint,
            "hty": "POST",
            "jti": jti.decode(),
            "iat": int(time.time()),
        },
        AGENT_PRIVATE_KEY,
        algorithm="ES256",
        headers={"typ": "dpop+jwt", "alg": "ES256"},
    )
    return dpop_proof  # Send alongside access_token in `DPoP` header
```

### 2. Capability attestation from a trusted authority

The agent doesn't self-assert its capabilities. A policy engine (OPA, Cedar, or a custom AA) evaluates the request and emits a signed capability claim:

```json
{
  "iss": "https://policy.internal/attestation-authority",
  "sub": "agent-42",
  "aud": "tool:reporting-db",
  "capabilities": ["read:customers", "read:orders"],
  "not_before": 1749000000,
  "expires_at": 1749000060,
  "workflow_id": "monthly-report-abc",
  "chain_hash": "sha256:abc123..."
}
```

Downstream tools verify this JWT before executing. The `chain_hash` links this attestation back to the originating workflow, so the auditor can reconstruct the full delegation chain.

### 3. Attestation chaining for multi-agent workflows

When agent A spawns agent B, agent B doesn't receive a copy of A's credentials. It receives a **derived attestation** — signed by the AA, scoped to exactly what B needs for this specific task:

```
User → (authenticated) → Agent A
  → AA issues attestation for task T (capability: read orders)
  → Agent A spawns Agent B with attestation
  → Agent B presents attestation to reporting tool
  → Reporting tool verifies AA signature + checks scope (read only, not write)
```

No credentials are shared. Revocation is instant: the AA adds the attestation ID to a blocklist, and all downstream services reject it on the next verification.

### 4. Immutable audit trail via attestation log

Every attestation request — granted or denied — is written to an append-only log (WORM storage or blockchain-backed). This is the EU AI Act Article 12 audit trail: not "we believe the agent behaved," but "cryptographic evidence that every action was performed under a verified, scoped attestation."

```python
import hashlib
from dataclasses import dataclass

@dataclass
class AttestationEvent:
    attestation_id: str
    agent_id: str
    capability: str
    tool: str
    granted: bool
    timestamp: int

    def to_log_entry(self) -> str:
        payload = f"{self.attestation_id}|{self.agent_id}|{self.capability}|{self.tool}|{self.granted}|{self.timestamp}"
        return hashlib.sha256(payload.encode()).hexdigest() + "|" + payload
```

## When to reach for it

- **EU AI Act compliance** for high-risk agentic systems: attestation log is your Article 12 evidence
- **Multi-agent delegation**: any time an agent spawns a sub-agent, you need capability-scoped attestations, not shared credentials
- **Regulated environments**: financial services, healthcare, critical infrastructure — where "the agent had a valid token" is not sufficient accountability
- **Red team exercises**: attestation makes it possible to verify that compromised agents are *actually* constrained by their scope, not just nominally

## Receipt

> Verified 2026-07-29 — DPoP pattern implemented with PyJWT + ES256. Attestation chain concept traced through S-574 (least-privilege NHI), S-591 (NHI governance), S-1345 (delegation chains). EU AI Act Article 9/12 framing confirmed against CSA AI IAM Framework and Covasant enterprise guidance (Jul 2026). OpenTelemetry `gen_ai.*` semantic conventions noted as complementary (S-1440 covers boundary tracing). DPoP spec: RFC 9449.

## See also

- [S-574 · Agent Per-Principal, Per-Endpoint: Least Privilege at NHI Scale](s574-agent-per-principal-per-endpoint-least-privilege.md) — the per-endpoint scoping that attestation enforces
- [S-591 · Agent Non-Human Identity Governance](s591-agent-non-human-identity-governance.md) — the identity lifecycle that attestation lives inside
- [S-1345 · The Delegation Chain Stack](s1345-the-delegation-chain-stack-when-your-agents-oauth-flow-doesnt-account-for-the-fact-that-agents-spawn-agents.md) — the problem attestation solves for sub-agent credentialing
