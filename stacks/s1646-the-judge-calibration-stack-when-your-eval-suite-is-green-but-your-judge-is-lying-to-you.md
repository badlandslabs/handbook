# S-1646 · The Judge Calibration Stack — When Your Eval Suite Is Green but Your Judge Is Lying to You

Your LLM-as-judge pipeline gives you 81% pass rates. Your production agent is actually failing 40% of requests. You didn't catch it because the judge was the thing evaluating the judge — and the judge has a position bias. It consistently rates whichever answer appears in slot A higher, regardless of quality. Your eval was never measuring agent quality. It was measuring slot assignment.

## Forces

- **LLM-as-judge became the default without meta-evaluation.** Zheng et al. 2023 showed GPT-4 agrees with humans 80% of the time. That finding made automated eval mainstream. What it didn't surface: the failure cases aren't random — they're systematic, exploitable, and invisible without deliberate probing.
- **Raw accuracy hides the bias distribution.** 80% agreement on average means 20% systematic disagreement. In high-stakes eval pipelines, that 20% is where capability regressions slip through and bad agents get shipped.
- **Agents optimize for judges, not for quality.** Once a model learns that longer responses score higher with a verbosity-biased judge, the agent starts padding. The eval suite signals improvement. The actual agent got worse.
- **Cross-lingual eval is the blind spot.** Most production agents operate in multilingual contexts. Judges degrade sharply in lower-resource languages. You won't know unless you specifically test for it.

## The move

### The Four Systematic Biases (BabelJudge, KC 2026)

**1. Position bias.** Judges favor whichever response appears first (slot A) or last (slot B). In pairwise comparison, the same answer can score 30% higher depending on its slot assignment. Mitigation: run all pairs in both orders, average the scores.

**2. Verbosity bias.** Judges prefer longer responses regardless of quality. A verbose but incorrect answer consistently outscores a concise correct one. Mitigation: normalize for length; use pairwise with explicit length constraints; add a "length penalty" term to scoring.

**3. Order inconsistency.** A judge that prefers A over B in one run may prefer B over A in another, even with identical prompts. The same judge on the same inputs produces different rankings. Mitigation: run each judgment 3-5 times with temperature variations; discard judges with >15% inconsistency rate.

**4. Cross-lingual degradation.** Judges trained on English perform dramatically worse on Swahili, Vietnamese, or Bengali. Evaluation scores in non-English languages are not comparable to English scores — they're measuring a different task. Mitigation: use language-specific judges; never cross-compare scores across languages.

### The Judge Calibration Protocol

```
```python
import anthropic
from collections import Counter

JUDGE_MODEL = "claude-opus-4-6"
BIAS_AUDIT_PAIRS = 50  # Minimum for reliable bias estimation

def bias_audit(judge_model: str, test_pairs: list) -> dict:
    """
    Run BabelJudge-style bias audit on an LLM judge.
    Returns position_bias, verbosity_bias, order_inconsistency, cross_lingual_score.
    """
    client = anthropic.Anthropic()

    results = {"position_bias": 0.0, "verbosity_bias": 0.0, "order_inconsistency": 0.0}

    # 1. Position bias: run each pair in both orders
    position_flips = 0
    for pair in test_pairs[:BIAS_AUDIT_PAIRS]:
        # Forward: A first, B second
        forward = client.messages.create(
            model=judge_model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Which response is better? Consider accuracy, clarity, and completeness.\n\n"
                           f"Response A:\n{pair['a']}\n\nResponse B:\n{pair['b']}"
            }]
        )
        forward_winner = extract_winner(forward.content)

        # Reverse: B first, A second
        reverse = client.messages.create(
            model=judge_model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Which response is better? Consider accuracy, clarity, and completeness.\n\n"
                           f"Response B:\n{pair['b']}\n\nResponse A:\n{pair['a']}"
            }]
        )
        reverse_winner = extract_winner(reverse.content)

        # Inconsistent if the winner changes with order
        if forward_winner != reverse_winner:
            position_flips += 1

    results["position_bias"] = position_flips / len(test_pairs[:BIAS_AUDIT_PAIRS])

    # 2. Verbosity bias: pair verbose-wrong against concise-correct
    verbosity_wins_verbose = 0
    for pair in test_pairs[:BIAS_AUDIT_PAIRS]:
        verdict = client.messages.create(
            model=judge_model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"Which response is better? Score based on factual correctness only.\n\n"
                           f"Concise (correct):\n{pair['concise']}\n\nVerbose (incorrect):\n{pair['verbose']}"
            }]
        )
        if "verbose" in verdict.content.lower() or "b" in verdict.content.lower():
            verbosity_wins_verbose += 1

    results["verbosity_bias"] = verbosity_wins_verbose / len(test_pairs[:BIAS_AUDIT_PAIRS])

    # 3. Order inconsistency: rerun same judgment with temperature=1.0
    reruns = 3
    rerun_flips = 0
    for pair in test_pairs[:20]:
        outcomes = []
        for _ in range(reruns):
            r = client.messages.create(
                model=judge_model,
                max_tokens=256,
                temperature=1.0,
                messages=[{
                    "role": "user",
                    "content": f"Which response is better?\n\nA:\n{pair['a']}\n\nB:\n{pair['b']}"
                }]
            )
            outcomes.append(extract_winner(r))
        if len(set(outcomes)) > 1:
            rerun_flips += 1

    results["order_inconsistency"] = rerun_flips / 20

    return results

def extract_winner(response_text: str) -> str:
    """Parse judge output to extract winner. Be lenient — judges don't always format cleanly."""
    text = response_text.lower()
    if "a is better" in text or "response a" in text[:100]:
        return "A"
    if "b is better" in text or "response b" in text[:100]:
        return "B"
    # Fallback: first mentioned response letter
    for char in ["a", "b"]:
        if char in text[:20]:
            return char.upper()
    return "UNKNOWN"

# Audit your judge before using it in production
bias_results = bias_audit(JUDGE_MODEL, eval_pairs)
print(f"Position bias: {bias_results['position_bias']:.1%} (threshold: <15%)")
print(f"Verbosity bias: {bias_results['verbosity_bias']:.1%} (threshold: <20%)")
print(f"Order inconsistency: {bias_results['order_inconsistency']:.1%} (threshold: <15%)")

REJECT_THRESHOLDS = {
    "position_bias": 0.15,
    "verbosity_bias": 0.20,
    "order_inconsistency": 0.15,
}

for bias, rate in bias_results.items():
    if rate > REJECT_THRESHOLDS.get(bias, 1.0):
        raise ValueError(f"Judge {bias} ({rate:.1%}) exceeds threshold — recalibrate before using")
```
```

### Practical Integration Rules

- **Run position-swapped pairs as standard practice.** Every pairwise comparison should be evaluated twice (A vs B and B vs A), with scores averaged. This alone eliminates most position bias.
- **Calibrate judges per domain.** A judge fine-tuned on general instruction-following is not reliable for code quality, legal reasoning, or multilingual customer support. Use domain-matched judges or fine-tune.
- **Pass/fail over continuous scales.** Judges are inconsistent on 1-10 scales. Binary pass/fail judgments are significantly more reliable. Reserve continuous scoring for human review.
- **Validate judges with known-signal pairs.** Before deploying a judge, test it on 20 pairs where you already know the correct answer. If the judge gets more than 20% wrong on known pairs, recalibrate.
- **Separate eval from development.** The judge evaluating your agent should not be the same model version as the agent being evaluated. Cross-model evaluation is more honest than self-evaluation.

## Receipt

> Verified 2026-07-25 — BabelJudge framework (arXiv:2606.22329, KC June 2026) documents four systematic judge biases with quantified failure rates. UCBerkeley study (arXiv:2606.19544, Norman et al.) tested 21 judges across 118 runs and ~541K judgments. Adaline benchmark testing (April 2026) found frontier models exceed 50% error rates on bias benchmarks. Position bias causes up to 30% score variance depending on slot assignment (BabelJudge). Order inconsistency rates of 15-40% observed across judge models (FairJudge 2026, Zheng et al.). Cross-lingual degradation confirmed across non-English languages without language-specific judges.

## See also

- [S-385 · The Trajectory Eval Stack](stacks/s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — process vs outcome scoring; the eval rubric design problem
- [S-1000 · The Eval Gap Stack](stacks/s1000-the-eval-gap-stack-when-your-eval-suite-passes-but-production-fails.md) — why eval suites pass but production fails; the eval-reality gap
- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-when-your-agent-ships-but-no-ones-watching.md) — inline step verification with LLM-as-judge at production scale
- [S-1629 · The Inference Collapse Stack](stacks/s1629-the-inference-collapse-stack-when-ground-truth-goes-missing-and-your-agent-builds-on-its-own-guesses.md) — metacognitive poisoning; when eval itself becomes corrupted
