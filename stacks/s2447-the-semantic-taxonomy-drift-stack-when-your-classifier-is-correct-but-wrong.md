# S-2447 · The Semantic Taxonomy Drift Stack — When Your Classifier Is Correct But Wrong

Your intent-classifier routes customer messages to the right department. Your policy engine flags risky transactions. Your routing agent sends tickets to the right team. Every eval passes. Every audit looks clean. And then you discover that "urgent" means something different to the model than it does to your business — and has meant something different for three months.

This is **Semantic Taxonomy Drift** — the silent divergence between the concepts your system operates on (defined in prose, in prompts, in policy documents) and the concepts the LLM actually uses when it makes decisions. It compounds silently, fires no errors, and corrupts decisions at scale.

## Forces

- **Definitions live in prose; decisions live in latent space.** Your system prompt defines "high-value customer" as "annual spend > $50k." But the LLM's embedding of "high-value" is shaped by every document it has ever seen — which may include CRM data, support tickets, and sales call summaries where "high-value" correlates with problem complexity, not spend. The model is being precise but answering a different question.

- **Drift accumulates without any code change.** Taxonomy drift isn't caused by deployments. It happens through: (1) model updates that shift how terms are embedded, (2) training data changes that alter connotation, (3) RAG retrieval that injects different contextual framing, and (4) prompt rewrites that subtly shift emphasis. None of these trigger alerts in traditional monitoring.

- **Accuracy metrics lie.** A classifier that scores 94% on a labeled test set can be entirely misaligned with business taxonomy. The labels may encode the old taxonomy; the model has moved to the new one. Your eval suite confirms you're doing the right thing — systematically, at scale.

- **Domain experts and model internals are opaque.** Subject matter experts write the taxonomy. Prompt engineers encode it. No one directly observes what the LLM's embedding space does with it. The gap between authored definition and effective definition is invisible unless you specifically test for it.

## The move

**Test definitions, not just accuracy.** Add a Semantic Calibration Set — a small, curated set of edge cases where the boundary between categories is ambiguous by design. Run these monthly against the live model. Score not just "correct/incorrect" but whether the model's reasoning uses the business taxonomy or an implicit alternative.

```python
# Semantic Taxonomy Calibration Test
# Run monthly against live model; flag when boundary interpretations shift

CALIBRATION_CASES = [
    {
        "id": "HV-001",
        "input": "A prospect signed a $80k deal last quarter but has submitted 14 support tickets in the last month.",
        "taxonomy_key": "high_value_customer",
        "definition": "annual_spend >= 50000",
        "expected_behavior": "trigger_value_retention_flow",
        "probe": "Does this customer trigger the high-value retention workflow? Why or why not? Walk through the exact criteria.",
    },
    {
        "id": "URG-042",
        "input": "Customer says 'I suppose this could wait until Monday if it's easier for your team'.",
        "taxonomy_key": "urgency_classification",
        "definition": "explicit_deadline OR safety_implication OR revenue_impact",
        "expected_behavior": "classify as NON_URGENT",
        "probe": "Classify urgency level. What keywords or signals drove your decision?",
    },
    {
        "id": "RISK-017",
        "input": "Transaction: $12,000 from new account, new device, VPN connection, first purchase. Card verified.",
        "taxonomy_key": "fraud_risk",
        "definition": "score >= 0.7 triggers_step_up_auth; score >= 0.9 blocks",
        "expected_behavior": "score >= 0.9 → BLOCK",
        "probe": "Estimate fraud score 0–1. Which signals contribute most?",
    },
]

def run_calibration(model_client, cases=CALIBRATION_CASES):
    """Detect taxonomy drift by probing model definitions, not just accuracy."""
    results = []
    for case in cases:
        response = model_client.chat([
            {"role": "user", "content": case["probe"] + "\n\nContext: " + case["input"]}
        ])
        # Parse: does the model's reasoning align with the authored taxonomy?
        # Extract key signals, compare against definition keywords
        signals = extract_decision_signals(response.content)
        alignment = compute_taxonomy_alignment(
            signals,
            case["definition"],
            threshold=0.6  # flag if <60% of required criteria appear
        )
        results.append({
            "case_id": case["id"],
            "signals": signals,
            "alignment_score": alignment,
            "expected": case["expected_behavior"],
            "model_reasoning": response.content[:500],
        })
        if alignment < 0.6:
            alert(f"TAXONOMY_DRIFT: {case['id']} alignment={alignment:.2f}")
    return results
```

**Three-layer taxonomy governance:**

1. **Authoring layer** — Every concept used in routing, classification, or policy decisions gets a machine-readable definition with required and optional criteria. Not prose for humans; structured spec for probes.
2. **Calibration layer** — Monthly Semantic Calibration Set run against live model. Track alignment scores over time; flag any drop >5% since last run.
3. **Injection layer** — Embed the active taxonomy definition in every relevant prompt as a structured constraint block, not free-form description. Update it when the calibration layer detects drift.

**The counter-intuitive part:** Adding more detail to prose definitions makes drift *worse*, not better. Long definitions give the model more surface area to reinterpret. Structured criteria blocks with explicit exclusion logic are more stable across model updates.

## Receipt

> Verified 2026-08-10 — Semantic Taxonomy Drift concept synthesized from: (1) Semantic.io taxonomy drift framework (Eubanks, March 2026) distinguishing semantic drift from data/modal drift, (2) arxiv:2605.01604 PAEF framework's coverage of "semantic misalignment" as a distinct failure mode from behavioral drift, (3) Erba/Wiklund real-time detection patterns (July 2026) with 79% risk reduction framing, (4) Bellwether MCP schema detection patterns demonstrating that definition-versioning techniques apply to both API schemas and LLM-grounded taxonomies. No receipts run — this is a pattern analysis chapter. Mark "Receipt pending — [future run with live calibration]"

## See also

- [S-2445 · The Agent Eval Stack](s2445-the-agent-eval-stack-when-your-benchmarks-say-pass-but-your-production-system-is-lying.md) — eval philosophy that would catch taxonomy drift if calibration sets were part of the harness
- [S-3020 · The Confidence Calibration Stack](s3020-the-confidence-calibration-stack-when-your-agent-is-wrong-but-sounds-certain.md) — uncertainty quantification techniques applicable to boundary-case probing
- [S-1927 · The MCP Token Wall Stack](s1927-the-mcp-token-wall-stack-when-three-mcp-servers-consume-71-percent-of-your-context-before-your-agent-does-anything.md) — related drift from MCP schema changes vs. LLM taxonomy changes
