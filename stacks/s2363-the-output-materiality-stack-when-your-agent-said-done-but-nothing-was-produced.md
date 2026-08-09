# S-2363 · The Output Materiality Stack — When Your Agent Said Done but Nothing Was Produced

[Your agent ran for 47 minutes. The final log says: `status: complete`, `task_id: inv-48921`, `confidence: 0.97`. The task was to produce a compliance report and email it to the regulator. The inbox is empty. The file share is empty. Every API call returned 200. The agent's success signal lied — not because of an error, but because it couldn't verify the output actually materialized.]

## Forces

- **The agent's success signal is structural, not semantic.** Agents report success based on the LLM declaring completion or the tool call returning 200. Neither indicates whether the downstream system accepted the output, whether the file was written to the right path, or whether the email landed in an inbox rather than a spam folder. The agent has no concept of output materiality.
- **Silent green exits outnumber loud failures in production.** The most expensive agent failure mode in 2026 is not crashes or hallucinations — it's the agent confidently reporting task completion while producing zero artifacts. OperatorIQ's field data (June 2026) shows this running undetected for weeks in multi-step workflows where intermediate steps succeed but the final delivery step silently fails.
- **Verification lives inside the agent that produced the work — the fox guarding the henhouse.** Every existing verification approach (self-reported output checks, prompt-injected receipts, agent-authored logs) is inside the agent's trust boundary. A compromised or hallucinating agent cannot reliably verify its own output.
- **Logs are mutable. Mutable logs are not evidence.** Observability platforms write to databases that anyone with write access can modify. An audit trail you can rewrite is not an audit trail. EU AI Act Article 12 (effective August 2026, 7% global revenue penalties for non-compliance) mandates tamper-evident records for high-risk AI decisions — standard logging doesn't satisfy this.
- **The artifact may exist but be wrong.** A file on disk proves something was written, not that it was the right thing, in the right format, with the right content. Output materiality requires proof not just of existence but of substance.

## The move

Output materiality verification requires an **external attestation layer** — a process outside the agent's trust boundary that independently proves artifacts were produced, with the right properties, in the right destinations.

### The three-tier verification stack

**Tier 1 — Output existence receipt (cryptographic):**
After the agent completes, an independent daemon (running with signing keys the agent cannot access) probes every declared output destination and produces a signed output receipt:

```
Ed25519-signed attestation:
  task_id: inv-48921
  declared_outputs:
    - type: file, path: /reports/2026/compliance-q2.pdf
    - type: email, to: regulator@example.gov, subject: Q2 Compliance
  receipt_type: output_materiality_v1
  probing_method: { file: sha256_hash, email: smtp_delivery_receipt }
  probed_at: 2026-08-09T03:14:22Z
  next_hop: sha256(chain_pointer)  # hash-chained to prior receipt
```

The agent cannot forge this receipt — the probing daemon has its own signing key, separate process space, and access to ground-truth destinations (SMTP delivery receipts, cloud storage API confirmations, database INSERT confirmations).

**Tier 2 — Artifact content attestation (semantic):**
For consequential outputs (contracts, reports, compliance submissions), Tier 2 hashes the actual artifact content and includes the content hash in the receipt. This proves not just that a file exists but that the specific file with the specific content was produced — detectable if the file is later swapped.

**Tier 3 — Delivery proof (protocol-level):**
For outputs requiring cross-system delivery (emails, API calls, database writes), Tier 3 captures the protocol-level confirmation: SMTP delivery receipt ID, HTTP 201 with the created resource ID, database transaction commit log offset. These are authoritative signals from the destination system, not from the agent.

### Implementation pattern (Python + agent-receipts SDK)

```python
from obsigna import ReceiptDaemon
from ads_foundation import ProofTrailMonitor

daemon = ReceiptDaemon(
    signing_key_path="/etc/agent-receipts/signer-key.ed25519",
    receipt_store="postgresql+bolt://receipts.prod/",
    agent_isolation=True,  # daemon key inaccessible to agent process
)
monitor = ProofTrailMonitor(daemon=daemon)

# Wrap the agent's output step — runs outside agent's trust boundary
@monitor.track_output_materiality(
    expected_outputs=[
        {"type": "file", "path": "/reports/compliance/{task_id}.pdf"},
        {"type": "email", "to": "regulator@example.gov"},
    ],
    timeout_seconds=300,
)
def run_reporting_task(task_id: str, params: dict) -> dict:
    # Agent runs here — the monitor probes outputs after completion
    return agent.execute(task_id=task_id, params=params)

result = run_reporting_task("inv-48921", {...})
# After completion, daemon automatically:
# 1. Probes /reports/compliance/inv-48921.pdf — computes SHA-256
# 2. Queries SMTP server for delivery receipt matching message_id
# 3. Signs and hash-chains the output receipt
# 4. Stores to receipt_store with Merkle tree anchor
```

### Silent green detection: the output emptiness test

For any task that produces artifacts, add an explicit emptiness check that the agent cannot suppress:

```python
def verify_output_materiality(task_id: str, declared_paths: list[str]) -> dict:
    """Called by the daemon — not by the agent."""
    results = {}
    for path in declared_paths:
        if not os.path.exists(path):
            results[path] = {"status": "MISSING", "material": False}
        elif os.path.getsize(path) == 0:
            results[path] = {"status": "EMPTY", "material": False}
        elif os.path.getsize(path) < MINIMUM_SIZE.get(Path(path).suffix, 100):
            results[path] = {"status": "TRUNCATED", "material": False}
        else:
            sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            results[path] = {"status": "MATERIAL", "hash": sha, "material": True}
    
    all_material = all(r["material"] for r in results.values())
    return {"task_id": task_id, "all_material": all_material, "details": results}
```

If `all_material == False`, the task is a silent green exit — alert immediately regardless of what the agent logged.

### Key design constraints

| Constraint | Rationale |
|---|---|
| Signing keys live outside agent process | Agent compromise cannot forge receipts |
| Probing daemon has independent cloud credentials | Cannot be fooled by agent-controlled mock endpoints |
| Receipts hash-chain to prior receipts | Tamper-evident — modifying any receipt breaks the chain |
| Output paths declared *before* execution | Prevents agent retroactively creating artifacts to pass verification |
| Content hash included for consequential outputs | Detects artifact swap after the fact |

## Receipt

> Verified 2026-08-09 — Agent Receipts/Obsigna (agentreceipts.ai, Apache 2.0, obsigna Python SDK pip installable), ProofTrail (prooftrail.dev, Merkle-backed receipts with Python decorator API), PipeLab Pipelock production deployment (May 2026, signed action receipts blocking a bad response). EU AI Act Article 12 mandate confirmed at prooftrail.dev. Silent green exit taxonomy from OperatorIQ field data (June 2026). Pattern: logs = self-attestation; receipts = independent attestation — the core architectural distinction driving all three tools (Obsigna, ProofTrail, PipeLab Pipelock) toward the same solution shape.

## See also

- [S-1113 · The Five-Layer Audit Trail Stack](s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — audit trail layers, of which output materiality is one
- [S-1164 · Agent Hash-Chained Audit Trail](s1164-agent-hash-chained-audit-trail-the-immutable-ledger-pattern.md) — immutable ledger pattern for tamper-evident chains
- [S-1509 · The Oracle Problem Stack](s1509-the-oracle-problem-stack-when-you-cannot-tell-if-your-agent-is-right.md) — the verification gap for open-ended agent tasks
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — semantic failure detection when the agent's success signal lies
- [S-1032 · The Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — silent failure patterns in agent retry logic
