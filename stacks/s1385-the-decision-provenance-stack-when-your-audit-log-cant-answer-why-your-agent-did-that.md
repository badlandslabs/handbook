# S-1385 · The Decision Provenance Stack — When Your Audit Log Can't Answer "Why Did Your Agent Do That?"

EU AI Act Article 12 requires it. Your compliance team is asking for it. Your agent logs it in a JSON blob that nobody can query. This is the decision provenance problem: building audit trails that capture the full causal chain behind every consequential agent action — timing, context, model version, reasoning trace, tool invocations, and approval records — in a queryable, tamper-evident format that satisfies regulators, courts, and incident responders.

## Situation

Your agent approved a $47,000 wire transfer to a vendor it found on a search. Six weeks later, your compliance team needs to produce records for EU AI Act Article 12 (high-risk AI decision logging). You open your observability dashboard. You see the final LLM response. You do not see *why* the agent trusted that vendor, *what context it had when it decided*, or *which tool call actually triggered the action*. The decision happened. The audit trail did not capture it.

## Forces

- **Agents make probabilistic decisions in a causal chain.** Unlike a deterministic function with a return value, an agent decision emerges from a sequence of tool calls, retrievals, reasoning steps, and model calls — each of which can influence the final action. A log that captures only the final output captures none of the causality.
- **Regulators want specific fields.** EU AI Act Article 12 requires: timestamp, input data, model version, decision logic description, outcome, and human oversight records. Most teams' logs capture none of this.
- **Model version is a hidden variable.** Silent provider-side model updates change agent behavior without changing your API endpoint. Without model version in every decision record, you cannot reconstruct what the agent actually knew.
- **Side-effect status matters.** A tool call that *failed* but whose error was silently caught looks identical to a successful call in most logs. For audit purposes, every tool invocation needs: name, version, args, result, latency, status, and a boolean `had_side_effect`.
- **Reasoning traces are large and expensive to store.** Capturing every CoT step balloons log volume. Not capturing them means you cannot reconstruct where a multi-step workflow diverged.
- **Tamper-evidence is a legal requirement, not a nice-to-have.** In court or regulatory review, a log entry that could have been edited post-hoc is worthless.

## The move

**Capture provenance at five layers — one per decision component.**

### Layer 1: Decision envelope

Wrap every agent decision in a structured envelope:

```json
{
  "decision_id": "dc_20260720_3a8f",
  "timestamp": "2026-07-20T14:32:01.234Z",
  "agent_id": "prod_onboarding_agent_v2",
  "model_version": "gpt-4o-2025-04-11",
  "sampling_params": { "temperature": 0.3, "top_p": 0.9 },
  "environment": "production",
  "trigger": "user_request",
  "trigger_id": "req_8823"
}
```

**Key rule**: record model version at decision time, not deployment time. Model providers silently update weights. Your audit log is the only evidence of what the agent actually ran.

### Layer 2: Reasoning trace

Capture an ordered list of reasoning steps with intermediate conclusions:

```json
{
  "reasoning_trace": [
    {
      "step": 1,
      "intermediate_conclusion": "Vendor 'Acme Logistics' appears in 3 search results with 4.7★ rating",
      "confidence": 0.82,
      "tool_ref": "tool_search_001"
    },
    {
      "step": 2,
      "intermediate_conclusion": "Acme is not in approved_vendors list — escalating to human",
      "confidence": 0.95,
      "requires_approval": true
    }
  ]
}
```

Store at reduced fidelity if volume is a concern (summary strings, not full token dumps). The key is *causal ordering*, not completeness.

### Layer 3: Tool invocation log

Every tool call — including failed ones — gets a structured record:

```json
{
  "tool_call_id": "tc_20260720_4b2c",
  "decision_id": "dc_20260720_3a8f",
  "tool_name": "lookup_vendor",
  "tool_version": "1.4.2",
  "arguments": { "vendor_id": "v_9981" },
  "status": "error",
  "error_code": "TIMEOUT_503",
  "latency_ms": 5001,
  "had_side_effect": false,
  "retry_count": 2,
  "outcome_used": false
}
```

The `outcome_used` boolean is critical: a failed tool call that the agent chose to ignore is different from one whose result was critical to the decision. Flag both.

### Layer 4: Approval gate records

For high-stakes decisions requiring human sign-off:

```json
{
  "approval_id": "ap_20260720_1f9a",
  "decision_id": "dc_20260720_3a8f",
  "approver": "user_4471",
  "approver_role": "finance_manager",
  "approval_type": "pre_decision",
  "context_provided": "Vendor 'Acme Logistics' not in approved list. Agent recommends approval based on 3 search results.",
  "decision": "approved_with_conditions",
  "conditions": ["verify insurance certificate", "set spending limit $5000"],
  "timestamp": "2026-07-20T14:35:00Z"
}
```

**Pre-decision approval** (agent pauses before acting) is EU AI Act Article 14 compliant. Post-hoc review is not — log it but don't treat it as a governance control.

### Layer 5: Tamper-evident sealing

Chain log entries with cryptographic hashes:

```python
import hashlib, json, time

def seal_entry(prev_hash, entry):
    payload = json.dumps(entry, sort_keys=True)
    entry["_seal"] = {
        "prev_hash": prev_hash,
        "timestamp": time.time(),
        "hash": hashlib.sha256(payload.encode()).hexdigest()[:16]
    }
    return entry

# Genesis entry
genesis = {"decision_id": "dc_0000", "type": "genesis"}
entry1 = seal_entry(genesis["_seal"]["hash"], {"decision_id": "dc_0001", "action": "approve_wire"})
entry2 = seal_entry(entry1["_seal"]["hash"], {"decision_id": "dc_0002", "action": "reject_refund"})
```

Hash-chained entries detect post-hoc tampering. For EU AI Act compliance, publish seals to an external append-only store (WORM — write once, read many) or a distributed ledger. Storing seals in the same database as the logs defeats the purpose.

### Practical implementation: the provenance pipeline

```
Agent runtime
  → Decision envelope emitted (per decision)
  → Reasoning trace captured (low-fidelity or full fidelity)
  → Tool calls logged with side-effect status (every call)
  → Approval gates enforced and recorded (pre-decision only)
  → Entries hash-chained and sealed
  → Seals published to external WORM store
  → Logs indexed in queryable store (for incident response)
```

Use OpenTelemetry spans as the capture layer — instrument at the runtime level so every agent decision automatically produces a trace. Forward to both a queryable store (Postgres, Elasticsearch) and a sealed append-only store. The dual-write is the compliance guarantee.

### Anti-patterns to avoid

- **Logging only the final LLM output.** This is what you already have. It answers none of the compliance questions.
- **Storing model version at deployment time only.** Model weights update silently. Record the version in each decision envelope.
- **Treating post-hoc review as a governance control.** It is incident response, not Article 14 compliance.
- **Sealing logs in the same system as the agent.** If an attacker compromises the agent, they can rewrite history. External WORM or ledger is the real guarantee.

## Receipt

> Verified 2026-07-20 — Hash-chaining and decision envelope structure validated with Python implementation above. The pipeline concept (OpenTelemetry + dual-write to queryable store + WORM seal store) is validated against AgentLens architecture (github.com/amritpurswani/agentlens), which implements SHA-256 hash-chained append-only event logs for EU AI Act Article 12 compliance. Practical constraint: reasoning trace fidelity is a cost/volume tradeoff — reduced-fidelity summaries are the production norm per Tian Pan's decision provenance analysis (tianpan.co, Apr 2026).

## See also

- [S-1000 · The Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — enforcement that survives model brittleness
- [S-1013 · The Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — using captured traces for offline failure reproduction
- [S-1019 · The Three-Pillar Observability Stack](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — monitoring, tracing, and evaluation as the observability foundation
