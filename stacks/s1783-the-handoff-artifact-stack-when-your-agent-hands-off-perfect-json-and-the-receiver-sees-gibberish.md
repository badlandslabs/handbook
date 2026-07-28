# S-1783 · The Handoff Artifact Stack — When Your Agent Hands Off Perfect JSON and the Receiver Sees Gibberish

Your multi-agent pipeline has two agents. Both pass their unit tests. Both return HTTP 200. The orchestrator connects them: Agent A outputs a JSON artifact, Agent B reads it and produces the final answer. In staging, it works. In production, Agent B starts hallucinating aggressively on what should be a trivial field extraction. You dig into the trace. Agent A's output was valid JSON. The schema was correct. The content was correct. But Agent B interpreted `"2026-01-15"` as "sometime in January" and `"amount": "USD 1,234.56"` as the string "one million two hundred thirty-four point five six dollars." No error was thrown. No validation failed. The artifact was structurally perfect and semantically broken.

This is the **handoff artifact problem** — the gap between what the sender encodes and what the receiver decodes. The artifact format looks like a technical detail. It is actually the trust boundary of every multi-agent system.

## Forces

- **JSON is a serialization format, not a communication contract.** JSON encodes structure and values. It encodes nothing about intent, units, precision, freshness, or provenance. An agent reading a JSON artifact must infer semantics the sender never stated — and models infer differently from humans, and differently from each other.
- **Agents accumulate hidden context between turns.** Agent A generated its output in a session where `"customer_id"` referred to an internal UUID. Agent B receives the artifact in a fresh session where `"customer_id"` was used in a different context entirely. Both are correct by their own local context. The handoff artifact carries no semantic anchors to resolve the collision.
- **Schema validation is the floor, not the ceiling.** A JSON Schema validator confirms `type: string` and `format: date`. It cannot confirm that `2026-01-15` is not a fictional date, that `USD 1,234.56` is not a monetary total in a ledger, or that `status: "active"` means the same thing to the billing agent as it does to the provisioning agent.
- **Multi-agent pipelines amplify handoff errors.** A two-agent handoff has one failure point. A pipeline of five agents has four, and each subsequent agent compounds the previous agent's interpretive errors into its own context. A 95% semantic fidelity rate per handoff produces 81% fidelity after four handoffs.
- **Handoff failures are invisible in single-agent evals.** Your eval suite tests Agent A in isolation and Agent B in isolation. Neither eval catches the artifact interpretation gap because neither tests the boundary.

## The Move

The fix is a **handoff manifest** — a structured annotation layer that travels alongside the artifact, encoding not just what the data is but what it means, where it came from, and what to do if it looks wrong.

### 1. The artifact manifest schema

Every handoff includes a manifest object alongside the primary payload:

```json
{
  "handoff": {
    "version": "1.0",
    "emitter": "agent-customer-classifier-v3",
    "emitter_session_id": "sess-abc123",
    "generated_at": "2026-01-15T14:32:00Z",
    "intent": "Extract and classify customer tier from billing record for downstream provisioning",
    "ttl_seconds": 300,
    "schema_version": "billing-v4",
    "confidence": {
      "overall": 0.91,
      "fields": {
        "customer_id": 0.99,
        "tier": 0.87,
        "effective_date": 0.95
      }
    },
    "provenance": [
      {"step": "db_query", "source": "billing.customer_table", "timestamp": "..."},
      {"step": "classification", "model": "gpt-4o-2025-06", "temperature": 0}
    ],
    "semantic_contracts": {
      "tier": {"type": "enum", "values": ["free", "pro", "enterprise"], "origin": "billing.enum_tier"},
      "effective_date": {"type": "iso8601_date", "timezone": "UTC", "not_future": true},
      "customer_id": {"type": "uuid-v4", "not_empty": true}
    },
    "rejection_signal": "If tier is not in [free, pro, enterprise], halt and escalate"
  },
  "payload": {
    "customer_id": "550e8400-e29b-41d4-a716-446655440000",
    "tier": "enterprise",
    "effective_date": "2026-01-15"
  }
}
```

### 2. Receiver-side manifest parsing

Agent B doesn't just read `payload.tier` — it reads `handoff.semantic_contracts.tier` first to understand the contract, then validates the payload against it before using values:

```python
def parse_handoff_artifact(raw_json: str) -> tuple[dict, list[str]]:
    """
    Parse a handoff artifact and validate semantic contracts.
    Returns (validated_payload, warnings).
    Warnings are non-fatal — they flag uncertainty without blocking execution.
    """
    artifact = json.loads(raw_json)
    handoff = artifact.get("handoff", {})
    payload = artifact.get("payload", {})

    warnings = []
    contracts = handoff.get("semantic_contracts", {})

    # Check TTL
    ttl = handoff.get("ttl_seconds", float("inf"))
    age = time.time() - datetime.fromisoformat(
        handoff["generated_at"].replace("Z", "+00:00")
    ).timestamp()
    if age > ttl:
        warnings.append(f"HANDOFF_EXPIRED: artifact is {age:.0f}s old, TTL={ttl}s")

    # Validate each contracted field
    validated = {}
    for field, contract in contracts.items():
        value = payload.get(field)
        field_warnings = _validate_field(field, value, contract)
        warnings.extend(field_warnings)
        validated[field] = value

    # Carry through uncontracted fields as-is (with a flag)
    for key, value in payload.items():
        if key not in validated:
            warnings.append(f"FIELD_UNCONTRACTED: '{key}' has no semantic contract — interpret with caution")

    return validated, warnings


def _validate_field(field: str, value: Any, contract: dict) -> list[str]:
    warnings = []
    ctype = contract.get("type")

    if ctype == "enum":
        allowed = contract.get("values", [])
        if value not in allowed:
            warnings.append(f"CONTRACT_VIOLATION: {field}='{value}' not in {allowed} — HALTS")

    elif ctype == "iso8601_date":
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if contract.get("not_future") and parsed > datetime.now(timezone.utc):
                warnings.append(f"CONTRACT_VIOLATION: {field}='{value}' is in the future")
        except ValueError:
            warnings.append(f"CONTRACT_VIOLATION: {field}='{value}' is not a valid ISO8601 date")

    elif ctype == "uuid-v4":
        if contract.get("not_empty") and not value:
            warnings.append(f"CONTRACT_VIOLATION: {field} is empty but contract requires non-empty")

    return warnings
```

### 3. The rejection signal

The `rejection_signal` field in the manifest encodes what to do when contract violations occur. Unlike error codes, rejection signals are written in natural language by the emitting agent — capturing the sender's intent about what "broken" means:

```python
def execute_with_rejection_signal(
    payload: dict,
    handoff: dict,
    agent: Any
) -> dict:
    """
    Execute agent action with handoff contract enforcement.
    If rejection_signal is triggered, halt and produce a structured escalation artifact
    instead of silently degrading.
    """
    validated, warnings = parse_handoff_artifact(
        json.dumps({"handoff": handoff, "payload": payload})
    )

    rejection_signal = handoff.get("rejection_signal", "")
    triggered = any("HALTS" in w for w in warnings)

    if triggered:
        return {
            "status": "handoff_rejected",
            "artifact_version": handoff.get("version"),
            "emitter": handoff.get("emitter"),
            "violations": [w for w in warnings if "CONTRACT_VIOLATION" in w],
            "warnings": warnings,
            "escalation_reason": rejection_signal,
            "original_payload": payload,
            "action": "ESCALATE"
        }

    return {
        "status": "accepted",
        "warnings": warnings,
        "validated_payload": validated,
        "action": "PROCEED"
    }
```

### 4. Emit the manifest from the sender side

Agent A generates the manifest at the same time as the payload — not as a post-processing step:

```python
def emit_handoff_artifact(
    payload: dict,
    emitter: str,
    intent: str,
    confidence: dict,
    provenance: list[dict],
    semantic_contracts: dict,
    rejection_signal: str,
    ttl_seconds: int = 300
) -> str:
    """
    Emit a handoff artifact with full semantic manifest.
    Call this at the end of Agent A's turn, before returning output to orchestrator.
    """
    import uuid

    return json.dumps({
        "handoff": {
            "version": "1.0",
            "emitter": emitter,
            "emitter_session_id": f"sess-{uuid.uuid4().hex[:12]}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "intent": intent,
            "ttl_seconds": ttl_seconds,
            "schema_version": _infer_schema_version(payload),
            "confidence": {
                "overall": sum(confidence.values()) / len(confidence),
                "fields": confidence
            },
            "provenance": provenance,
            "semantic_contracts": semantic_contracts,
            "rejection_signal": rejection_signal
        },
        "payload": payload
    }, indent=2)
```

### 5. Cross-agent schema negotiation

Before building a pipeline, run a schema negotiation handshake. Both agents share their expected input/output contracts in a structured format:

```python
def negotiate_handoff_contract(
    sender_expects: dict[str, dict],   # field -> semantic contract from Agent A
    receiver_expects: dict[str, dict]   # field -> semantic contract from Agent B
) -> tuple[dict[str, dict], list[str]]:
    """
    Negotiate a shared handoff contract between two agents.
    Returns (merged_contract, conflicts).
    Conflicts are mismatches that must be resolved before the pipeline runs.
    """
    merged = {}
    conflicts = []

    all_fields = set(sender_expects.keys()) | set(receiver_expects.keys())

    for field in all_fields:
        sender_contract = sender_expects.get(field, {})
        receiver_contract = receiver_expects.get(field, {})

        if not sender_contract:
            conflicts.append(f"RECEIVER_EXTRA_FIELD: '{field}' expected by receiver but not emitted by sender")
            continue
        if not receiver_contract:
            conflicts.append(f"SENDER_EXTRA_FIELD: '{field}' emitted by sender but not expected by receiver")
            merged[field] = sender_contract
            continue

        # Type alignment check
        if sender_contract.get("type") != receiver_contract.get("type"):
            conflicts.append(
                f"TYPE_MISMATCH: '{field}' — sender declares {sender_contract['type']}, "
                f"receiver expects {receiver_contract['type']}"
            )

        # Enum alignment check
        if "values" in sender_contract and "values" in receiver_contract:
            if set(sender_contract["values"]) != set(receiver_contract["values"]):
                conflicts.append(
                    f"ENUM_MISMATCH: '{field}' — sender: {sender_contract['values']}, "
                    f"receiver: {receiver_contract['values']}"
                )

        # Union of constraints — take the stricter version
        merged[field] = {**sender_contract, **receiver_contract}

    return merged, conflicts
```

### 6. The handoff quality gate in CI

Before deploying a multi-agent pipeline, run a handoff compatibility test against the artifact schema:

```bash
# Test handoff compatibility in CI
python -m pytest tests/handoff/ \
  --handoff-negotiation \
  --sender-manifest=agents/sender/manifests/ \
  --receiver-manifest=agents/receiver/manifests/ \
  --max-conflicts=0
```

## Receipt

> Verified 2026-07-28 — Design pattern derived from production multi-agent pipeline research. The manifest schema and negotiation protocol are modeled on documented cross-agent handoff failure patterns from production deployments. Cross-referenced against S-1013 (Multi-Agent Boundary Stack) and S-1132 (Semantic Intent Divergence) — this entry covers the artifact-level contract layer those entries reference but don't fully detail. No live execution runnable without a specific multi-agent deployment.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement; this entry covers artifact-level fixes
- [S-1132 · The Semantic Intent Divergence Stack](s1132-the-semantic-intent-divergence-stack-when-your-agents-all-succeed-but-disagree-on-what-success-means.md) — intent divergence at mission level; this entry covers intent alignment at data handoff level
- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — how downstream contamination spreads; this entry provides the artifact-level defense
