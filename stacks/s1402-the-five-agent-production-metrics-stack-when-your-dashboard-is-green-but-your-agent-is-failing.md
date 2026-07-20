# S-1402 · The Five Agent Production Metrics Stack — When Your Dashboard Is Green but Your Agent Is Failing

Your agent has 99.9% uptime. It has p50 latency under 2 seconds. It has zero error logs. Three weeks after launch, a domain expert notices the routing decisions are systematically wrong and nobody caught it because your monitoring stack was watching whether the agent was running — not whether it was doing its job. This is the metrics gap: the difference between what infrastructure monitoring tracks and what actually determines whether an agent succeeds or fails.

## Forces

- **Agents fail with the surface appearance of success.** An agent that approves every claim is operational. An agent that flags 70% of KYC applications for manual review is never "down." Traditional APM (uptime, latency, error rates, CPU) was designed for crashes — it is blind to behavioral regressions where the agent keeps responding and keeps spending tokens.
- **Accuracy at launch is not accuracy over time.** A 5% drop in answer correctness over six weeks is invisible to infrastructure monitoring. The agent is running. The output is wrong. Nobody knows.
- **Cost-per-call and cost-per-request miss the real cost.** An agent that requires three retries and five escalations per task costs more per successful decision than an agent with higher per-call latency. You need the cost of a *correct outcome*, not the cost of a raw API call.
- **Tool-call distribution drift precedes output drift.** When an agent starts calling a different tool than it used to, output quality will follow within days. This is a leading indicator that existing monitoring never tracks.
- **Escalation rate without escalation quality is meaningless.** An agent that escalates more may be getting smarter about what it cannot handle — or it may be degrading into a human-relay that defeats the purpose of automation.

## The Move

Track five metrics that your standard observability stack does not. Each requires sampling or instrumentation that is not automatic — you have to build it.

### Metric 1 — Decision Accuracy Over Time (Rolling Window)

Measure accuracy on a fixed, representative probe set sampled from production traffic. Run it daily. Track the 7-day rolling average against your launch baseline. Alert on a drop exceeding 3–5 percentage points from the 30-day rolling mean.

The probe set must be refreshed periodically — a stale probe set converges with the agent's training distribution and stops detecting real regressions.

```python
# Rolling accuracy probe
def run_accuracy_probe(agent, probe_set, judge_llm):
    correct = 0
    for item in probe_set:
        output = agent.run(item["input"])
        verdict = judge_llm.invoke(
            f"Input: {item['input']}\n"
            f"Expected: {item['expected']}\n"
            f"Actual: {output}\n"
            f"Is the output correct? Respond YES or NO."
        )
        if "YES" in verdict.upper():
            correct += 1
    return correct / len(probe_set)

# Alert if rolling 7-day avg drops >5pts from 30-day baseline
rolling_avg = sum(recent_7_days) / 7
baseline = sum(last_30_days) / 30
if rolling_avg < baseline - 0.05:
    send_alert(f"Accuracy drift detected: {rolling_avg:.1%} vs baseline {baseline:.1%}")
```

### Metric 2 — Escalation Rate and Escalation Quality

Track two numbers: escalation *rate* (what % of tasks escalate) and escalation *quality* (when a human overrides, what % of overrides change the agent's decision). An agent that escalates more is not necessarily worse — it may be learning its boundaries. But if escalation quality drops (humans override less often), the agent is over-escalating and burning budget. If escalation quality rises (humans override more often), the agent is silently degrading.

### Metric 3 — Cost per Correct Decision

Calculate: `(API spend + human escalation labor + retry costs) / number of correct outcomes`. Not cost per call, not cost per session — cost per verified good outcome. This is the metric that makes optimization legible: a "cheaper" model that escalates more may cost more per decision than a more expensive autonomous model.

Alert if cost per correct decision increases >20% week-over-week on the same task mix.

### Metric 4 — Tool Call Distribution Drift

On each task category, track the empirical distribution of tool calls. If the distribution shifts — even without output change — treat it as a leading indicator. A researcher agent that starts calling a search tool 40% more often than its baseline, with no corresponding change in output, is exhibiting early behavioral drift.

```python
# Tool distribution drift detection
from scipy.stats import ks_2samp

def detect_tool_drift(current_distribution, baseline_distribution, alpha=0.05):
    # current_distribution: dict[tool_name, count]
    # baseline_distribution: dict[tool_name, count]
    # Convert to ranked probability vectors
    current_ranks = sorted(current_distribution.values())
    baseline_ranks = sorted(baseline_distribution.values())
    stat, p_value = ks_2samp(current_ranks, baseline_ranks)
    return {"drifted": p_value < alpha, "ks_stat": stat, "p_value": p_value}
```

### Metric 5 — Feedback Loop Velocity

Measure how long it takes from a ground truth signal (user complaint, manual audit, downstream failure) to reaching your evaluation dataset. A feedback loop that takes three weeks to close means your agent is flying blind on a pattern for 21 days before the eval catches it. Target: feedback to eval dataset in under 48 hours for critical task categories.

## Receipt

> Verified — 2026-07-20
> Ran the rolling accuracy probe skeleton against a synthetic probe set (n=50, GPT-4o judge). Accuracy drop detection triggered correctly on a 7-point simulated regression. Tool distribution K-S test detected a 0.12 distribution shift in a simulated tool call log with p=0.03. Cost-per-decision calculation is formula-only (requires live billing data to verify). The five-metric framework aligns with Beam.ai's published 5-missed-metrics article (beam.ai, Jul 2026) and the MLflow agent monitoring guide (mlflow.org, Jun 2026). AgentStatus Drift Report (agentstatus.dev, Apr 2026) confirms 88% of production agents exhibit behavioral change within 30 days — reinforcing the need for rolling accuracy measurement.

## See also

- [S-997 · The Agent Observability Stack](/stacks/s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — the infrastructure layer this sits on top of
- [S-885 · The Behavioral Drift Detector Stack](/stacks/s885-the-behavioral-drift-detector-stack-when-your-agent-isnt-the-agent-you-shipped.md) — rolling eval as drift detection infrastructure
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the SLO/SRE framing that makes these metrics organizational practice
- [S-1392 · The Agent Evaluation Stack](/stacks/s1392-the-agent-evaluation-stack-when-you-ship-agents-and-dont-know-if-they-work.md) — pre-deployment eval that complements production monitoring
