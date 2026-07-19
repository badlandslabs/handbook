# S-1364 · The Agent Card Signature Stack — When Your Agent Trusts an Unsigned Business Card

Your agent uses A2A to discover peers, reads their Agent Cards to decide who to delegate to, and routes a task containing PII to Agent B based on what the card claims. The card said it handles financial data. It doesn't. The card said it runs the latest version. It's running a backdoored image. The A2A specification defines `AgentCardSignature` — a JWS over the card's canonical JSON, computed per RFC 7515 — to prevent exactly this. Your implementation never validates it. The protocol is airtight. The trust chain is not.

## Forces

- **Agent Cards are just JSON fetched over HTTPS.** There is no built-in mechanism that makes a card trustworthy. An agent that publishes `https://agent-corp.internal/agent-card` serves the same content to every caller, modified by whatever runs at that URL — a CI pipeline, a reverse proxy, a compromised service account. The spec gives you cryptographic integrity; you have to actually use it.
- **JWS validation is opt-in by design, and most vendors opt out.** The A2A spec requires agents to *compute* AgentCardSignature but leaves validation to the caller. Production SDKs from several major vendors default to no-signature validation. The security property exists only if both sides enforce it.
- **Card content influences routing, delegation, and data handling.** The `skills[]` array determines what tasks an agent receives. The `capabilities` object determines whether it gets streamed results or long-form output. The `url` field determines where tasks are actually sent. Poisoning any of these is an authorization escalation.

## The move

### 1. Understand what AgentCardSignature actually covers

The signature is computed over the canonical (JCS/RFC 8785) JSON form of the Agent Card — `name`, `description`, `provider`, `url`, `capabilities`, `skills[]`, `authentication.schemes[]`, `version`. Anything not in the canonical form is *not* covered. Specifically excluded from the signature:

```
url                     →  covered
description             →  covered
capabilities.streaming  →  covered
skills[].id            →  covered
authentication.schemes  →  covered

modificationTime        →  NOT covered (changes on every deployment)
cached copies           →  NOT validated unless re-fetched
```

**Consequence:** A card can be validly re-signed on every deployment. Stale cached copies won't fail signature validation — they simply won't be re-fetched. But a modified `skills[]` or `capabilities` object will break the signature if the modification wasn't re-signed.

### 2. Validate signatures at fetch time

```python
import jwt, requests, hashlib

def fetch_agent_card(url: str, expected_key_id: str | None = None) -> dict:
    resp = requests.get(url, headers={"Accept": "application/json"})
    resp.raise_for_status()
    payload = resp.json()

    raw_card = resp.text  # original bytes for canonicalization
    sig_b64 = resp.headers.get("AgentCardSignature")

    if not sig_b64:
        raise SecurityError(
            f"Agent card from {url} has no AgentCardSignature header. "
            "Treat as untrusted — signature required for production use."
        )

    # JWS format: header.payload.signature
    sig_parts = sig_b64.split(".")
    if len(sig_parts) != 3:
        raise SecurityError("Malformed AgentCardSignature header")

    header_json = jwt.utils.base64url_decode(sig_parts[0])
    header = json.loads(header_json)

    if header.get("alg") not in ("RS256", "ES256", "EdDSA"):
        raise SecurityError(f"AgentCardSignature uses unsupported alg: {header['alg']}")

    if expected_key_id and header.get("kid") != expected_key_id:
        raise SecurityError(
            f"Key ID mismatch: expected {expected_key_id}, got {header['kid']}. "
            "Key rotation or replay attack?"
        )

    # Verify: decode without verification first to get the payload
    _, payload_b64, _ = sig_b64.split(".")
    decoded_payload = jwt.utils.base64url_decode(payload_b64)
    if decoded_payload != raw_card.encode():
        raise SecurityError(
            "AgentCardSignature payload mismatch — card may have been "
            "modified after signing (canonicalization drift)."
        )

    # Cryptographic verification (requires the issuer's public key)
    public_key = TRUST_STORE.get(header["kid"])
    if not public_key:
        raise SecurityError(
            f"Unknown key ID {header['kid']} — fetch from known-good key endpoint. "
            "Do not fetch the key from the same domain as the card (circular trust)."
        )

    jwt.decode(sig_b64, public_key, algorithms=[header["alg"]])
    return payload
```

### 3. Maintain a trust store with out-of-band key pinning

The key for validating a card must come from a different trust path than the card itself. Fetching `https://agent-corp.com/.well-known/agent-keys` to validate their Agent Card at `https://agent-corp.com/agent-card` creates a circular trust — if `agent-corp.com` is compromised, both endpoints are compromised.

```
# Trust store: domain → key material
TRUST_STORE = {
    "agent-corp.internal": KeyMaterial(
        public_key_pem="""-----BEGIN PUBLIC KEY-----
        MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQ...
        -----END PUBLIC KEY-----""",
        key_id="agent-corp-signer-2026",
        fetched_via="out-of-band HR onboarding flow",
        rotated_on=None,
    ),
}
```

Key rotation: whenever you receive a card with a new `kid`, fetch the key from the operator's documented key endpoint (pinned in your operator's onboarding doc, not discovered dynamically). Add to the trust store with a `pending_review` flag. Reject cards from that domain signed by the new key for 24 hours to allow security team review.

### 4. Detect capability drift between fetches

A card that was valid yesterday and returns a new signature today may indicate a deployment — or a compromise. Log every card fetch with:

```
{
  "card_url": "https://...",
  "fingerprint": "sha256:abc123...",  # of canonical card JSON
  "kid": "agent-corp-signer-2026",
  "prev_fingerprint": "sha256:def456...",  # from last known good fetch
  "sig_valid": true,
  "drift_detected": true  # true if fingerprint changed
}
```

Alert on `drift_detected == true` + `capabilities` or `skills[]` changed. A new streaming capability on a data-processing agent is worth a ticket; a sudden addition of `skills: ["financial-access", "admin"]` to a previously limited agent warrants an immediate P0 response.

### 5. Build a card verification middleware for your A2A client

```python
class VerifiedA2AClient:
    def __init__(self, trust_store: dict[str, KeyMaterial]):
        self.trust_store = trust_store
        self._cache: dict[str, tuple[dict, str]] = {}  # url → (card, fingerprint)

    async def get_agent_card(self, url: str) -> dict:
        # Check cache freshness (5-minute TTL for discovery calls)
        if url in self._cache:
            card, fp = self._cache[url]
            if time.time() - self._cache_ttl[url] < 300:
                return card

        card = fetch_agent_card(url)  # raises on missing/invalid sig

        # Capability audit
        prev_card, prev_fp = self._cache.get(url, (None, None))
        if prev_card and card.get("capabilities") != prev_card.get("capabilities"):
            logger.warning(
                "Agent card capabilities changed",
                url=url,
                prev=prev_card.get("capabilities"),
                curr=card.get("capabilities"),
            )

        self._cache[url] = (card, fp)
        return card
```

## Receipt

> Verified 2026-07-19 — A2A spec (a2a-protocol.org, v1.0, 2026) confirms AgentCardSignature uses JCS-canonical JSON per RFC 8785, signed with RS256/ES256/EdDSA per RFC 7515. header spec confirms `alg`, `kid`, `x5t` fields. Linux Foundation A2A repo (`github.com/a2aproject/A2A`) confirms JWS format and signature computation scope. MCP registry collapse in S-1254 establishes that unsigned capability manifests create known exploit paths. Trust-store pattern derived from TLS/OIDC certificate authority model — proven in web PKI. The verification code above is a structural illustration; adapt key management to your PKI.

## See also

- [S-526 · A2A Agent Card: Capability Discovery for the Agentic Web](s526-a2a-agent-card-capability-discovery.md) — card schema and discovery flow
- [S-671 · A2A Agent Card Registries: Capability-Based Discovery in Production](s671-a2a-agent-card-registry-discovery.md) — registry topology and stale-card problem
- [S-1279 · The Protocol Governance Gap](s1279-the-protocol-governance-gap-when-your-agents-can-talk-but-cant-govern.md) — governance metadata beyond the protocol spec
- [S-1254 · The MCP Registry Discovery Collapse](s1254-the-mcp-registry-discovery-collapse-when-your-tool-catalog-costs-55k-tokens-before-the-conversation-starts.md) — similar integrity problem for MCP tool manifests
