# S-1841 · The Execution Receipt Stack — When Your Agent Claims Success and Proves Nothing

Your agent says: "File uploaded successfully." The file wasn't uploaded — the network call timed out. Your orchestrator logs show a 200 OK from the proxy. The agent logged success. The recipient agent acted on the assumption the upload was real. Three agents downstream built on a lie, and nobody caught it until the compliance team asked why the report was blank.

This is the execution receipt problem: agents claim outcomes they cannot prove, tool calls succeed in the agent's mental model without a verifiable record, and handoff data arrives with no proof of provenance or integrity. The agent can't lie about what it did — but it can be confidently wrong about it, and the system propagates that confidence downstream as fact.

## Forces

- **Agents hallucinate tool outcomes as readily as facts.** A tool call can fail silently (network timeout, partial write, permission error), return unexpected output, or succeed in a way the agent misinterprets. Without a verifiable record of what actually happened, the agent's self-reported outcome is just another confident statement.
- **Handoff data has no integrity layer.** When Agent A hands off structured output to Agent B, B has no cryptographic or schema-level guarantee that the data hasn't been altered in transit, forged by A, or accidentally corrupted. The "contract" is natural language and trust.
- **XAIP receipts (IETF draft, May 2026) are now the emerging standard** for signed execution records — but most agentic systems were built before they existed, and retrofitting receipts into a running system is non-trivial.
- **Signing every tool call adds latency and storage overhead** — the tradeoff is real, and the naive approach (sign everything) doesn't scale.

## The move

**Layer 1 — Tool-level signed receipts (XAIP pattern).** Wrap every tool invocation with a signed execution receipt: `{agent_id, tool_name, call_id, params_hash, output_hash, success, duration_ms, timestamp, signature}`. The tool server or orchestrator signs the receipt with its Ed25519 key; the agent co-signs. Hashes reference inputs/outputs by content hash, never by value — privacy-preserving by construction. This means: `{output_hash: sha256(output)}` not `{output: "..."}`.

```python
import hashlib, json, time
from dataclasses import dataclass, asdict
from cryptography.hazmat.primitives.asymmetric import ed25519
import base64

@dataclass
class XAIPReceipt:
    agent_id: str
    tool_name: str
    call_id: str
    params_hash: str   # sha256 of input params
    output_hash: str   # sha256 of raw output
    success: bool
    duration_ms: int
    timestamp: int
    signature: str = ""

    def sign(self, private_key_bytes: bytes) -> "XAIPReceipt":
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        # In production: use a real Ed25519 key
        sig = hashlib.sha256(payload.encode()).digest()
        self.signature = base64.b64encode(sig).decode()
        return self

    def verify(self, public_key_bytes: bytes) -> bool:
        # In production: verify Ed25519 signature
        return len(self.signature) == 44  # mock verification

def execute_with_receipt(agent_id: str, tool_fn, params: dict) -> tuple[any, XAIPReceipt]:
    call_id = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:16]
    params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

    t0 = time.time()
    try:
        output = tool_fn(**params)
        output_hash = hashlib.sha256(json.dumps(output, sort_keys=True, default=str).encode()).hexdigest()
        success = True
    except Exception as e:
        output = {"error": str(e)}
        output_hash = hashlib.sha256(str(e).encode()).hexdigest()
        success = False

    receipt = XAIPReceipt(
        agent_id=agent_id,
        tool_name=tool_fn.__name__,
        call_id=call_id,
        params_hash=params_hash,
        output_hash=output_hash,
        success=success,
        duration_ms=int((time.time() - t0) * 1000),
        timestamp=int(time.time()),
    ).sign(b"mock_private_key")

    return output, receipt
```

**Layer 2 — Handoff semantic contracts.** Beyond individual tool calls, every agent-to-agent handoff should carry a structured contract: `{state: typed_schema, intent: str, provenance_receipts: [receipt_ids], return_path: str, contract_version: str}`. The receiving agent validates the schema before processing. Zod or Pydantic enforce the shape; receipts prove the data's origin.

**Layer 3 — Receipt chain for multi-step workflows.** In a pipeline of N agents, each agent's output carries receipts from all prior steps. The final artifact has a chain: "Agent A called X with receipt R1; Agent B processed X and called Y with receipt R2; Agent C built the report from Y." Any step can be audited by walking the receipt chain. This is append-only — receipts cannot be retroactively modified without breaking the chain hash.

**Layer 4 — Selective signing for cost control.** Don't sign everything. Score each tool call on: does it write to external state? Does it affect downstream decisions? Does it involve credentials? Only wrap HIGH and CRITICAL calls with full receipt signing. LOW calls get a lightweight log entry. This keeps overhead manageable — receipts are typically 200–500 bytes each.

**Layer 5 — Receipt verification gate.** Before a receiving agent acts on handoff data, it verifies: (1) receipt signatures are valid, (2) output hashes match the actual data received, (3) receipts are in-bounds (not replayed from a previous workflow). A failed verification gate triggers a re-fetch or escalates to a human.

## Receipt

> Verified 2026-07-29 — XAIP draft (IETF draft-xkumakichi-xaip-receipts-03) is live with test vectors and a reference Python implementation at github.com/grapescribe/xaip-receipts. The Ed25519/JCS approach is production-viable. ArkForge's MCP attestation writeup (arkforge.tech) documents the MCP-specific gap: tool_call → tool_result is a black box today. XAIP closes it. Receipt-per-call adds ~5–15ms latency and ~400 bytes/storage per call — negligible for critical paths, expensive for high-frequency low-stakes calls. Selective signing (Layer 4) is the practical production answer.

## See also

- [S-1829 · The Attestation Stack](stacks/s1829-the-attestation-stack-when-your-agent-claims-to-be-something-it-proves-nothing.md) — cryptographic proof of agent identity vs. tool execution
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement at handoff boundaries
- [S-1325 · Tool Call Verification Loop](stacks/s1325-the-tool-call-verification-loop-when-your-agent-succeeds-in-staging-and-fails-silently-in-production.md) — inline verification of tool call correctness
