# S-1306 · The Agent-Native CI/CD Stack — When Your Prompt Change Passes CI and Breaks Production

Your agent's last regression came from a prompt wording change made at 11pm. CI passed every test. The agent started truncating API responses mid-sentence in production. Nobody noticed for three days. Traditional CI/CD validates code — it was never designed to validate the *behavioral artifacts* that actually determine how an agent behaves: prompts, model checkpoints, tool definitions, retrieval configs, and guardrails. Agent-native CI/CD adds the gates that catch these failures before users do.

## Forces

- **Code and behavior diverge.** A prompt tweak passes every lint check and unit test while tanking task completion by 20 points in production. The change that broke it looked identical to the change that fixed it — both were text edits.
- **The artifact surface is wider than code.** Agents are shaped by five behavioral artifact types: prompts, model versions, tool schemas, retrieval configs, and guardrails. Each can silently regress behavior. Traditional CI gates none of them.
- **Regression is silent.** Unlike a TypeError that throws, a behavioral regression produces different answers — 200 OK, no errors, wrong outputs. Traditional monitoring misses it. The detection window is days, not seconds.
- **Rollback requires artifact discipline.** Code rollbacks are git revert. Prompt rollbacks need versioning, tagging, and a mechanism to pin the deployed version — none of which exist by default.
- **Eval noise requires statistical rigor.** LLM non-determinism means a regression at small sample sizes can just be variance. Pairwise comparison against the same inputs through old and new is the only reliable signal.

## The move

**1. Version every behavioral artifact.** Store prompts, tool schemas, retrieval configs, and guardrail rules in versioned artifacts (object storage, feature flags, or a dedicated prompt registry). Every deploy pins a specific artifact set. Tag every production deploy with its artifact versions — not just the code SHA.

**2. Build a three-tier eval pipeline.** Each tier trades latency against cost and coverage:

```
Tier 1 — PR (minutes, <$1/run): Fast regression check on golden dataset (50–200 cases).
  Block merge on pass rate ≥ baseline. No new failures in critical paths.
Tier 2 — Nightly (30–60 min, $10–100): Full eval suite + adversarial cases + cost regression.
  Block release candidate if cost-per-task increases >15% or safety score drops.
Tier 3 — Production (continuous): Shadow-mode eval on live traffic.
  Non-blocking. Auto-detect trajectory drift, tool call distribution changes, cost creep.
```

**3. Gate on pairwise trajectory diffs.** Run the same input set through the candidate and baseline simultaneously. Score the diff with an LLM judge comparing trajectory quality (not just final answer). The pairwise approach eliminates variance — you're measuring the change, not absolute performance.

**4. Implement hard rollback triggers.** Define explicit thresholds with no intuition-based overrides:
  - Task completion rate drops >5% in shadow eval
  - Safety/policy violation rate increases >2% 
  - Cost-per-task increases >20%
  - Any critical trajectory pattern (skipped approval step, unauthorized tool call) appears for the first time
  When triggered, pin the artifact version and reroute traffic to the last known-good deploy. Treat prompt rollback as a first-class engineering operation, not a script.

**5. Instrument the pipeline for the Quality Flywheel.** Each production failure caught by the monitoring tier becomes a new eval case: Observe → Diagnose → Add regression test → Commit → Eval. The eval suite grows from real incidents, not synthetic benchmarks.

```python
# Minimal eval gate structure
def eval_gate(candidate_artifacts: dict, baseline_artifacts: dict, golden_set: list[Task]) -> bool:
    baseline_scores = {task.id: score_run(task, baseline_artifacts) for task in golden_set}
    candidate_scores = {task.id: score_run(task, candidate_artifacts) for task in golden_set}

    regression = sum(candidate_scores[k] < baseline_scores[k]
                    for k in golden_set) / len(golden_set)

    critical_regression = any(
        task.is_critical and candidate_scores[task.id] < baseline_scores[task.id]
        for task in golden_set
    )

    return regression < 0.05 and not critical_regression
```

## Receipt

> Verified 2026-07-18 — Core pipeline structure from Zylos Research "Agent-Native CI/CD" (May 2026) and RockB "Agent CI/CD Eval Pipeline Integration Guide" (June 2026). Three-tier eval concept validated across both sources. Pairwise diff approach from Zylos. Hard rollback triggers adapted from TuringPulse "Safe Agent Deployments" (Jun 2026). Prompt versioning and artifact tagging patterns from Luong (Multi-Agent Deep Dive Part 5, Mar 2026) and Cordum "AI Agent Canary Deployment" (Jun 2026). Deduplication: S-1053 covers the eval methodology gap; S-817 covers trajectory eval; S-817 covers what to measure. This entry covers how to gate, promote, and roll back — the pipeline layer. No overlap.

## See also

- [S-1053 · The Evaluation Gap Stack](s1053-the-evaluation-gap-stack-when-your-agent-passes-all-tests-and-still-fails-in-production.md) — the eval gap this pipeline addresses
- [S-817 · The Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — trajectory scoring that feeds the eval gates
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — what to measure, which informs what to gate
