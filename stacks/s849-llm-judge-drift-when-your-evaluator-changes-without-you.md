# S-849 · LLM Judge Drift — When Your Evaluator Changes Without You

Your eval suite turned green. Your regression gate passed. You shipped. Two weeks later, a human reviewer spots that the agent is subtly worse — slower refusals on edge cases, more verbose reasoning traces, a different tone. The eval suite still shows green. The judge changed too.

This is **LLM Judge Drift** — the silent re-calibration of your evaluator model between runs, causing score incomparability without any change to your agent, prompts, or infrastructure. The candidate model and the judge model are two independent moving parts. When the judge migrates, your dashboard lies directionally.

## Forces

- **LLM-as-judge ships two moving models, not one.** The candidate model is what you deploy; the judge model is what tells you whether the candidate is working. When both evolve independently, a score of 4.2 in January and 4.4 in March describe the opinions of two differently-trained judges about two differently-iterated candidates. The number 4.4 is not higher than 4.2 in any longitudinally meaningful sense. (Tian Pan, April 2026)
- **Judge providers migrate silently.** Like model provider drift, evaluation providers update judge models mid-quarter. The judge you pinned to `gpt-4o-mini` last March may be running a different weight snapshot in June. Score deltas across that boundary are confounded by judge migration, not agent improvement.
- **In-family judging inflates scores directionally.** A judge pulled from the same provider family as the candidate tends to report quality improvements that are actually the judge catching up to the candidate's idiom. Out-of-family judges report regressions more accurately — but they're noisier. Both effects are silent without explicit calibration. (Tian Pan, April 2026)
- **The dashboard has no red line at the judge migration boundary.** Traditional APM shows HTTP 200s and latency. It has no signal for "your eval currency just devalued." Scores migrate before the agent does.
- **You can't retroactively fix the comparison.** Once scores from different judge versions are mixed in your time series, you can't un-mix them. The historical record is permanently confounded. Prevention is the only reliable solution.

## The move

**Three layers prevent judge drift from corrupting your eval signal:**

### Layer 1 — Pin the judge with a semantic version boundary

Don't pin `gpt-4o-mini`. Pin `gpt-4o-mini-2026-03-01` or use a provider that supports model snapshots with declared stability windows. On every eval run, log the judge model, version, and a hash of the judge prompt. Any score comparison across a version boundary must be treated as incomparable, not averaged.

```python
JUDGE_PROMPT_HASH = hashlib.sha256(JUDGE_PROMPT.encode()).hexdigest()[:8]
JUDGE_MODEL = "gpt-4o-mini"
JUDGE_VERSION = "2026-06-15"  # provider snapshot date

def run_eval(task: Task, candidate: Agent) -> EvalResult:
    run_record = {
        "candidate_hash": candidate.snapshot(),
        "judge_model": JUDGE_MODEL,
        "judge_version": JUDGE_VERSION,
        "judge_prompt_hash": JUDGE_PROMPT_HASH,
    }
    # If judge_version changed since last run, flag scores as incomparable
    if judge_version != get_baseline_judge_version(task):
        run_record["drift_detected"] = True
        alert_on_call("Judge version changed for task %s", task.id)

    score = judge.evaluate(candidate.run(task))
    run_record["score"] = score
    log_eval_run(run_record)
    return score
```

### Layer 2 — Anchor on a golden trajectory set

Run every judge against a frozen set of 20–50 golden trajectories (expert-validated agent traces) on every eval run. The golden set never changes. Its score trajectory across judge versions becomes your calibration baseline. When the judge's scores on the golden set shift, all other scores from that run are re-calibrated against the shift.

```python
GOLDEN_TRAJECTORIES = load_golden_set()  # frozen, versioned

def calibrate_judge(judge, golden_scores_baseline):
    """Calibrate judge by measuring drift against frozen golden trajectories."""
    current_golden_scores = [judge.evaluate(t) for t in GOLDEN_TRAJECTORIES]
    delta = mean(current_golden_scores) - mean(golden_scores_baseline)
    return delta  # subtract delta from all scores in this run

def run_eval_calibrated(task, candidate):
    drift = calibrate_judge(judge, GOLDEN_BASELINE_SCORES)
    raw_score = judge.evaluate(candidate.run(task))
    calibrated_score = raw_score - drift
    return EvalResult(score=calibrated_score, drift_applied=drift)
```

### Layer 3 — Cross-family judge sanity check

Run a second judge from a different provider family on a 10% sample of tasks. When the two judges disagree directionally on the same task, flag for human review. In-family agreement without out-of-family confirmation is insufficient signal.

```python
IN_FAMILY_JUDGE = "claude-sonnet-4"
CROSS_FAMILY_JUDGE = "gpt-4o-mini-2026-06-15"

def run_with_cross_check(task, candidate):
    score_in = family_judge(IN_FAMILY_JUDGE).evaluate(candidate.run(task))
    score_cross = cross_family_judge(CROSS_FAMILY_JUDGE).evaluate(candidate.run(task))

    if (score_in - score_cross).abs() > 1.5:
        log_sanity_check_failure(task.id, score_in, score_cross)
        # Route to human review instead of auto-pass/fail
        return EvalResult(score=score_in, sanity_check="REVIEW")
    return EvalResult(score=score_in, sanity_check="PASS")
```

## Receipt

> Verified 2026-07-09 — Pattern derived from Tian Pan "LLM-as-Judge Drift" (April 2026, tianpan.co) and Iris "Eval Drift" (March 2026). Layer 1 pattern (provider snapshot pinning) matches practices described in the LLM-as-Judge literature. Layers 2 and 3 (golden trajectory calibration, cross-family sanity check) are operationalized from practitioner reports; not yet run in a live harness. Composite code example is realistic, not run against a live system.

## See also

- [S-202 · LLM-as-Judge Evaluation Harness](s202-llm-as-judge-harness.md) — the broader harness architecture this is a failure mode of
- [S-451 · LLM-as-Judge Failure Modes: The Echo Chamber Problem](s451-llm-as-judge-failure-modes-the-echo-chamber-problem.md) — in-family judging bias (distinct from drift)
- [S-839 · The Provider Model Drift Stack](s839-the-provider-model-drift-stack-when-your-agent-changes-without-you.md) — the candidate-side mirror of this problem
- [S-817 · The Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — testing the path, not just the answer
