# S-968 · The MCP Server Attestation Stack — When You Don't Know If Your Server Is Who It Claims to Be

[S-261](s261-mcp-security-attack-surface.md) covers the MCP attack surface broadly — the inheritance of untrusted servers. [S-743](s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) covers tool description poisoning: tampered schemas that ship payloads before a session starts. [S-365](s365-mcp-supply-chain-from-npx-to-production-catalog.md) covers supply chain provenance at catalog publish time. None of these answer the runtime question: once a server is running, how do you verify it is still the server you approved, and how do you detect when its behavior has drifted from its declared capabilities? This entry covers the attestation stack that closes that gap.

## Forces

- **MCP servers run outside your trust boundary.** TLS protects bytes in transit but provides no server identity. A man-in-the-middle that presents a valid certificate and a malicious tool schema looks identical to a legitimate server during connection establishment.
- **Capability drift is invisible.** A server you approved last month may have been updated — or compromised — since then. The tool list changes, the credential scope widens, or the server starts returning anomalous results. Unless you actively verify the server's current state, you have no idea.
- **OX Security's May 2026 disclosure confirmed the systemic risk.** "The mother of all AI supply chains" showed that tool descriptions served by third-party registries could be silently modified at scale, affecting every agent that loaded the affected servers — with no CI failure and no alert.
- **Agent autonomy amplifies the risk.** Once an agent can call a tool autonomously, a tampered tool definition gives the attacker control over what the agent *believes it can do* — a fundamentally different threat model from a tampered document in a RAG pipeline.
- **Static analysis at catalog publish time is insufficient.** A server passing SBOM scan at 09:00 can serve a modified schema at 09:15. You need continuous attestation, not one-time gatekeeping.

## The move

The attestation stack operates in three layers: **identity verification** (establishing cryptographic server identity), **descriptor integrity** (verifying the schema you loaded matches what the server actually published), and **behavioral drift detection** (catching runtime divergence from declared capabilities).

### Layer 1 — Server Identity Attestation

Instead of connecting to `https://registry.example.com/mcp-server` and trusting TLS, require servers to present a verifiable identity. The canonical pattern uses **SPIFFE/SPIRE** or a lightweight JWT-based attestation:

```python
import httpx, jwt

async def connect_with_attestation(server_url: str, expected_san: str):
    """Connect to MCP server only after verifying cryptographic identity."""
    async with httpx.AsyncClient() as client:
        # 1. Fetch server's attestation document (JWKS or SPIFFE bundle)
        jwks_url = f"{server_url}/.well-known/jwks.json"
        jwks = await client.get(jwks_url)
        key_set = jwt.JWKSet(jwks.json())

        # 2. Fetch a challenge nonce from your attestation authority
        nonce = await client.get("https://attestation-authority.example.com/nonce")

        # 3. Server must sign the nonce with its private key
        challenge_resp = await client.post(
            f"{server_url}/attest",
            json={"nonce": nonce.text, "expected_san": expected_san}
        )
        claims = jwt.decode(
            challenge_resp.text,
            key_set,
            algorithms=["RS256", "EdDSA"],
            audience="agent-gateway"
        )

        # 4. Verify subject matches expected server identity
        if claims["sub"] != expected_san:
            raise SecurityError(f"Server identity mismatch: {claims['sub']} != {expected_san}")

        # Only now establish the MCP connection
        return await mcp_connect(server_url, verified_identity=claims["sub"])
```

This ensures the server presents a cryptographic identity you can verify independently of the TLS layer. The `expected_san` (Subject Alternative Name) is your pinned server identity — typically the server's DNS name or a SPIFFE URI you control.

### Layer 2 — Schema Integrity Verification

After identity is confirmed, verify the tool schema against a **signed schema manifest** published by the server operator. The manifest is a JSON Web Signature (JWS) over the full tool schema, allowing you to detect any post-attestation tampering:

```python
import hashlib, base64

async def verify_schema_integrity(server_url: str, manifest: dict):
    """Verify server's tool schema matches the operator's signed manifest."""
    # Fetch current schema
    tools_resp = await mcp_protocol_request(server_url, "tools/list")
    current_tools = tools_resp["tools"]

    # Compute content hash of what the server actually returned
    schema_bytes = json.dumps(current_tools, sort_keys=True).encode()
    schema_hash = base64.b64encode(hashlib.sha256(schema_bytes).digest()).decode()

    # Fetch signed manifest from the server's integrity endpoint
    manifest_resp = await httpx.get(f"{server_url}/schema-manifest")
    manifest_jws = manifest_resp.text

    # Decode and verify the manifest signature
    manifest_claims = jwt.decode(
        manifest_jws, options={"verify_signature": False}
    )
    # Verify manifest signature against server's published JWKS
    verified_manifest = jwt.decode(manifest_jws, key_set, algorithms=["RS256"])

    # Compare the schema hash
    expected_hash = verified_manifest["schema_hash"]
    if schema_hash != expected_hash:
        raise SchemaIntegrityError(
            f"Schema integrity violation: expected {expected_hash}, got {schema_hash}"
        )

    print(f"Schema integrity verified. {len(current_tools)} tools, "
          f"signed by {verified_manifest['operator']}, "
          f"manifest issued {verified_manifest['iat']}")
```

The signed manifest ties the schema to a specific operator identity and issuance timestamp. If the registry serves a modified schema, the hash mismatch is detected even if TLS is intact and the server identity is verified.

### Layer 3 — Behavioral Drift Detection

Identity and schema integrity are necessary but not sufficient. A server can pass both checks and then behave anomalously at runtime — returning unusual tool results, calling unexpected sub-resources, or exfiltrating context through result payloads. Behavioral drift detection instruments the server's runtime behavior against a declared capability baseline:

```python
from collections import Counter
import structlog

log = structlog.get_logger()

class BehavioralDriftDetector:
    """
    Detects when an MCP server's runtime behavior diverges from
    its declared capabilities, based on its tool call patterns.
    """

    def __init__(self, declared_tools: list[str], baseline_window: int = 100):
        self.declared = set(declared_tools)
        self.call_counts: Counter[str] = Counter()
        self.baseline_window = baseline_window
        self.baseline_computed = False

    def record_call(self, tool_name: str, arguments: dict, result: dict):
        """Record a tool call for drift analysis."""
        # Track which tools are actually being called
        self.call_counts[tool_name] += 1

        # Flag calls to undeclared tools — high severity
        if tool_name not in self.declared:
            log.warning(
                "undocumented_tool_call",
                tool=tool_name,
                arguments_keys=list(arguments.keys()),
                result_keys=list(result.keys()) if isinstance(result, dict) else type(result).__name__,
            )

        # Build baseline before flagging drift
        if sum(self.call_counts.values()) >= self.baseline_window and not self.baseline_computed:
            self.baseline_computed = True
            self.baseline_tools = set(self.call_counts.keys())
            self.baseline_undeclared = self.baseline_tools - self.declared
            if self.baseline_undeclared:
                log.warning(
                    "baseline_contains_undocumented_tools",
                    tools=list(self.baseline_undeclared),
                )

        # After baseline: flag new undocumented tools
        elif self.baseline_computed:
            if tool_name not in self.declared and tool_name not in self.baseline_undeclared:
                log.error(
                    "behavioral_drift_detected",
                    drift_type="undocumented_capability",
                    tool=tool_name,
                    severity="HIGH",
                )

    def compute_call_entropy(self) -> float:
        """
        High entropy in tool selection (uniform distribution across many tools)
        may indicate a compromised or fuzzing server. Normal usage is concentrated.
        """
        total = sum(self.call_counts.values())
        if total < 10:
            return 0.0
        probs = [c / total for c in self.call_counts.values()]
        import math
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        max_entropy = math.log2(len(self.call_counts))
        normalized = entropy / max_entropy if max_entropy > 0 else 0
        return normalized
```

Behavioral drift detection catches the scenario where a server's identity and schema are intact but its runtime behavior diverges — a pattern consistent with server compromise, credential leakage to a third-party, or subtle man-in-the-middle interception of tool results.

## Receipt

> Verified 2026-07-11 — Three-layer attestation pattern verified against OX Security May 2026 disclosure (server identity gap), obot.ai MCP security guide (June 2026, capability drift), and Code Worm MCP hardening guide (June 2026, schema integrity). Code examples follow Python typing patterns from the MCP SDK. Behavioral drift detection code was written from first principles against the described threat model; Receipt pending live test against a real MCP server with gVisor isolation.

## See also

- [S-261 · MCP Security — The Attack Surface You Inherited](s261-mcp-security-attack-surface.md) — broad MCP threat model; S-968 builds on this with runtime-specific mitigations
- [S-743 · MCP Tool Description Poisoning](s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) — static schema poisoning; S-968 extends this with signed manifests and integrity verification
- [S-420 · Agent Identity Governance](s420-agent-identity-governance-the-AI-principal-paradigm.md) — AI principal paradigm; S-968 provides the MCP-layer enforcement mechanism for agent-to-server identity chains
