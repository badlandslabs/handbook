# S-934 · The Eval Rubric Coupling Problem — When Your Grading Rubric Ages Faster Than Your Agent

Your agent's prompt just shipped its 14th version. Your eval suite still scores 91% — same as v1. You treat this as evidence the agent is stable. You are wrong. The rubric was written for v1. It has been grading v1's behavior on v14's agent for three months. Scores compute. Dashboard is green. The signal is noise.

## Forces

- **Rubrics are snapshots, not specifications.** A grading rubric encodes a set of criteria at a point in time — the behaviors you thought mattered, the failure modes you had seen, the output shapes you expected. When the agent changes (prompt edit, model swap, new tools), the rubric's criteria drift from reality without any version bump or warning.
- **Score changes are uninterpretable without rubric version context.** Prompt changed, rubric unchanged, score dropped 3 points. Did the agent degrade, or did the rubric's "correct answer" become less correct? You cannot know without versioning both. Teams that skip rubric versioning end up with 91% scores that mean nothing.
- **Rubric coupling hides semantic drift in the scoring dimension.** A rubric written for v3 may include a dimension that was a pain point then but is irrelevant at v14. The agent scores high on that dimension, but it measures nothing real. Conversely, a failure mode that emerged at v10 has no rubric coverage — it can't be caught because it can't be scored.
- **LLM-as-judge rubrics compound the coupling.** When the judge model changes, the rubric's implied grading standard changes with it. A rubric written for GPT-4's judgment characteristics, evaluated by Claude, produces structurally different score distributions — even when the criteria text is identical. The rubric and the judge are coupled; changing one without re-anchoring the other produces uncalibrated scores.
- **The rubric is treated as infrastructure; it should be treated as code.** Prompts are versioned because they visibly break. Rubrics are not versioned because they silently drift. This asymmetry creates a class of production incidents that have no detection signal until customers complain.

## The move

Treat the eval rubric as a first-class, versioned artifact — as coupled to the agent as the prompt itself.

### 1. Version the rubric alongside the agent

```yaml
# eval_bundle/v14/
agent_prompt.yaml    # the agent's system prompt (v14)
eval_rubric.yaml     # the grading rubric (v14)
judge_config.yaml    # which model judges, at what temp
eval_set.yaml        # which test cases, versioned
```

Score comparisons are only valid within the same rubric version. Any rubric change bumps the minor version. Any agent prompt change bumps the patch version. When you see a score delta across rubric versions, decompose it: how much came from the rubric criterion change, how much from the agent?

### 2. Tag every eval output with rubric metadata

```python
eval_result = {
    "agent_version": "v14.2",
    "rubric_version": "v14",
    "judge_model": "claude-sonnet-4-20250514",
    "scores": {"accuracy": 0.87, "tool_use": 0.91, "safety": 0.93},
    "rubric_score_hash": "sha256:abc123",  # prevents silent rubric edits
}

# Score comparison is only valid when rubric_version AND rubric_score_hash match
```

The hash prevents the silent rubric edit problem: someone tweaks a criterion in the rubric file without bumping the version number. The hash breaks the comparison.

### 3. Anchor the rubric against a reference grade set

Maintain 10-20 cases with known-correct grades — not known-correct *answers*, but known-correct *grades* under the current rubric. Run the rubric against the reference set. If the rubric's own grades for the reference set drift by more than ±0.02 on any dimension, flag the rubric as needing re-anchoring before using it for scoring.

```python
def validate_rubric(rubric_version: str, reference_cases: list[dict]) -> bool:
    """Re-anchor: rubric grades reference cases, check stability."""
    for case in reference_cases:
        expected = case["anchored_grade"]
        actual = grade_with_rubric(rubric_version, case["input"])
        if abs(actual - expected) > 0.02:
            raise RubricDriftError(
                f"Rubric {rubric_version} drifted on case {case['id']}: "
                f"expected {expected}, got {actual:.2f}"
            )
    return True
```

This catches rubric drift the way eval catches agent drift: automatically, in CI, before the bad rubric ships.

### 4. Decompose score changes into agent vs. rubric contribution

When a score changes after a prompt or model update, run two evals: one with the new agent + old rubric (isolate agent effect), one with new agent + new rubric (isolate rubric effect).

```
Score delta = f(agent_change) + f(rubric_change) + f(judge_change)
```

Without this decomposition, you can't tell if your agent got 3 points better or your rubric got 3 points easier. Both look identical in the dashboard.

### 5. Treat judge model changes as rubric invalidation events

A rubric written for `gpt-4-turbo` may not transfer directly to `claude-sonnet-4` or `gemini-2.5-pro` — the models have different leniency profiles, different sensitivity to formatting, and different threshold calibration for multi-dimensional scoring. When the judge model changes, re-anchor the rubric by running it against the reference grade set with the new judge and adjusting criterion thresholds until the reference grades match.

## Receipt

> Verified 2026-07-11 — Concept validated against research: futureagi.com (Apr 2026, "six drift modes"), tianpan.co (Apr 2026, "Agent SLOs Without Ground Truth"), Maxim AI (2026 prompt versioning guide), AgentMode (AM-137, May 2026), Suhas Bhairav blog (May 2026). No code example was executed; the above patterns are synthesized from documented production practices across multiple sources.

## See also

- [S-385 · Agent Trajectory Evaluation](stacks/s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — rubric dimensions and process-vs-outcome scoring; S-934 extends this by versioning the rubric itself
- [S-901 · The Golden Set Trap](stacks/s901-the-golden-set-trap-when-your-eval-suite-gives-you-confidence-you-havent-earned.md) — eval set coverage and the confidence illusion; rubric coupling is the complementary problem on the grading side
- [S-825 · The Trace-Eval Gap Stack](stacks/s825-the-trace-eval-gap-stack-knowing-when-your-agent-is-lying-to-you.md) — eval sets freeze while production drifts; rubric coupling is the second drift axis (grading criteria drift independently from test cases)
- [S-532 · The Six Agent SLOs](stacks/s532-the-six-agent-slos.md) — six-layer SLO stacking; rubric coupling affects the eval-validation layer specifically
