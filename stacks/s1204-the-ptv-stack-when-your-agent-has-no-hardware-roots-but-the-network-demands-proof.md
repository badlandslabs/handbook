# S-1204 · The PTV Stack — When Your Agent Has No Hardware Roots but the Network Demands Proof

Your agent needs to authorize a high-value payment, access a compliance-gated API, or hand off work to a partner's agent across a trust boundary. The system asks: "Prove you are authorized to do this." Your agent has an API key — a static string that proves nothing about the agent's runtime state, version, or policy compliance. An attacker who steals that key gets the same authorization. This is the gap PTV (Prove-Transform-Verify) fills: replacing identity-by-token with **identity-by-cryptographic-proof**, anchored in hardware roots of trust.

## Forces

- **OAuth and SPIFFE tokens carry no runtime guarantees.** A JWT bearer token proves only that someone had a valid credential at issuance time. It reveals nothing about whether the presenting agent is running approved code, is within its policy scope, or has not been tampered with since. Stolen tokens work until revoked — and revocation is reactive.
- **Agents multiply the credential attack surface.** A single human principal spawns one agent, which spawns N sub-agents, each calling N tools with N credentials. Static credentials have no concept of delegation depth. One compromised sub-agent can silently escalate to the full set of its parent's scoped permissions.
- **Cross-boundary transactions require identity continuity.** When your agent delegates to a partner's agent via A2A, neither the human operator nor the receiving system has a way to verify the calling agent's runtime posture — its hardware attestation, its policy version, its behavioral telemetry — without exposing raw credentials.
- **ZKPs enable privacy-preserving proof without data exposure.** A proving agent should be able to demonstrate "I am a v2.1 agent registered with AcmeCorp, running on a TPM 2.0–provisioned host, and my current policy allows read access to this dataset" — without transmitting the raw key, the policy text, or the host identifier. Zero-knowledge proofs make this possible.

## The move

PTV is a three-phase protocol (IETF draft, RATS working group, expires October 2026) that replaces token-based authorization with cryptographic proof:

```
Agent ──────[1] PROVE───────> Attestation Service
             (TPM 2.0 / Secure Enclave quote,
              signed attestation document)

Agent ◄──────[2] TRANSFORM────── Attestation Service
             (Groth16 zero-knowledge circuit,
              strips identity, keeps policy claims)

Verifier ◄───[3] VERIFY───────── Attestation Service
             (ZK proof + policy engine check,
              returns allow/deny in <240ms p99)
```

**Key components:**

- **Hardware root of trust.** TPM 2.0 or ARM TrustZone / Intel SGX provides an unforgeable identity anchor. The agent's signing key is generated inside the secure enclave and never exported. Attestation quotes bind the key to PCR (Platform Configuration Registers) values — boot measurements, firmware hashes, runtime config hashes.
- **Policy-attested claims.** Instead of "here is my API key," the agent proves: "my TPM holds key K, PCR values match policy P, and I am running software version V approved by my principal." This is the *prove* phase.
- **ZK proof transformation.** The attestation service runs a Groth16 circuit (or PLONK/Moore) that takes the raw attestation and outputs a zero-knowledge proof. The proof certifies the claims without revealing: the TPM endorsement key, the host's unique identifier, the exact PCR values, or the principal's identity. Sub-200ms generation is achievable on commodity hardware with pre-compiled circuits.
- **Verification gate.** The verifier (payment processor, API gateway, receiving agent) checks the ZK proof against the known policy without seeing the underlying attestation. Result: allow or deny. No raw credentials cross the trust boundary.

**When to use it:**

- Payment authorization (Mastercard Agent Pay, Visa Verified Agent, AP2 Verifiable Credentials)
- Cross-organizational A2A handoffs where both parties require attestation
- Compliance-gated APIs (financial data, healthcare records, government systems)
- Multi-agent delegation chains where each hop needs to verify the previous agent's policy compliance

**Implementation variants:**

```python
# PROVE: generate TPM attestation quote (simplified)
import tpm2

def prove_identity(agent_id: str, policy_hash: bytes) -> AttestationQuote:
    """
    Phase 1: Agent generates a hardware-rooted attestation quote.
    Quote binds: TPM key → PCR values → policy_hash → nonce (fresh per request).
    """
    with tpm2.TPM2Connection("/dev/tpm0") as ctx:
        # Load agent's attestation identity key (AIK) from TPM
        aik_handle = tpm2.load_ak(
            ctx,
            ak_context=agent_ak_context,
            ak_public=agent_ak_public,
        )
        # Generate quote: signs {PCR_values || policy_hash || nonce}
        quote = tpm2.quote(
            ctx,
            aik_handle,
            data=policy_hash + nonce,  # nonce prevents replay
            hash_algorithm=tpm2.TPM2_ALG_SHA256,
        )
        return AttestationQuote(
            signature=quote.signature,
            pcr_values=quote.pcrs,
            policy_hash=policy_hash,
            nonce=nonce,
            aik_pub=agent_ak_public,
        )
```

```python
# TRANSFORM: attestation → ZK proof (using snarkjs)
from snarkjs import groth16

def transform_to_zkp(quote: AttestationQuote, circuit: Circuit) -> ZKProof:
    """
    Phase 2: Attestation service converts quote to a zero-knowledge proof.
    The circuit verifies:
      1. Quote.signature is valid for quote.aik_pub
      2. quote.policy_hash matches the policy the verifier trusts
      3. quote.nonce is fresh (prevents replay within the session)
    Output: proof attests to (2) and (3) WITHOUT revealing:
      - The TPM endorsement key
      - The host's unique identifier
      - The exact PCR measurement values
    """
    input_signals = [
        int.from_bytes(quote.signature, "big"),
        int.from_bytes(quote.policy_hash, "big"),
        int.from_bytes(quote.nonce, "big"),
    ]
    
    # {A, B, C} = Groth16 proof elements
    proof = groth16.fullProve(input_signals, circuit.wasm, circuit.final_zkey)
    
    return ZKProof(
        pi_a=proof["pi_a"],
        pi_b=proof["pi_b"],
        pi_c=proof["pi_c"],
        public_signals=[quote.policy_hash],  # only policy_hash is public
    )
```

```python
# VERIFY: ZK proof + policy check (sub-240ms p99 target)
def verify_agent_identity(
    proof: ZKProof,
    trusted_policy_hash: bytes,
    policy_engine: PolicyEngine,
) -> VerificationResult:
    """
    Phase 3: Verifier checks the ZK proof against:
      1. Trusted policy_hash (matches what the proof's public signal contains)
      2. Policy engine rules (is this policy allowed for this action?)
      3. Optional: revocation list (has the agent been suspended?)
    """
    # ZK verification: proof proves knowledge of valid attestation
    # without revealing the attestation itself
    is_valid = groth16.verifKey(
        verification_key=trusted_vk,
        public_signals=[trusted_policy_hash],
        proof=proof,
    )
    
    if not is_valid:
        return VerificationResult(allow=False, reason="Invalid ZK proof")
    
    # Policy check: is this policy_hash approved for this action?
    policy_ok = policy_engine.check(
        policy_hash=trusted_policy_hash,
        action=current_action,
        resource=requested_resource,
    )
    
    if not policy_ok:
        return VerificationResult(allow=False, reason="Policy not satisfied")
    
    return VerificationResult(allow=True, reason="Attested and authorized")
```

## Tradeoffs

- **Hardware dependency.** PTV requires TPM 2.0 or equivalent secure enclave. Cloud workloads on hardware without SGX/TrustZone need alternate attestation paths (AMD SEV-SNP, Nitro Enclaves, or simulated TPM for dev/test). Hardware requirements limit adoption in pure-software environments.
- **ZK circuit complexity.** Writing and auditing ZK circuits is specialist work. Pre-compiled circuit libraries (snarkjs, Halo2) reduce the burden, but circuit changes (new policy fields, new attestation claims) require regeneration of proving keys and trusted setups.
- **Latency budget.** ZK proof generation adds 50–200ms to the first request per session. Use proof caching: once a proof is generated and the agent's state hasn't changed, reuse it for subsequent requests within the same policy window.
- **PTV ≠ magic.** It proves identity and policy compliance — not that the agent's logic is correct. A hardware-attested agent with a buggy policy still produces wrong outputs. Combine with behavioral telemetry and output verification gates.

## Context

**Deduplication:** Related to [S-420 Agent Identity Governance](./s420-agent-identity-governance-the-ai-principal-paradigm.md) (I-033) which covers the governance/framework layer for agent identity. PTV is the cryptographic primitive S-420's policy engine reads from. Related to [S-972 Agent Trust Negotiation](./s972-agent-trust-negotiation-cross-boundary-credential-and-capability-presentation.md) (I-133) which covers the A2A-level capability manifest and ATN framework — PTV provides the hardware-attested credential underlying the ATN session receipt. Related to [S-1075 Ephemeral Delegation](./s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) which covers credential scoping for delegated agents — PTV prevents the "stranger" problem by making the receiving party prove identity before receiving any scoped credential.

**Sources:** IETF draft-anandakrishnan-ptv-attested-agent-identity-00 (A. Damodaran, Sovereign AI Stack, RATS working group, March 2026); eco.com agent identity verification guide (June 2026); Mastercard Agent Pay technical spec; signets.ai AI agent payment verification (2026); Zylos Research agentic identity survey (Q2 2026).
