# S-2312 · The Governed Uncertainty Stack — When Your Agent Claims 90% Confidence and Is Still Wrong

Your loan-underwriting agent has a 90% confidence threshold. Every transaction that scores below it gets escalated. The one that scored 87% — that was the fraudulent application your analyst caught — came back from review because the agent output looked polished and complete. The one that scored 94% — the one that slipped through with a misclassified collateral type — also came back. Your confidence threshold was calibrated on a dataset that doesn't resemble your production distribution. And even if it were, LLM confidence scores are systematically miscalibrated: a model that says 90% is right roughly 75% of the time in adversarial open-world settings.

This is the governed uncertainty problem: the gap between what an agent believes it knows and what it actually knows, amplified by the fact that the signal you use to detect ignorance — its verbal confidence — is the least reliable signal you have. [S-807](s807-the-confidence-gap-stack-when-agents-say-i-dont-know-then-act-anyway.md) covers why agents misrepresent their uncertainty. This entry covers what to build around them.

## Forces

- **LLM confidence is a model output, not a calibrated probability.** Verbalized confidence is shaped by RLHF to sound appropriately certain — not to accurately reflect true accuracy. A model trained to be helpful will always err toward expressing confidence it has earned, not confidence it deserves.
- **Escalation friction determines whether the threshold works.** If escalating costs more (cognitive load, latency, user experience, budget) than proceeding, rational agents will route around the threshold. The governance architecture must make escalation cheaper than proceeding on uncertain ground.
- **Miscalibration compounds across chains.** Three agents each reporting 90% confidence produce roughly 42% probability that all three are simultaneously correct — not 90%. The system needs a structural escalation path that doesn't depend on individual agent confidence signals.
- **The EU AI Act makes escalation non-optional for high-risk systems from August 2026.** Auditability of the human-in-the-loop decision trail is now a compliance requirement, not a product choice.

## The Move

### 1. Decompose the Confidence Signal

Never use a single confidence number. Decompose it into three orthogonal signals:

```
ConfidenceReport = {
  "calibrated_confidence": 0.87,      # verbalized confidence — the weakest signal
  "uncertainty_indicators": [...],      # parsing failures, low retrieval scores, 
                                       # contradictory retrieved documents, 
                                       # tool call uncertainty, repeated retries
  "stakes_multiplier": 1.0,           # risk-adjusted: dollar amount, data sensitivity,
                                       # regulatory tier, downstream blast radius
}
```

The calibrated_confidence field is the least informative. The uncertainty_indicators are what you actually govern on.

### 2. Build a Three-Tier Escalation Ladder

```
TIER_1 — Proceed with verification
  trigger: uncertainty_indicators.length <= 2 AND stakes_multiplier < 0.5
  action: agent proceeds, annotates output with confidence stamp, 
          logs for retrospective review
  
TIER_2 — Proceed with human notification
  trigger: uncertainty_indicators.length <= 4 AND stakes_multiplier >= 0.5
  action: agent proceeds, sends async notification to human reviewer,
          reviewer approves/rejects asynchronously within SLA window
  
TIER_3 — Pause and await approval
  trigger: uncertainty_indicators.length > 4 OR calibrated_confidence < 0.6
           OR stakes_multiplier >= 1.0
  action: agent pauses, presents the decision point to human,
          resumes only on explicit approval
```

The key insight: stakes_multiplier is the gate. It is not derived from the model's output — it is derived from the context of the request. A 60% confident answer about a low-value routine task is Tier 1. A 60% confident answer about a high-value financial decision is Tier 3.

### 3. Instrument the Calibration Loop

Your escalation thresholds will be wrong. Calibrate them by tracking:

```python
@dataclass
class EscalationRecord:
    session_id: str
    calibrated_confidence: float
    uncertainty_indicators: list[str]
    stakes_multiplier: float
    tier_reached: int
    human_override: bool        # did the human change the outcome?
    human_intervention_type: str  # "approved", "rejected", "modified"
    actual_outcome: str         # "correct", "incorrect", "unknown"


def compute_calibration_delta(records: list[EscalationRecord]) -> dict:
    """
    Run weekly to detect systematic miscalibration.
    Tracks: threshold accuracy, indicator false-positive rate,
    and stakes_multiplier sensitivity.
    """
    tier3_records = [r for r in records if r.tier_reached == 3]
    override_rate = sum(1 for r in tier3_records if r.human_override) / max(len(tier3_records), 1)
    
    # If Tier 3 has <10% override rate, your threshold is too conservative
    # If Tier 3 has >60% override rate, your calibrated_confidence threshold 
    # is not the right gate — look at uncertainty_indicators instead
    
    return {
        "tier3_override_rate": override_rate,
        "tier1_false_negative_rate": _compute_tier1_miss_rate(records),
        "recommended_confidence_threshold": _recalibrate(
            [r for r in records if r.actual_outcome != "unknown"],
            target_precision=0.85
        )
    }
```

### 4. Make Escalation a First-Class Tool

Do not implement escalation as a prompt instruction. Implement it as a tool the agent is *required* to call:

```json
{
  "name": "escalate_for_review",
  "description": "Pause execution and request human review. REQUIRED when 
                   uncertainty_indicators > 4 or stakes_multiplier >= 1.0.
                   Calling this is always safe — proceeding on uncertain ground
                   without calling it is a governance violation.",
  "parameters": {
    "type": "object",
    "required": ["decision_point", "options_presented", "reason_for_escalation"],
    "properties": {
      "decision_point": {"type": "string", "description": "What decision needs review"},
      "options_presented": {"type": "array", "description": "Candidate actions with risk annotations"},
      "reason_for_escalation": {"type": "string", "description": "Specific uncertainty signal"},
      "stakes_multiplier": {"type": "number", "description": "Risk-adjusted stakes score"}
    }
  }
}
```

The governance enforcement happens at the harness layer: if the agent does not call `escalate_for_review` when the conditions are met, the harness blocks the subsequent tool calls until it does. This moves escalation from a suggestion in a system prompt to a structural requirement.

## Receipt

> Verified 2026-08-08 — The three-tier escalation ladder pattern appears consistently across Bittalks.org (May 2026), DigitalApplied HITL guide (June 2026), and Redis.io human-in-the-loop architecture guide (April 2026). EU AI Act enforcement date (August 2026) confirmed via OWASP GenAI documentation. Calibration loop metric design (override_rate, false_negative_rate) matches standard eval-harness practice documented in MLflow Agentic AI Monitoring Guide (June 2026). The stakes_multiplier decomposition is explicitly recommended by DigitalApplied's "calibration math" section: "the confidence number you are thresholding against is not trustworthy."

## See also

- [S-807 · The Confidence Gap](s807-the-confidence-gap-stack-when-agents-say-i-dont-know-then-act-anyway.md) — the attribution problem: why verbalized confidence misrepresents true uncertainty
- [S-1890 · The Difficulty-Aware Escalation Stack](s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — routing by difficulty, not just confidence
- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — root cause analysis when escalation itself fails
- [S-2311 · The Agentic Consensus Stack](s2311-the-agentic-consensus-stack-when-two-agents-agree-on-the-wrong-answer.md) — why correlated confidence across agents makes individual thresholds insufficient
