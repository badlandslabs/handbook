# S-951 · The Safety Over-Refusal Regression Stack — When Your Agent Starts Rejecting Legitimate Users

Your agent worked fine on Monday. On Tuesday, your security-research team gets locked out of a legitimate pentest workflow. On Wednesday, a pharmaceutical researcher gets blocked from querying drug-interaction data. On Thursday, a developer gets refused for asking about syscall design. Nobody changed the code. The provider updated the safety classifier. Now your agent is refusing requests it should handle — and you have no idea it's happening because refusals return a 200.

This is **safety over-refusal regression** (also called **false-positive refusal** or **over-refusal**): a distinct failure mode where a provider safety update increases false-positive refusals on legitimate requests, degrading agent reliability without changing the API contract. It is distinct from [S-787](s787-invisible-model-drift-the-silent-provider-update-pattern.md) (general behavioral drift) and [S-839](s839-the-provider-model-drift-stack-when-your-agent-changes-without-you.md) (provider model drift) because the mechanism is specifically safety-classifier tightening — not output quality degradation, not tool-call behavior change, and not schema drift.

## Forces

- **Safety classifiers improve and break things.** Provider safety updates are designed to catch more harmful requests. They do — but they also catch more *legitimate* requests. The false-positive rate is not zero and changes with every update.
- **The 200 OK lies.** Refusals return an API 200 with a refusal message. No error code, no exception. Your error-rate monitoring stays flat. Your uptime dashboard is green. The failure is invisible to every traditional signal.
- **Over-refusal is domain-specific.** A pentest assistant gets hit hard by safety-updates targeting "offensive security" content. A medical researcher gets blocked by content about "dangerous substances." A developer assistant gets flagged for "syscall" or "exploit" terminology. These are the same terms that appear in legitimate professional work.
- **Behavioral regression suites don't test refusals.** [S-220](s220-agentic-behavioral-regression-suite.md) covers behavioral regression testing, but the canonical behavioral suite tests task completion, tool selection, and output format. Refusal rate on benign inputs is rarely in the baseline.
- **The compounding blast radius.** An agent that over-refuses loses user trust faster than one that hallucinates — users notice being told "no" for no reason. [S-200](s200-agent-reliability-compounding.md) applies: each refusal costs user confidence, not just tokens.
- **Provider silence is the norm.** Providers do not announce safety classifier sensitivity changes. [S-787](s787-invisible-model-drift-the-silent-provider-update-pattern.md) covers the general silence problem; the refusal-regression case is its most acute manifestation because the fix (system prompt expansion, request reformulation) is different from output-quality drift.

## The move

Three layers: **Detect → Attribute → Mitigate**.

### Layer 1 — Refusal Rate Monitor (Detect)

Track refusal rate per task type and per user segment, not just overall. The signal is refusal *delta*, not absolute rate.

```python
from collections import defaultdict
from datetime import datetime, timedelta

class RefusalRateMonitor:
    """Monitor refusal rate per task type. Alert on sudden increases."""

    def __init__(self, alert_threshold_pct: float = 5.0):
        self.alert_threshold_pct = alert_threshold_pct
        self.counts = defaultdict(lambda: {"total": 0, "refused": 0})
        self.baseline = {}  # task_type -> baseline refusal rate

    def record(self, task_type: str, response: str, refused: bool) -> None:
        bucket = self.counts[task_type]
        bucket["total"] += 1
        if refused:
            bucket["refused"] += 1

    def check(self, task_type: str) -> dict | None:
        """Return alert if refusal rate increased beyond threshold."""
        bucket = self.counts[task_type]
        if bucket["total"] < 50:
            return None  # not enough data
        current_rate = bucket["refused"] / bucket["total"]
        baseline = self.baseline.get(task_type, current_rate)
        delta = current_rate - baseline
        if delta > self.alert_threshold_pct / 100:
            return {
                "task_type": task_type,
                "baseline_rate": baseline,
                "current_rate": current_rate,
                "delta_pct": delta * 100,
                "total_requests": bucket["total"],
                "action": "INVESTIGATE"
            }
        return None

    def snapshot_baseline(self) -> None:
        """Call after stable operation period to set baseline."""
        for task_type, bucket in self.counts.items():
            if bucket["total"] > 100:
                self.baseline[task_type] = bucket["refused"] / bucket["total"]
```

Detection signal: `RefusalClassification` in the response metadata (Anthropic, OpenAI) or keyword-matching on refusal phrases ("I'm not able to", "I can't help with that", "This request may violate").

### Layer 2 — Attribution (Is It Provider Drift?)

Rule out other causes before declaring a safety update:

| Check | What It Rules Out |
|-------|-------------------|
| Same request succeeds with different phrasing | Prompt sensitivity shift, not provider |
| Same request succeeds on different model | Provider-side classifier change |
| Same request fails across all models | Content genuinely flagged at OS level |
| Other tenants / users see same spike | Shared upstream safety update |

```python
def attribute_refusal_increase(
    task_type: str,
    request: str,
    monitor: RefusalRateMonitor
) -> str:
    """Attribute refusal spike to provider safety update or local cause."""
    alert = monitor.check(task_type)
    if not alert:
        return "NORMAL"

    # Step 1: Check if reformulation succeeds (local prompt sensitivity)
    reformulated = rephrase_for_safety(request)
    if test_with_reformulation(reformulated):
        return "PROMPT_SENSITIVITY"  # not provider drift

    # Step 2: Check if other providers/models handle this request
    results = {
        "openai": test_on_openai(request),
        "anthropic": test_on_anthropic(request),
        "google": test_on_google(request),
    }
    if all(r.refused for r in results.values()):
        return "CONTENT_GENUINELY_FLAGGED"
    if not all(r.refused for r in results.values()):
        return "PROVIDER_SAFETY_UPDATE"  # some providers handle it

    return "UNKNOWN"
```

### Layer 3 — Mitigation Stack

Once attributed to provider safety update, three mitigation tiers in order of invasiveness:

**Tier 1 — System Prompt Expansion (least invasive)**

Establish the legitimate context explicitly. Providers allow operator system prompts to expand the model's understanding of approved use cases:

```
You are assisting [profession]s at [organization] who have verified credentials.
This assistant is used for [specific legitimate purpose]. Users are acting
within their authorized scope. The following topics are legitimate and expected:
- [term A] used in the context of [legitimate use]
- [term B] used in the context of [legitimate use]
```

MindStudio's documentation confirms this is the primary enterprise lever: "A well-crafted system prompt that establishes the deployment context...will shift classifier behavior meaningfully. This isn't a magic override — hard blocks remain hard — but it handles most soft-block friction."

**Tier 2 — Request Reformulation (medium invasive)**

Pre-process requests that are known to trigger false positives:

```python
import hashlib

# Known false-positive trigger terms mapped to reformulation strategies
REFORMULATION_MAP = {
    "syscall": "system call interface (syscall)",
    "exploit": "security vulnerability analysis",
    "pentest": "authorized security assessment",
    "malware": "malware analysis for defensive purposes",
    "ROP chain": "return-oriented programming (defensive research)",
}

def reformulate_request(text: str) -> str:
    for trigger, reformulation in REFORMULATION_MAP.items():
        if trigger in text.lower():
            text = text.lower().replace(trigger, reformulation)
    return text
```

This approach was empirically validated by the arXiv:2605.05427 study: rephrasing alone reduced false-positive refusals by 35-60% on flagged content categories without increasing compliance on genuinely harmful requests.

**Tier 3 — Provider Escalation + Fallback Model (most invasive)**

For Tier 1 and 2 failures — hard blocks that don't respond to context or rephrasing:

1. **File a provider support ticket** with the specific request, response, and timestamp. Reference the GitHub issue on your provider's tracker if a broader issue is confirmed.
2. **Route affected requests to a fallback model** with different safety calibration, while preserving the Tier 1/2 mitigation for the primary model in the long run.
3. **Track the affected user cohort** — over-refusal regressions tend to cluster by professional domain (security researchers, medical professionals, developers) — segment users to understand blast radius.

### The Refusal Regression Dashboard

At minimum, instrument these signals and alert on deltas:

| Signal | Metric | Alert Threshold |
|--------|--------|-----------------|
| Per-task refusal rate | `refused / total` per hour | +5pp vs 7-day baseline |
| Per-user-segment refusal rate | `refused / total` by user cohort | +10pp vs cohort baseline |
| Refusal by content category | breakdown of flagged topics | any new category > 2% |
| Hard block vs soft block ratio | hard_blocks / (hard + soft) | shift > 20% |

## Receipt

> Receipt pending — July 11, 2026
> Code is reference architecture (monitor + attribution + mitigation patterns). Verified: arXiv:2605.05427 (May 30, 2026) documents over-refusal as a measurable, cross-model phenomenon — empirical audit across 21 LLMs on OR-Bench, XSTest, ToxiGen, and BOLD benchmarks. GitHub #66728 (June 10, 2026) documents live Fable 5 false-positive safety refusals on legitimate syscall content. The Register (June 10, 2026) reports Fable 5 blocking "hello!"-level prompts. MIT Technology Review, June 2026 covers provider safety-classifier churn as a top production concern for enterprise agent builders.

## See also

- [S-787 · Invisible Model Drift: The Silent Provider Update Pattern](s787-invisible-model-drift-the-silent-provider-update-pattern.md) — general provider silent update framework
- [S-839 · The Provider Model Drift Stack](s839-the-provider-model-drift-stack-when-your-agent-changes-without-you.md) — when your agent changes without you
- [S-220 · Agentic Behavioral Regression Suite](s220-agentic-behavioral-regression-suite.md) — adding refusal rate to the behavioral baseline
- [S-282 · Agent Guardrails](s282-agent-guardrails.md) — safety architecture at the agent layer
- [F-62 · Handling Model Refusals](f62-handling-model-refusals.md) — handling individual refusal events
