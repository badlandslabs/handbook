# [S-2303] · The Eval Harness Regression Gate — When Your Agent "Passed" Last Week but Got Worse

Your agent scored 94% on your eval suite last Thursday. You shipped the prompt change. Your production refund-approval rate dropped 11 points the following week. The harness said green; the users said red. This is the harness gap: the gap between what your eval measures and what your production agents actually do, and the silent failure mode that makes every automated eval a false promise.

## Forces

- **Harness variance dwarfs model variance.** A 2026 comparison of 11 open-source eval harnesses (RockB, Jun 2026) found identical models on identical task sets producing an **11.5-point score spread** — entirely due to harness design choices. Picking the wrong harness gives you confident wrong answers.
- **Seed noise is the hidden enemy.** ClawBench's bootstrap analysis found **47% of benchmark variance is seed noise** — a 10-point improvement on a single run may be statistical noise, not real progress. Without variance-aware reporting, teams celebrate noise and miss regressions.
- **Trajectories diverge before outputs do.** An agent can reach the correct answer through a broken reasoning path (lucky tool selection, unintended side effects absorbed silently). Outcome-only scoring misses this. Trajectory scoring — measuring the process, not just the result — catches capability decay earlier.
- **CI was built for deterministic code.** A unit test either passes or fails. An agent eval produces a score distribution. Drawing the regression threshold is a judgment call that most teams never make explicitly — until a bad threshold lets a regression ship.
- **Golden trajectories rot.** The reference traces that define "correct" behavior become stale as the world changes (API schemas shift, business rules evolve, user intent distributions drift). An unmaintained golden set is worse than no golden set — it gives false confidence.

## The Move

Build a **golden-trajectory regression gate**: a harness layer between your agent and production that treats behavioral changes as first-class CI events, with variance-aware scoring and trace-level comparison.

### Layer 1 — Fixture Library

Curate a **golden scenario set**: input prompts, expected tool-call sequences, acceptable output schemas, and known failure injection points. Structure each fixture with:

```
task_id: refund-escalation-v3
input: { user_id: "...", amount: 2400, region: "EU" }
expected_trajectory:
  - tool: classify_refund
    args: { amount: 2400, region: EU }
  - tool: check_approval_history
    args: { user_id: "...", lookback_days: 90 }
  - tool: escalate_for_review
    args: { reason: "above-threshold", amount: 2400 }
prohibited_patterns:
  - tool: approve_refund_without_review
    args: { amount: ">1000" }
  - tool: skip_human_review
variance_tolerance: 0.08   # 8% score variance is noise
```

Include **adversarial fixtures**: known injection patterns, permission boundary violations, ambiguous intent cases. These aren't about security — they're about measuring how reliably the agent follows its own constraints.

### Layer 2 — Harness Selection with Variance Reporting

Run each fixture across **5–25 seeds** (ClawBench recommends 25 for high-stakes decisions, 5 for fast feedback loops). Compute:

- **Mean score** — overall pass/fail
- **Variance decomposition** — what fraction of variance is seed noise vs. real behavioral change
- **Trajectory match rate** — fraction of runs where the agent followed the expected tool-call sequence (not just produced the right answer)
- **Tool-call fingerprint** — the specific sequence of tools used, which degrades before outcome quality does (earlier signal)

```bash
openclaw run \
  --harness reaatech \
  --trials 25 \
  --variance-report full \
  --fixtures ./fixtures/refund-escalation-v3.yaml \
  --golden ./golden/refund-escalation-v3.trajectory

# Output includes:
#   score: 0.87 ± 0.04 (CI: [0.83, 0.91])
#   trajectory_match: 0.72
#   variance_source: seed=48%, harness=31%, model=21%
#   REGRESSION DETECTED: trajectory_match dropped from 0.89 → 0.72
```

The **47% seed-noise finding** means: always run ≥5 seeds before declaring a regression or an improvement. One-shot evals are noise.

### Layer 3 — CI Regression Gate

Wire the harness into your CI/CD pipeline as a **blocking gate**, not advisory:

```yaml
# .github/workflows/agent-eval.yml
- name: Agent Regression Gate
  run: |
    openclaw run \
      --fixtures ./fixtures/prod-candidates/ \
      --golden ./golden/ \
      --regression-threshold 0.05  # block on >5% regression
      --variance-aware \
      --output-format junit
  env:
    EVAL_THRESHOLD: BLOCK_ON_REGRESSION
    VARIANCE_TOLERANCE: 0.08
```

The gate fails if:
- Mean score drops by more than the regression threshold, OR
- Trajectory match rate drops, even if mean score is flat (earlier warning), OR
- A prohibited tool pattern appears (any occurrence is a regression)

The trajectory-match trigger catches regressions that outcome-only scoring misses.

### Layer 4 — Golden Set Maintenance

Treat your golden trajectory library as versioned code. Every fixture has a `last_verified` timestamp and a `reviewer` field. Schedule quarterly reviews: re-run the fixture, compare the current trajectory against the stored golden, and update only when the new behavior is the intended behavior.

**Auto-deprecate stale fixtures**: if a fixture hasn't been run against the current harness version in 90 days, flag it as `STALE` — the CI gate skips it and alerts the owner. A stale golden set is a false negative factory.

### Layer 5 — Harness Isolation

Evaluate each agent in an **isolated sandbox** (microVM or container). Running the agent and evaluator in the same environment lets a zero-capability agent tamper with the test harness or claim success through fabricated evidence. Tensorlake microVMs and AWS microVM-based eval platforms (e2b, Daytona) provide the necessary isolation.

## Receipt

> Verified 2026-08-07 — RockB (Jun 2026) benchmark comparison found 11.5-point spread across 11 harnesses on identical task sets. ClawBench's bootstrap analysis confirms 47% of variance is seed noise. reaatech/agent-eval-harness (MIT, TypeScript/pnpm) implements trajectory scoring, golden comparison, CI regression gates, and variance-aware thresholds in production. sebuzdugan/agent-eval-harness (MIT, Jul 2026) demonstrates per-task isolation as a prerequisite for trustworthy evaluation. OpenClaw (OpenClaw, 2026) provides the multi-seed harness with variance reporting used in the CI gate example. The core finding — that harness choice and seed variance dominate model variance in eval results — is confirmed across multiple independent benchmarks (PawBench, ClawBench, MASEval, 2026).

## See also

- [S-1037 · The Evaluation Gap](s1037-the-evaluation-gap-when-your-agent-scores-high-and-fails-in-production.md) — why benchmarks don't predict production behavior
- [S-541 · Agent Drift Detection](s541-agent-drift-detection.md) — behavioral regression detection in production (complementary: this entry is pre-ship, S-541 is post-deploy)
- [S-120 · Agent Telemetry Stack](s120-the-agent-telemetry-stack-when-every-tool-call-logs-but-you-cant-see-agent-reasoning.md) — observability layer that feeds the trajectory data the harness needs
- [S-1005 · AI-SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — treating agent deployments as SLO changes enables the regression-gate mindset
