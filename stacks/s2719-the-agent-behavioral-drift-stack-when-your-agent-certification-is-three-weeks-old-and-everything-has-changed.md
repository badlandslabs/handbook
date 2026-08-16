# S-2719 · The Agent Behavioral Drift Stack — When Your Agent Certification Is Three Weeks Old and Everything Has Changed

[Your agent was certified for production three weeks ago. 91% success rate, zero critical failures, clean audit trail. Today it silently started approving transactions outside policy boundaries — not because it broke, but because the world around it changed. The model behind the API silently updated. The RAG index was refreshed with slightly different source material. Three tools were updated by a different team. The agent's memory accumulated patterns that shifted its default behavior. Nothing in your observability stack fired. This is the behavioral drift problem: agents change without you changing them.]

## Forces

- **Agents are not software — they are systems.** A certified agent encompasses the model, its instructions, the data it accesses, the tools it calls, its accumulated memories, its permissions, and every other agent it coordinates with. Changing any one of those changes the agent. You didn't ship new code. The agent is nonetheless different.
- **Certification is a snapshot, not a contract.** The 91% you measured three weeks ago was measured against a specific version of everything: a specific model snapshot, a specific tool schema, a specific RAG corpus, a specific memory state. Model providers silently update. RAG indexes refresh. Tools evolve. Each silent change shifts the behavioral surface — and your test suite only knows what it was calibrated to detect.
- **Traditional monitoring watches for failures, not behavioral shifts.** HTTP 200 is not a behavioral signal. Latency is not a behavioral signal. You have dashboards that tell you the agent is up. None of them tell you whether the agent is still making decisions the way it did when you certified it.
- **The agent compounds the problem through use.** Every session adds to the agent's memory. Every batch job refines or pollutes its retrieved context. The agent that was certified three weeks ago had a different memory state. The agent today has absorbed patterns, preferences, and biases from hundreds of interactions that didn't exist during certification.
- **Multi-agent drift is multiplicative.** When agents coordinate, drift in one agent propagates through message passing. An upstream drift becomes a downstream input, which produces more drift. Multi-agent systems don't just accumulate drift — they amplify it. arXiv:2601.04170 (January 2026) documents a 42% reduction in task success rates and 3.2× increase in human intervention requirements over extended multi-agent interactions from unchecked drift.

## The Move

### 1. Establish a Behavioral Baseline at Certification Time

The core insight: you need to know what "the agent behaving correctly" looks like before you can detect that it has changed. This means capturing behavioral fingerprints at certification, not just performance metrics.

Capture at certification:
- **Tool call distribution**: what fraction of tasks call which tools, in what order. A shift in tool call frequency is an early drift signal.
- **Plan structure signature**: the typical length, branching depth, and escalation rate of agent plans for each task type.
- **Output feature vector**: structured properties of the output (field counts, value ranges, format adherence) measured across a representative task corpus.
- **Reasoning trajectory pattern**: the typical depth and style of the agent's reasoning traces — not just correctness, but *how* it reasons.

Store these as a **behavioral baseline** tied to the specific deployment hash (model version + tool schemas + RAG index version + instruction version). Any re-deployment triggers a new baseline.

### 2. Deploy Continuous Behavioral Monitoring Against the Baseline

Run a shadow evaluation suite continuously in production — not blocking traffic, just observing. The shadow suite replays a fixed evaluation corpus against live agent behavior and compares behavioral fingerprints against the baseline:

```
python
def behavioral_drift_score(baseline_fingerprints, current_fingerprints):
    """
    Compare current agent behavior against certification baseline.
    Returns drift_score in [0, 1] — 0 = identical to baseline, 1 = completely drifted.
    """
    drift_scores = {}
    for dimension, (base, current) in align_fingerprints(
        baseline_fingerprints, current_fingerprints
    ).items():
        if dimension == "tool_call_distribution":
            # KL divergence between tool call distributions
            drift_scores[dimension] = kl_divergence(base, current)
        elif dimension == "plan_structure":
            # Cosine similarity of plan structure vectors
            drift_scores[dimension] = 1 - cosine_similarity(base, current)
        elif dimension == "output_features":
            # Earth mover's distance on structured feature distributions
            drift_scores[dimension] = wasserstein_distance(base, current)
        elif dimension == "reasoning_depth":
            # Relative change in mean reasoning trace depth
            drift_scores[dimension] = abs(current["mean_depth"] - base["mean_depth"]) / base["mean_depth"]
        else:
            # Generic normalized distance for other dimensions
            drift_scores[dimension] = normalized_distance(base, current)
    
    # Weighted composite drift score
    weights = {
        "tool_call_distribution": 0.30,
        "plan_structure": 0.25,
        "output_features": 0.25,
        "reasoning_depth": 0.20,
    }
    return sum(weights[d] * drift_scores.get(d, 0) for d in weights)

# Alert threshold: drift > 0.15 triggers investigation
# Critical threshold: drift > 0.30 triggers automatic re-certification gate
```

### 3. Name the Drift Types and Watch Them Separately

Different drift sources have different remedies. BASTYN's taxonomy (May 2026) identifies seven types of agentic drift:

| Drift Type | Trigger | Detection Signal |
|---|---|---|
| **Model Drift** | Provider silently updates the model snapshot | Behavioral fingerprint shift on same inputs, no config change |
| **Context Drift** | RAG index refreshes with shifted source material | Different retrieved context → different answers to same queries |
| **Tool Schema Drift** | Downstream tools update their schemas | Tool call success rate changes, parameter type errors increase |
| **Memory Drift** | Accumulated session memory shifts default behavior | Pattern changes in how the agent starts similar tasks |
| **Permission Drift** | RBAC or permission grants change | Agent attempting calls it previously skipped |
| **Inter-Agent Drift** | Upstream coordinating agents change behavior | Cascade of behavioral shifts in downstream agents |
| **Instruction Drift** | System prompt or instructions updated | Behavioral shifts correlated with prompt deployment timestamps |

Monitor each dimension independently. A total drift score of 0.25 could mean 0.25 on one dimension or 0.05 across five — the response is completely different.

### 4. Build the Re-Certification Trigger

Static re-certification schedules are blunt instruments. Instead, trigger re-certification based on drift:

```
python
DRIFT_INVESTIGATION_THRESHOLD = 0.15
DRIFT_RECERT_GATE_THRESHOLD = 0.30
DRIFT_RATE_SPIKE_THRESHOLD = 0.10  # per-day drift accumulation rate

def should_recertify(drift_score, drift_rate, days_since_cert):
    # Absolute drift threshold
    if drift_score > DRIFT_RECERT_GATE_THRESHOLD:
        return True, "absolute_drift_exceeded"
    
    # Rate-based early warning
    if days_since_cert > 0 and drift_rate > DRIFT_RATE_SPIKE_THRESHOLD:
        projected_drift = drift_rate * 30  # 30-day projection
        if projected_drift > DRIFT_INVESTIGATION_THRESHOLD:
            return True, "drift_rate_projection_exceeded"
    
    # Time-based minimum (re-cert at least every 90 days regardless)
    if days_since_cert > 90:
        return True, "certification_age_exceeded"
    
    return False, None
```

### 5. Treat Drift as an Incident Class

Most teams don't have a process for "the agent is working but behaving differently." Add it to your incident management:

1. **Detect** → Behavioral monitoring fires at DRIFT_INVESTIGATION_THRESHOLD
2. **Classify** → Isolate which drift dimension(s) triggered the alert
3. **Correlate** → Check deployment logs: model version change? RAG index refresh? Tool update?
4. **Decide** → Is the behavioral change acceptable (new capability, improved reasoning) or problematic (degraded policy adherence, shifted outputs)?
5. **Remediate** → If problematic: pin the drifting dimension (model version, RAG snapshot, tool version) and re-run certification against baseline

## Receipt

> Verified — 2026-08-16 — Research synthesis from: arXiv:2601.04170 (Agent Drift paper, Jan 2026 — 847 workflows, 42% success rate drop, 3.2× human intervention increase); BASTYN behavioral drift taxonomy (May 2026); Agnost AI agent drift blog (Jun 2026); Agent Governance Review post-mortem article (Aug 2026). The seven-type drift taxonomy, behavioral fingerprinting approach, and certification-gate design are synthesized from practitioner publications. The code examples are realistic constructs based on documented monitoring patterns.

## See also

- [S-2713 · The Quality Circuit Breaker Stack](s2713-the-quality-circuit-breaker-stack-when-your-agent-looks-healthy-but-is-reasoning-wrong.md) — Real-time quality monitoring that complements behavioral drift detection
- [S-1100 · The Drift Vector Stack](s1100-the-drift-vector-stack-when-your-agent-produces-auditable-outputs-one-run-and-fails-audit-the-next.md) — Output reproducibility and the specific case of deterministic failure
- [R-17 · The Behavioral Regression Detection Stack](r17-the-behavioral-regression-detection-stack-when-your-agent-test-suite-is-green-but-your-users-are-not.md) — The test-suite perspective on behavioral change
