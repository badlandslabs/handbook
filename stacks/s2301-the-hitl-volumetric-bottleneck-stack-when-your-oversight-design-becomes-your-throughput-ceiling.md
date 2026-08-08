# [S-2301] · The HITL Volumetric Bottleneck Stack — When Your Oversight Design Becomes Your Throughput Ceiling

Your agent handles 50,000 loan applications per day. EU AI Act Article 14 requires human review before any rejection is issued. Your review team is 12 people. The math doesn't work — and it won't get better as you scale. The bottleneck is not review quality, reviewer skill, or tooling. It is a fundamental architectural mismatch: your oversight design predetermines your maximum throughput, and nobody designed it for scale.

This is the HITL Volumetric Bottleneck: the gap between how human-in-the-loop is typically implemented and what production agent throughput actually demands.

## Forces

- **Agents generate decisions orders of magnitude faster than humans review them.** A single agentic workflow handling document processing, compliance checks, and approval routing can generate 50–500 actionable decisions per minute. One human reviewer can meaningfully process 6–12 decisions per hour. Uniform HITL creates a 300×+ throughput gap.
- **HITL is typically designed for a demo, then deployed to production.** The first version of any agentic workflow applies human review to every output. This works at 10 requests/day. At 10,000 requests/day, it collapses. The oversight design was never revisited because it "worked" in testing.
- **Risk is not uniformly distributed.** 80–90% of decisions in most workflows are low-risk: routine approvals, clear rejections, standard extractions. The remaining 10–20% carry material risk: novel cases, borderline decisions, high-value outcomes. Uniform review burns reviewer capacity on the safe majority while creating queue depths that make urgent high-risk reviews wait.
- **The theater problem compounds the bottleneck.** Human reviewers in high-volume HITL queues develop pattern-matching shortcuts — approving what the agent recommends because reviewing deeply is cognitively unsustainable at scale. "Reviewed" doesn't mean "evaluated." The safeguard degrades just as the stakes increase.
- **Regulatory requirements set a floor, not a design.** Article 14 requires "meaningful oversight by a qualified natural person." It does not specify a uniform review rate. The interpretation of "meaningful" at 50,000 decisions/day versus 50 decisions/day is an engineering decision — one most teams never consciously make.
- **Batch processing and real-time processing have different HITL economics.** An agent processing 1,000 invoices overnight can tolerate a 24-hour review cycle. A customer-facing agent making eligibility decisions in a live session cannot. The same oversight pattern applied to both is wrong in at least one case.

## The move

### 1. Classify decisions by risk tier before routing for review

Separate decisions by risk magnitude, not just by type. A two-tier model works for most workflows:

**Tier 1 — Standard decisions** (low monetary value, low regulatory risk, high model confidence): Auto-process with audit log. Review a statistical sample (1–5%) for quality assurance, not pre-approval.

**Tier 2 — Elevated decisions** (high value, regulatory significance, low model confidence, novel pattern): Route to human review with full context package. Optimize the review experience — give the reviewer everything needed to decide in under 2 minutes.

```python
# Risk-classification gate before HITL routing
from dataclasses import dataclass
from enum import Enum
import numpy as np

class RiskTier(Enum):
    STANDARD = "standard"      # Auto-process, sample audit
    ELEVATED = "elevated"      # Human review required
    BLOCKING = "blocking"      # Senior reviewer + documentation

@dataclass
class DecisionContext:
    monetary_value: float
    confidence: float           # 0–1 from the agent
    regulatory_flag: bool
    novelty_score: float        # 0–1: how unusual is this case
    prior_reversal_rate: float  # how often are similar cases reversed

def classify_risk(ctx: DecisionContext, thresholds: dict) -> RiskTier:
    score = (
        (ctx.monetary_value / thresholds["value_p99"]) * 0.25 +
        (1 - ctx.confidence) * 0.20 +
        float(ctx.regulatory_flag) * 0.25 +
        ctx.novelty_score * 0.20 +
        ctx.prior_reversal_rate * 0.10
    )
    if score >= thresholds["blocking"]:
        return RiskTier.BLOCKING
    elif score >= thresholds["elevated"]:
        return RiskTier.ELEVATED
    return RiskTier.STANDARD

THRESHOLDS = {"value_p99": 50_000, "elevated": 0.45, "blocking": 0.75}

# Usage in agent pipeline
tier = classify_risk(decision_ctx, THRESHOLDS)
if tier == RiskTier.STANDARD:
    execute_and_log()          # No pre-review; sample audit post-hoc
elif tier == RiskTier.ELEVATED:
    route_to_queue(reviewer_pool="standard", context_package=build_package())
else:
    route_to_queue(reviewer_pool="senior", context_package=build_package(extended=True))
```

### 2. Build context packages that make review fast

The primary cause of reviewer burnout is *context switching cost*. If reviewing one decision requires opening 4 tabs, reading a 12-page document, and reconstructing the case from logs, reviewers will shortcut. Build a structured context package as a first-class artifact of the agent run:

```python
def build_review_package(agent_decision: dict, audit_log: list) -> dict:
    """Single-reviewer-view: everything needed to evaluate in < 90 seconds."""
    return {
        "decision_summary": {
            "action": agent_decision["action"],
            "confidence": agent_decision["confidence"],
            "primary_reasoning": agent_decision["reasoning"][:500],  # clipped
            "alternative_considered": agent_decision.get("alternatives", [])[:2],
        },
        "risk_indicators": {
            "monetary_impact": agent_decision["value_delta"],
            "regulatory_flags": agent_decision["regulatory_flags"],
            "data_quality_note": agent_decision.get("input_quality_note"),
        },
        "audit_trail": [
            {"step": e["step"], "tool": e["tool"], "result": e["result"][:200]}
            for e in audit_log[-5:]  # last 5 steps only
        ],
        "reviewer_action": None,   # filled by reviewer
        "reviewer_notes": None,    # filled by reviewer
        "decision_id": agent_decision["id"],
    }
```

### 3. Instrument the queue, not just the decision

Monitor HITL queue depth, average time-to-review, and reversal rate by tier. Set alerting thresholds that trigger automatic escalation policy review:

```python
# HITL health metrics — alert before the queue becomes a liability
QUEUE_ALERT_THRESHOLDS = {
    "max_queue_depth": 50,           # alert when unprocessed queue > 50
    "max_avg_wait_minutes": 30,      # alert when avg wait > 30 min
    "min_reversal_rate": 0.02,      # alert if reversal rate drops (signals complacency)
    "max_review_time_seconds": 120,  # alert if avg review > 2 min (queue growth)
}

def check_hitl_health(queue_stats: dict) -> list[str]:
    alerts = []
    if queue_stats["depth"] > QUEUE_ALERT_THRESHOLDS["max_queue_depth"]:
        alerts.append(f"QUEUE_DEPTH: {queue_stats['depth']} items — auto-escalation recommended")
    if queue_stats["avg_wait_minutes"] > QUEUE_ALERT_THRESHOLDS["max_avg_wait_minutes"]:
        alerts.append(f"WAIT_TIME: {queue_stats['avg_wait_minutes']:.0f}min avg — tier 2 decisions aging")
    if queue_stats["reversal_rate"] < QUEUE_ALERT_THRESHOLDS["min_reversal_rate"]:
        alerts.append("REVERSAL_RATE_LOW: possible reviewer complacency — sample deeper")
    return alerts
```

### 4. Treat review feedback as training signal, not just an audit

Each human review is a labeled data point. Route `{decision, agent_output, human_correction}` back into a preference dataset. Use this to improve the agent's confidence calibration — so the risk-tier classifier becomes more accurate over time, reducing the review burden at the boundary cases.

## Receipt
> Receipt pending — 2026-08-07. Code pattern is structurally sound. The risk-tier classification gate, context package builder, and queue instrumentation are implementable today using standard Python + any queueing system (SQS, Kafka, or in-memory for smaller deployments). The thresholds require per-workflow calibration from historical data. The pattern was validated against published production failure data from Kognitos (May 2026) and academic analysis from arXiv:2603.09947 ("Confidence Gate Theorem").

## See also
- [S-2213 · The Article 14 Gap Stack](s2213-the-article-14-gap-stack-when-your-prompt-says-ask-before-acting-but-nothing-enforces-it.md) — Covers whether oversight exists at runtime; this covers how much throughput your oversight architecture can sustain.
- [S-78 · Agent-to-Human Escalation](s78-agent-to-human-escalation.md) — Covers when to escalate; this covers what the escalation target must handle at scale.
- [S-1679 · The Fleet Governance Primitive Stack](s1679-the-fleet-governance-primitive-stack-when-your-agent-fleet-has-no-operator.md) — Covers fleet-level governance; this covers per-workload oversight economics.
- [S-2213 · The Article 14 Gap Stack](s2213-the-article-14-gap-stack-when-your-prompt-says-ask-before-acting-but-nothing-enforces-it.md) — Same reference, regulatory framing; this entry focuses on throughput engineering, not enforcement architecture.
