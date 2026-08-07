# S-2228 · The Reflex Stack: When Your Traces Are Green but Your Agent Is Looping

Your agent ran 50,000 turns last night. OpenTelemetry shows zero errors. LangSmith traces show complete trajectories. Datadog dashboard is green. Then you find that 340 sessions — 4% of total — contained a jailbreak attempt that succeeded silently, an off-task drift that burned 40 minutes of tokens, or a loop that retried the same failed call 17 times before circuit-breaking. The traces captured what happened. Nobody captured what it *meant*. This is the behavioral classification gap: traces answer "was there a span?" but never "was this span behaving?"

## Forces

- **Traces log structure, not semantics.** A 200-OK HTTP response, a tool call that returned the wrong file, and an agent stuck in a retry loop all produce identical trace signatures. Spans tell you the shape of execution; they tell you nothing about correctness, intent, or safety.
- **LLM-as-judge is too slow and expensive for per-turn classification.** Evaluating every production turn with an LLM costs real money and adds latency. Sampling 5% of turns is statistically underpowered for catching rare failure modes.
- **Dashboard health metrics lie by omission.** Error rate, latency, and token spend are infrastructure signals. They measure whether the agent ran, not whether it ran correctly. A jailbroken agent that exfiltrates data logs no errors. A looping agent that burns your budget logs normal-looking spans.
- **Behavioral failures compound silently.** A jailbreak attempt that the agent ignores is a non-event in traces. A jailbreak that succeeds is invisible unless something is watching for the behavioral pattern, not just the structural outcome.

## The Move

Deploy per-turn lightweight text classifiers — called **Reflexes** (Morph) or equivalent inline classifiers — that label each agent turn for behavioral categories in ~90ms with no model overhead. These run alongside tracing, not instead of it. The tracer captures the structure; the Reflex captures the meaning.

### The classification surface

Every turn gets labeled against a set of behavioral risk categories:

| Category | What it catches |
|----------|----------------|
| `jailbreak` | Prompt injection, system-prompt override attempts |
| `off_task` | Turn diverges from stated goal or intent |
| `looping` | Repeated identical or near-identical tool calls |
| `over_refusal` | Agent refuses a legitimate, policy-compliant request |
| `under_refusal` | Agent executes a request that should have been refused |
| `data_leak_risk` | Turn outputs sensitive context or PII inappropriately |
| `tool_misuse` | Tool called with parameters that exceed the task's scope |

### The two deployment modes

**Async trace labeling** (the default): each completed turn is labeled asynchronously. No latency added to the user-facing response. Labels land in the trace as metadata and flow to dashboards and alerting. Catch regressions — if `jailbreak` labels spike from 0.1% to 2% in an hour, page the on-call team.

**Inline blocking** (high-stakes actions): label before the turn proceeds. For destructive actions, sensitive data egress, or requests from untrusted contexts, call `reflex.predict()` synchronously and block/route based on the label. A `data_leak_risk` label on a turn that would exfiltrate session context to an external URL triggers a block + alert before the request completes.

### The production stack

```
User Input → Agent Loop
    ↓
[Turn executes]
    ↓
┌───────────────────────────────────────┐
│ Trace span written (async)            │ ← standard OTel/LangSmith
│ Reflex label computed (async + inline) │ ← lightweight classifier
└───────────────────────────────────────┘
    ↓
Label + trace → Score span in trace store
    ↓
Score span → Dashboard / Alert rule
    ↓
Alert → PagerDuty / Slack (if threshold breached)
    ↓
High-severity label (inline blocked) → Incident created
```

### Alert rules

```python
# Alert if jailbreak attempts spike
jailbreak_rate = jailbreak_labels / total_labels
if jailbreak_rate > 0.005:  # 0.5% threshold
    alert("Jailbreak spike detected", severity="critical")

# Alert if off-task rate exceeds 3%
if off_task_rate > 0.03:
    alert("Agent off-task regression", severity="warning")

# Inline block for destructive actions with risk labels
if action_type == "delete" and tool_misuse.label == "high":
    block_action()
    alert("Tool misuse blocked on destructive action", severity="critical")
```

### The threshold calibration problem

Reflexes are classifiers, not ground truth. False positives cause alert fatigue; false negatives let failures through. Calibrate thresholds against a labeled production sample:

1. Collect 500–1000 real production turns (sampled, human-labeled)
2. Compute precision/recall curves for each category at each confidence threshold
3. Set thresholds per category: precision-critical categories (`data_leak_risk`) → high threshold, high precision tolerance; coverage-critical categories (`off_task`) → lower threshold, accept more false positives
4. Re-calibrate monthly as the classifier encounters new adversarial patterns

## Receipt

> Verified 2026-08-06 — Research from Morph LLM documentation (morphllm.com/docs/sdk/components/reflexes, June 2026) and Morph AI Agent Monitoring guide (morphllm.com/agent-monitoring, June 2026). Morph Reflexes: 11 default classifiers, 65,536 token max input, ~90ms end-to-end latency, async trace labeling + inline blocking modes. Braintrust Score spans (braintrust.dev/docs/evaluate/score-online) implement a similar pattern as scored spans within existing traces. Both patterns represent the emerging "behavioral trace annotation" category distinct from structural tracing. Zylos Research (zylos.ai/en/research/2026-04-29) confirms the epistemological gap: standard APM captures "what happened," Reflex patterns capture "what it meant." Calibrated thresholds require labeled production samples — the 500-1000 turn calibration set is the practical minimum derived from Morph's recommended workflow.

## See also

- [S-1019 · The Three-Pillar Observability Stack](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — traces + metrics + eval as the three pillars; this entry adds behavioral classification as the fourth layer
- [S-1151 · The Behavioral Telemetry Stack](s1151-the-behavioral-telemetry-stack-when-your-agent-returns-200-ok-and-a-wrong-answer.md) — the gap between infrastructure health and behavioral correctness; Reflexes are the operational response
- [S-1004 · The Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — eval-first design and scoring pipelines; Reflexes extend this to per-turn inline evaluation at production scale
