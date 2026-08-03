# S-2031 · The Inter-Agent Message Provenance Stack — When Your Agent Acts on Instructions That Carry No Proof of Origin

Your orchestrator agent sends a task instruction to a worker agent: `delete this record`. The worker checks the orchestrator's identity — it's registered — and executes. But who sent that instruction? It could be the legitimate orchestrator. It could be an attacker who intercepted a prior message and is replaying it. It could be a compromised agent whose memory was poisoned and is now issuing instructions its creator never intended. The worker has no way to tell, because inter-agent messages carry no cryptographic proof of origin or integrity.

This is the **inter-agent message provenance problem** — and it's the gap that makes S-1065 (trust escalation) structural rather than theoretical. You can define the right trust policy, but if every agent accepts any message from a registered peer, the policy is only as strong as the weakest registration.

## Forces

- **Messages cross trust boundaries.** An agent receiving a task from another agent has no out-of-band way to verify the message wasn't intercepted, replayed, or forged. The network channel is not the same as the trust channel.
- **Agent identity ≠ message authenticity.** Registration proves the sender has an identity in the system. It says nothing about whether *this specific message* originated from that identity or was constructed by an attacker with access to the network path.
- **Replay is a first-class attack.** A captured `approve_payment` message can be replayed 50 times. The agent checks: is the sender registered? Yes. Are the contents valid? Yes. Was this the only authorized `approve_payment`? No way to know.
- **MACaroons and JWTs solve different problems.** JWTs prove identity at the *token* level but not at the *message* level — a JWT on a poisoned instruction is still a poisoned instruction. MACaroons attenuate authority but require the receiving agent to verify the chain of caveats.

## The move

Layer cryptographic provenance over every inter-agent message boundary. The pattern has three components:

### 1. Message signing (origin + integrity)

Every outbound message carries an HMAC-SHA256 signature from the sender's secret key, covering the canonical message body + a monotonically increasing nonce:

```python
import hmac
import hashlib
import json
import time
import secrets

class SignedMessage:
    def __init__(self, sender_key: bytes, seq: int):
        self.sender_key = sender_key
        self.seq = seq
        self.nonce = secrets.token_hex(8)
        self.timestamp = int(time.time())
        self._body = None
        self._signature = None

    def build(self, body: dict) -> "SignedMessage":
        self._body = {
            "seq": self.seq,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "body": body,
        }
        canonical = json.dumps(self._body, sort_keys=True, separators=(',', ':'))
        self._signature = hmac.new(
            self.sender_key,
            canonical.encode(),
            hashlib.sha256
        ).hexdigest()
        return self

    def toEnvelope(self) -> dict:
        return {
            "message": self._body,
            "signature": self._signature,
        }


# Sender side
sender_key = secrets.token_bytes(32)  # shared or derived via ECDH
msg = SignedMessage(sender_key, seq=42).build({
    "action": "delete_record",
    "record_id": "R-789",
})
envelope = msg.toEnvelope()

# Receiver side
def verify_and_receive(envelope: dict, expected_key: bytes, window: int = 300) -> dict:
    """Verify signature, nonce freshness, and timestamp before processing."""
    msg_body = envelope["message"]
    sig = envelope["signature"]

    # 1. Integrity check
    canonical = json.dumps(msg_body, sort_keys=True, separators=(',', ':'))
    expected_sig = hmac.new(expected_key, canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Signature mismatch — message tampered or forged")

    # 2. Timestamp freshness (replay window)
    if abs(time.time() - msg_body["timestamp"]) > window:
        raise ValueError(f"Message outside {window}s replay window")

    # 3. Nonce deduplication (store seen nonces in Redis; reject duplicates)
    nonce = msg_body["nonce"]
    if redis_client.exists(f"nonce:{nonce}"):
        raise ValueError("Replay detected — nonce already used")
    redis_client.setex(f"nonce:{nonce}", window * 2, "1")

    return msg_body["body"]
```

### 2. Delegation chains with MACaroon attenuation

When Agent A delegates to Agent B with restricted scope — `you may read this record but not delete it` — encode the restriction as a MACaroon caveat rather than a plain assertion. A MACaroon carries its own cryptographic proof: Agent B cannot strip caveats to expand its authority.

```python
import base64
import hmac
import hashlib
import json

class MacaroonCaveat:
    def __init__(self, predicate: str, vid: bytes):
        self.predicate = predicate
        self.vid = vid  # verification-id — known only to issuer

    def serialize(self) -> str:
        return json.dumps({"pred": self.predicate, "vid": base64.b64encode(self.vid).decode()})

    @staticmethod
    def first_party(caveats: list, secret: bytes, plain: str) -> str:
        """Derive discharge token for a caveat, bound to the original secret."""
        return hmac.new(secret, plain.encode(), hashlib.sha256).hexdigest()


class Macaroon:
    """Simplified MACaroon: issuer secret → token + caveats."""
    def __init__(self, secret: bytes, location: str, key_id: str):
        self.secret = secret
        self.location = location
        self.key_id = key_id
        self.caveats: list[MacaroonCaveat] = []

    def add_first_party_caveat(self, predicate: str) -> "Macaroon":
        vid = secrets.token_bytes(16)
        self.caveats.append(MacaroonCaveat(predicate, vid))
        return self

    def discharge(self, secret: bytes) -> dict:
        """Generate discharge macaroons for third-party caveats."""
        discharge = Macaroon(secret, self.location, self.key_id + "-discharge")
        discharge.caveats = self.caveats
        return {
            "caveats": [
                {
                    "pred": c.predicate,
                    "vid": base64.b64encode(c.vid).decode(),
                    " Discharge": MacaroonCaveat.first_party(self.caveats, self.secret, c.predicate)
                }
                for c in self.caveats
            ],
            "sig": self._sig(),
        }

    def _sig(self) -> str:
        base = hmac.new(self.secret, f"{self.location}:{self.key_id}".encode(), hashlib.sha256).hexdigest()
        for c in self.caveats:
            base = hmac.new(base, c.serialize().encode(), hashlib.sha256).hexdigest()
        return base

    def to_string(self) -> str:
        return base64.b64encode(json.dumps({
            "location": self.location,
            "key_id": self.key_id,
            "caveats": [c.serialize() for c in self.caveats],
            "sig": self._sig(),
        }).encode()).decode()


# Issuer (orchestrator) creates a scoped token
orchestrator_secret = secrets.token_bytes(32)
token = Macaroon(orchestrator_secret, "orchestrator", "task-42")
token.add_first_party_caveat("action=read")
token.add_first_party_caveat("record_id=R-789")
token.add_first_party_caveat("expires=2026-08-02T23:59:59Z")

# Worker receives token + discharge and verifies all caveats before executing
def verify_macaroon(token: dict, discharges: list[dict], verifier_fn) -> bool:
    """Verify every caveat against the verifier function; fail if any caveat fails."""
    all_caveats = token["caveats"] + [d for dis in discharges for d in dis.get("caveats", [])]
    for caveat in all_caveats:
        if not verifier_fn(caveat["pred"], base64.b64decode(caveat["vid"])):
            return False
    return True
```

### 3. Provenance chain in the audit trail

Every agent's audit log records not just what it did, but what message triggered it and what signature verified that message. This enables post-incident reconstruction:

```
audit_entry = {
    "event": "delete_record",
    "record_id": "R-789",
    "triggered_by": "orchestrator-v2",
    "message_seq": 42,
    "signature": "a3f8...",
    "verified_key_id": "orchestrator:task-42",
    "nonce_used": "7b2c...",
    "caveats_checked": ["action=read", "record_id=R-789"],  # ← failed here
    "outcome": "DENIED",
}
```

## Receipt

> Receipt pending — 2026-08-02

The HMAC signing pattern and MACaroon structure above are implementable with Python stdlib. The HashiCorp Vault tutorial (developer.hashividual.com, June 2026) demonstrates a production version using Vault as the OIDC issuer for A2A agents — the same pattern applies to MCP message signing. The GitHub PoC for ASI07 (repson/ai-security-poc) provides a working vulnerable→mitigated comparison for the HMAC approach. No live execution of the full stack in this entry.

## See also

- [S-1065 · The Inter-Agent Trust Escalation Stack](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — the policy-level complement; this entry covers the cryptographic mechanism
- [S-1274 · The Ephemeral Credential Vending Stack](stacks/s1274-the-ephemeral-credential-vending-stack-when-your-agent-shares-a-credential-with-another-agent-and-nobody-owns-the-key.md) — MACaroons are the credential format; this entry is the delivery mechanism
- [S-1164 · Agent Hash-Chained Audit Trail](stacks/s1164-agent-hash-chained-audit-trail-the-immutable-ledger-pattern.md) — message signatures feed directly into the immutable audit log
