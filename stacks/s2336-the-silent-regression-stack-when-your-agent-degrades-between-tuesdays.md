# S-2336 · The Silent Regression Stack — When Your Agent Degrades Between Tuesdays

Your agent scored 91% on its evaluation suite on Monday. By Thursday, accuracy had quietly dropped to 72%. No model version changed. No deployment happened. No dashboards turned red. Your users started filing tickets by Friday, but you didn't notice until the next sprint review. The capability didn't fail — it drifted away slowly, invisibly, between two days nobody thought to check.

## Situation

You deployed a reliable agent. You built guardrails, wrote tests, set up observability. You trust the system. Then, over weeks, its accuracy silently erodes — sometimes due to model provider updates, sometimes due to distribution shift in inputs, sometimes due to accumulated tool schema drift. The agent never errors loudly. It just gets worse at the margins, and margins compound.

The canonical benchmark lies by omission: it answers "how good is the agent today?" but never "is it as good as it was last Tuesday?" A Stanford/UC Berkeley study documented GPT-4's accuracy on a specific task dropping from **84% to 51%** between March and June 2023 with no version change communicated. The model alias was identical; the behavior was not. In 2026, production teams report that **91% of deployed AI agents degrade silently** without any observable failure signal until user complaints surface.

This is the agent longevity problem — and it is the modal production failure mode nobody's evaluation suite catches.

## Forces

- **Silent degradation compounds.** Agents don't error on the path to bad; they progressively drift. By the time it's obvious, the gap from baseline is significant and the root cause is buried under weeks of production traffic.
- **Multiple independent drift vectors operate simultaneously.** Model provider updates, input distribution shift, tool schema changes, prompt chain emergent dependencies, and RAG corpus drift all conspire without coordination — and most observability stacks only watch one.
- **Point-in-time evaluation is structurally blind to regression.** A benchmark that runs once at deploy time tells you nothing about what happens between Tuesdays. You need a time-series view of agent quality, not a snapshot.
- **Per-call metrics hide pipeline-level decay.** Individual LLM calls can remain high-quality while the agent pipeline degrades because the degradation is in routing, tool selection, or result synthesis — not in the model's output directly.
- **Context accumulation creates hidden cliffs.** As conversation history grows, agent accuracy follows a non-linear decay curve. The agent works fine in short sessions and fails silently in long ones — exactly the high-value use cases where you need it most.

## The Move

Build longitudinal evaluation infrastructure — a production-grade system that continuously measures agent quality over time, detects change points, and fires alerts before users notice.

### The Four-Column Architecture

**Column 1: Canary Set**
Maintain a fixed, curated evaluation set with known-good inputs and expected outputs. Run it on every significant deployment and on a rolling schedule (at minimum weekly). The set must be:
- Input-stable (hardcoded prompts, not dynamic user data)
- Output-deterministic (ground truth doesn't change with context)
- Covering critical paths (the 10-20% of use cases that drive 80% of business value)

```python
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class CanaryResult:
    canary_id: str
    run_at: datetime
    passed: bool
    latency_ms: float
    output_hash: str  # fingerprint of actual output

# Canonical canary — output hash is the ground truth fingerprint
CANARY_SET = {
    "health_check": {
        "input": {"task": "check_account_status", "account_id": "test_001"},
        "expected_hash": "a3f9b2...",
        "critical": True,
    },
    "refund_approval": {
        "input": {"task": "evaluate_refund", "amount": 47.99, "reason": "defective"},
        "expected_hash": "c7d1e8...",
        "critical": True,
    },
    "escalation_routing": {
        "input": {"task": "route_ticket", "priority": "high", "category": "billing"},
        "expected_hash": "b2a4f1...",
        "critical": False,
    },
}
```

**Column 2: Continuous Shadow Evaluation**
Run production traffic through a shadow agent alongside the live agent. Shadow traffic gets identical inputs but outputs are evaluated against ground truth without affecting real users. Key metrics to track:
- Task completion rate (did the agent finish the task?)
- Output quality score (does the output match expected?)
- Step-level fidelity (did each tool call match expected sequence?)
- Refusal rate (did the agent correctly refuse impossible tasks?)

```python
@dataclass
class ShadowResult:
    trace_id: str
    input_snapshot: dict
    output_quality: float      # 0-1 against ground truth
    completion: bool
    steps_executed: list[str]  # tool call sequence
    refusal_detected: bool
    evaluated_at: datetime

def detect_drift(results: list[ShadowResult], window_days: int = 7) -> dict:
    """Detect statistically significant quality regression within a window."""
    from collections import defaultdict

    cutoff = datetime.utcnow() - timedelta(days=window_days)
    recent = [r for r in results if r.evaluated_at >= cutoff]
    older = [r for r in results if r.evaluated_at < cutoff]

    if len(recent) < 30 or len(older) < 30:
        return {"drift_detected": False, "reason": "insufficient_samples"}

    recent_mean = sum(r.output_quality for r in recent) / len(recent)
    older_mean = sum(r.output_quality for r in older) / len(older)

    # Simple change-point heuristic: alert if recent drops >5% from baseline
    delta = older_mean - recent_mean
    pct_drop = delta / older_mean if older_mean > 0 else 0

    return {
        "drift_detected": pct_drop > 0.05,
        "baseline_quality": older_mean,
        "current_quality": recent_mean,
        "pct_drop": pct_drop,
        "sample_size_recent": len(recent),
        "sample_size_older": len(older),
    }
```

**Column 3: Vendor Update Detection**
Model providers push updates without advance notice. Detect them by hashing outputs from a fixed "canary prompt" submitted to the API at regular intervals. Any change in output hash triggers an alert — even if the change is benign.

```python
CANARY_PROMPT_HASH = None  # Set on first run to establish baseline

def detect_vendor_update(prompt: str, model: str) -> bool:
    global CANARY_PROMPT_HASH
    current_hash = hashlib.sha256(
        call_model(prompt, model).encode()
    ).hexdigest()[:12]

    if CANARY_PROMPT_HASH is None:
        CANARY_PROMPT_HASH = current_hash
        return False

    if current_hash != CANARY_PROMPT_HASH:
        alert(f"Vendor update detected on {model}: {CANARY_PROMPT_HASH} → {current_hash}")
        CANARY_PROMPT_HASH = current_hash
        return True
    return False
```

**Column 4: Change-Point Detection on Quality Signals**
Use statistical change-point detection on rolling quality metrics. Alert when the output distribution shifts significantly — not just when it crosses a threshold, but when its *rate of change* breaks pattern.

```python
from scipy import stats

def rolling_change_point(scores: list[float], window: int = 50) -> float | None:
    """Return the index of detected change point, or None."""
    if len(scores) < window * 2:
        return None
    # CUSUM-like detection on rolling windows
    recent = scores[-window:]
    baseline = scores[-window*2:-window]
    t_stat, p_val = stats.ttest_ind(baseline, recent)
    return len(scores) - window if p_val < 0.01 else None
```

### The Alerting Contract

Don't alert on every dip. Structure alerts on three tiers:

| Tier | Trigger | Action |
|------|---------|--------|
| **Warning** | Quality drops 3-5% vs. 30-day baseline | Log, increase canary frequency |
| **Critical** | Quality drops >5% OR vendor update detected | Page on-call, halt non-critical deployments |
| **Incident** | Quality drops >10% AND affecting critical paths | Rollback consideration, postmortem |

### Context Accumulation Monitoring

Track the relationship between context size and accuracy. Plot the decay curve for your specific agent. If the decay is non-linear (common), set an explicit session-length budget and alert when average context consumption approaches it.

```python
def session_length_health(trace: list[dict], quality_fn) -> dict:
    """Correlate context size with quality within a session."""
    sizes = [len(str(m.get("content", ""))) for m in trace]
    output_quality = quality_fn(trace[-1]["output"])

    return {
        "avg_context_tokens": sum(sizes) / len(sizes),
        "quality": output_quality,
        "context_quality_ratio": output_quality / (sum(sizes) / len(sizes) + 1),
        "cliff_warning": sum(sizes) / len(sizes) > 80_000,  # tunable threshold
    }
```

## Cross-Links

- **S-2333 · The Benchmark Illusion Stack** — Both entries attack the same root failure: trusting point-in-time measurement. Benchmark Illusion is about evaluation validity at deploy time; Silent Regression is about evaluation continuity over time. Together they form the complete evaluation story.
- **S-2335 · The Metacognitive Silence Stack** — Metacognition can mask regression: the agent's self-assessment reports "healthy" while quality silently decays. Both entries are about false confidence in monitoring signals.
- **S-994 · The Agent Evaluation Stack** — The canonical evaluation entry. Silent Regression extends it by adding the temporal dimension that evaluation stacks typically omit.

## Key Pattern

**The Tuesday Problem** — Agents don't announce when they get worse. The window between "still working" and "clearly broken" is measured in weeks, not minutes. Closing it requires measuring quality continuously, not just at deploy time. The fix is not better guardrails; it's a time-series view of agent behavior with statistical change-point detection.

---

**Receipt pending** — 2026-08-08. Code examples are structurally complete; the canary hash values and model API calls are placeholders to be filled with your specific agent's ground truth.
