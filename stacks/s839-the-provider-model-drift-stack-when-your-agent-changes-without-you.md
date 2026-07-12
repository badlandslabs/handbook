# S-839 · The Provider Model Drift Stack — When Your Agent Changes Without You

Your agent was reliable last week. Your users started complaining this week. Nothing changed in your code, your prompts, or your infrastructure. The provider updated the model. The agent is now a different agent, and you didn't know.

This is **provider model drift** — silent behavioral change driven by upstream model updates, deprecations, or migrations that you neither initiated nor observed. Unlike context drift or tool-call drift, provider drift has no trigger inside your codebase. The dashboard is green. The error rate is flat. The agent is quietly worse.

## Forces

- **"The same service" changes.** Anthropic removes model version pinning, OpenAI patches "stable" versions mid-quarter, and Google sunsets model variants on aggressive schedules. Stanford HAI AI Index 2026 documents behavioral inconsistencies within supposedly-stable model versions. Your pinned deployment is a moving target. (Tian Pan, Apr 2026; FutureStackDev, May 2026)

- **Standard observability misses behavioral drift.** Uptime is green, latency is flat, error rates are unchanged — the agent still returns 200s, still calls tools, still produces valid JSON. The failure is invisible to every metric your dashboard tracks. (FutureStackDev, May 2026; AI Mad Tools, Apr 2026)

- **Drift compounds non-linearly in agentic chains.** A 5% regression in tool selection rate, combined with a 3% regression in refusal behavior and a 2% regression in output format, compounds across multi-step agent workflows. The Stanford longitudinal study documents 10–14 day degradation windows before visible failures surface. (Stanford HAI AI Index, 2026)

- **Forced migrations on deprecation have no grace period.** OpenAI's deprecation schedule sweeps legacy GPT-4o and o4-mini variants through Q2 2026. Once the retirement date lands, every request to the deprecated model fails — and the replacement model has different behavioral characteristics. (Tian Pan, Apr 2026)

- **Version pinning is a false guarantee.** Teams that pin model versions assume "the same model" is the same agent. The provider's internal updates to a pinned version can shift tool-selection preferences, refusal patterns, or reasoning depth without announcement. (Prefactor, May 2026)

## The move

### 1. Pin behavioral anchors, not just versions

Model version strings are insufficient. Capture a behavioral fingerprint at deployment time:

```python
# At deployment: capture behavioral baseline
BEHAVIORAL_BASELINE = {
    "tool_selection_rate": run_eval_probe(TOOL_SELECTION_SET),
    "refusal_rate": run_eval_probe(REFUSAL_SET),
    "output_format_accuracy": run_eval_probe(FORMAT_SET),
    "reasoning_depth": run_eval_probe(REASONING_SET),
}

# Store alongside model version in deployment manifest
manifest = {
    "model": "claude-sonnet-4-5",
    "provider_version": "stable-2026-06",
    "behavioral_baseline": BEHAVIORAL_BASELINE,
    "baseline_captured_at": timestamp,
}
```

The baseline is your ground truth. Re-run it on every provider announcement or schedule.

### 2. Build a provider-change detection layer

Three signal sources, none inside your code:

- **Provider announcement feeds** — subscribe to OpenAI model deprecation notices, Anthropic version changelogs, Google Vertex release notes. Parse programmatically, not manually.
- **Synthetic probe rerun** — on a fixed evaluation set, run the same agent against the same input daily. Track pass rate on a narrow behavioral probe (tool selection accuracy, refusal behavior, format compliance). A >2σ shift on any dimension is a drift signal.
- **Production canary window** — route 1–5% of real traffic through a mirrored evaluation pipeline after any provider change. Compare outcomes against the pre-change baseline.

### 3. Respond in three phases

**Detect (T+0):** Automated alert when behavioral probe score shifts by >2σ from baseline, or when provider changelog matches your pinned model.

**Isolate (T+1hr):** Pin to the previous version if available; fall back to a known-good model. Route high-stakes traffic away from the drifting version. This is why behavioral baselines must be captured before drift hits — you need something to compare against.

**Re-evaluate (T+24hr):** Run full agentic behavioral regression suite (S-220) against the new version. Update behavioral baseline if the new behavior is acceptable. If not, file a provider ticket and hold on the new version.

### 4. Treat provider updates like dependency updates

```yaml
# agent-deployment.yaml — model as a versioned dependency
dependencies:
  model:
    provider: anthropic
    model: claude-sonnet-4-5
    pin: hash-of-known-good-checkpoint  # not just version string
    behavioral-baseline-sha: <captured-on-last-good-deployment>

update_policy:
  auto_accept_patches: false  # always evaluate before switching
  fallback_model: claude-sonnet-4
  evaluation_gate: behavioral_probe_score_delta < 0.05
```

Model providers should be in your dependency management workflow the same way library versions are — with pinning, changelog monitoring, and staged rollout.

### 5. Instrument what actually matters for drift detection

The minimum viable drift telemetry layer:

| Signal | What it catches | Threshold |
|--------|----------------|-----------|
| `tool_selection_rate` | Agent now picks different tools for same intent | Δ > 2σ |
| `refusal_rate` | Agent suddenly refusing more queries | Δ > 1σ |
| `output_format_accuracy` | JSON validity or schema compliance drops | < 99% |
| `avg_token_per_response` | Reasoning verbosity shifted (prompt injection or drift indicator) | Δ > 20% |
| `cost_per_task` | Token volume change per task type | Δ > 10% |

## Receipt

> Verified 2026-07-09 — Research sourced from: Tian Pan "Invisible Model Drift" (Apr 19, 2026), FutureStackDev "Silent Degradation" (May 2026), Benchmarking Agents Vol. III (Apr 2026), Prefactor "Prevent Model Drift in Agents" (May 2026), AI Mad Tools "AI Model Drift Detection" (Apr 2026), Stanford HAI AI Index 2026. Handbook gap confirmed: no existing entry covers provider-side behavioral drift as a distinct failure category. Complements S-220 (behavioral regression CI), S-206 (context debt), S-209 (production observability), and S-838 (agent orchestration).

## See also

- [S-220 · Agentic Behavioral Regression Suite](s220-agentic-behavioral-regression-suite.md) — CI-based behavioral regression detection
- [S-206 · Context Debt](s206-context-debt.md) — the silent gap between agent inference and business meaning
- [S-209 · Agent Production Observability](s209-agent-production-observability.md) — telemetry that catches what dashboards miss
- [S-807 · The Confidence Gap](s807-the-confidence-gap-when-agents-say-i-dont-know-then-act-anyway.md) — calibrated epistemic signals in agent output
