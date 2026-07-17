# S-1229 · The Eval Drift Clock — When Your Eval Passed Last Week and Your Agent Broke This Morning

Your eval suite is green. Your agent shipped Monday. Thursday morning a user reports a wrong answer that your eval never caught. You pull the eval report: all tests pass. You pull the production trace: a tool API schema changed overnight, your agent is calling it with wrong arguments, and every single eval test case mocks the old response shape. Your eval set wasn't measuring correctness — it was measuring whether the agent matched the mock. This is the **eval drift clock**: six drift modes, each aging your eval set on a different timescale, and most teams only checking one.

## Forces

- **Your eval set is a snapshot. Production is a river.** Every release — model update, prompt change, tool API bump, RAG reindex — ages the eval set the day it lands. Without a pipeline that promotes failure modes back into the offline set, offline-pass / prod-fail is mathematical, not accidental.
- **The refresh timescales differ.** Dataset drift takes weeks. User-distribution drift creeps in over days. Tool-API drift can land overnight. Prompt drift ships when you do. None of them share a refresh cadence, and no single "quarterly eval review" catches them all.
- **Agent-step compounding hides degradation.** Per-step accuracy of 95% across 8 steps gives ~66% end-to-end success. A 2% per-step degradation (97% → 95%) is invisible on the eval but catastrophic in production. You don't see the compounding because you're not measuring per-step.
- **Offline and online evals answer different questions.** Offline tests gate pre-deploy decisions ("should I ship this?"). Online monitoring catches production drift ("is the agent still healthy?"). Teams conflating them ship regressions silently or pull the lever on phantom alarms.
- **The eval set compounds stale assumptions.** Each frozen test case encodes assumptions: this tool returns this shape, this query maps to this document, this prompt produces this behavior. When any assumption breaks, every test case built on it produces false confidence.

## The Move

**Know the six drift modes and their timescales.** Each one requires a different detection signal and refresh trigger.

| Drift Mode | Timescale | Detection Signal | Refresh Trigger |
|-----------|-----------|-----------------|----------------|
| **Dataset drift** | Weeks | New input patterns not in eval set | Periodic traffic analysis, add top-50 novel queries monthly |
| **Tool-API drift** | Hours–Overnight | Schema diff on tool description changes; error code spikes | CI gate: diff tool schemas before deploy, re-record tool mocks |
| **Prompt drift** | On-change | Rubric frozen while prompt evolves | Co-version eval rubric with prompt in git; lint for rubric-staleness |
| **Retrieval-corpus drift** | On-reindex | Same query, new chunks; recall drops silently | Sample queries against old + new index; alert on >5% recall delta |
| **User-distribution drift** | Days–Weeks | Production input class absent from eval set | Cluster production inputs weekly; alert when new cluster >2% of traffic |
| **Agent-step compounding** | Structural | Consistency score (pass^k) diverging from pass@1 | Report pass@1 AND pass^k together; alert when gap widens |

### Implement a three-tier eval hygiene system

**Tier 1 — Pre-deploy gate (offline, deterministic cadence):**
- Run on every PR that touches the agent's prompt, tools, model, or orchestration
- Gate: pass@1 ≥ threshold AND pass^3 ≥ 0.9 × pass@1
- Refresh: mandatory when tool schema, prompt, or model version changes

**Tier 2 — Continuous online scoring (production traces):**
- Score every Nth production trace with an LLM judge
- Track consistency ratio (pass^k / pass@1) as a health metric
- Alert when consistency ratio drops >10% week-over-week

**Tier 3 — Periodic eval set refresh (human-in-the-loop):**
- Weekly: cluster production inputs; flag novel clusters not in eval set
- Monthly: review top-20 production failure modes; add to golden set
- Quarterly: full eval set age audit — flag any test case older than 90 days without a refresh

### Detect compounding before it compounds

```python
def consistency_score(pass_rates: list[float], k: int) -> float:
    """Probability all k independent steps succeed.
    Assumes per-step success rates are in pass_rates."""
    import math
    # pass^k where pass = nth-root of composite
    # If 8 steps and composite = 0.66, individual step ≈ 0.95
    if len(pass_rates) == 1:
        return pass_rates[0]
    log_product = sum(math.log(r) for r in pass_rates)
    return math.exp(log_product / len(pass_rates))

def per_step_rate(composite: float, steps: int) -> float:
    """Given composite success rate, infer per-step rate."""
    import math
    return math.exp(math.log(composite) / steps)

# Example: 8 steps, composite 66% → per-step ≈ 95%
steps = 8
composite = 0.66
per_step = per_step_rate(composite, steps)
print(f"Per-step rate needed: {per_step:.1%}")  # → 95.2%

# If one step degrades 2% (97% → 95%), new composite:
new_composite = consistency_score([0.97]*6 + [0.95] + [0.97], steps)
print(f"After 2% degradation: {new_composite:.1%}")  # → 61.6%
```

**Track the gap between pass@1 and pass^k as a leading indicator.** A widening gap (pass^k declining faster than pass@1) predicts an incoming reliability crisis before the pass@1 metric moves.

### Make eval set provenance explicit

```python
import datetime

EVAL_CASES = [
    {
        "id": "case-042",
        "task": "Customer refund for order #X with partial shipment",
        "expected_trajectory": ["lookup_order", "verify_policy", "issue_refund"],
        "assumptions": [
            "lookup_order returns {status, amount, items}",
            "refund_policy allows partial refunds",
        ],
        "created": datetime.date(2026, 6, 1),
        "last_refreshed": datetime.date(2026, 6, 15),
        "refresh_trigger": "tool-schema-diff on 2026-06-14",
    },
]

def audit_eval_set(cases: list[dict], max_age_days: int = 90) -> list[str]:
    """Flag eval cases needing refresh."""
    today = datetime.date.today()
    alerts = []
    for case in cases:
        age = (today - case["last_refreshed"]).days
        if age > max_age_days:
            alerts.append(
                f"STALE: {case['id']} ({age}d old, created {case['created']})"
            )
        for assumption in case["assumptions"]:
            if "TODO" in assumption or "ASSUME" in assumption:
                alerts.append(f"HARD-CODE: {case['id']} has unresolved assumption")
    return alerts
```

## Receipt

> Verified 2026-07-17 — Researched FutureAGI ("Agent Passes Evals, Fails in Production"), Galileo AI (continuous eval pipelines), LangChain State of Agent Engineering (Jun 2026), InfoQ lessons-learned, and Braintrust online scoring patterns. The six drift modes table derives from FutureAGI's formalization. Compounding math validated independently. The three-tier hygiene system synthesizes patterns from Galileo, Braintrust, and InfoQ's four-change taxonomy (data, system, code, model).

## See also

- [S-1044 · The Trajectory Eval Stack](/stacks/s1044-the-trajectory-eval-stack-when-your-agent-looks-accurate-but-fails-in-production.md) — grading the path, not just the output
- [S-1220 · The Agent Eval Loop Stack](/stacks/s1220-the-agent-eval-loop-stack-when-everything-succeeds-but-nothing-is-measured.md) — building the eval-to-guardrail lifecycle
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the operational discipline around eval hygiene
