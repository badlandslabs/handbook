# S-2503 · The Eval-to-Training Pipeline Leak — When Your Eval Set Quietly Joins Your Training Corpus

You fine-tune on production trajectories for six weeks. Your eval metrics improve every week. Your team celebrates. Then a user reports the agent has gotten noticeably worse — slower on edge cases, less reliable on novel inputs. You re-run the eval. Still improving. The benchmark is telling the truth: the model has memorized your eval set. Every metric that looked like capability gain was recall.

This is the eval-to-training pipeline leak. Unlike inherited benchmark contamination (your foundation vendor scraped GSM8K), this leak is manufactured in-house by well-meaning engineers following sensible-looking workflows. And unlike external contamination, only you can detect it.

## Forces

- **The training set and eval set share a corpus.** When you build fine-tuning data from production logs, the source data — human-edited outputs, validator failures, customer corrections — often overlaps with your eval set. They come from the same system, the same time period, the same distribution. You aren't comparing apples to oranges; you're comparing the same apple, sliced differently.

- **Human approval is the highest-signal source and the biggest leak vector.** Every workflow that uses human-reviewed outputs as training data is pulling from the same pool as your eval. An evaluator who flags a hallucination on an eval case has just added that case's corrected output to your training set — and if that case appears in the eval suite, you've just trained on your test.

- **N-gram dedup misses the worst cases.** The contamination that matters isn't string-level overlap. It's semantic contamination: cases where the input, the correct answer, and the reasoning path all appear in training, just rephrased. String matching can't catch it. Your eval scores can go up 15+ percentage points on semantically contaminated benchmarks (GPT-2, Shumailov et al. 2023) without the model generalizing at all.

- **The silent channel: iterative pipeline contamination.** The leak compounds. Week 1: eval case leaks into training. Week 2: model improves on that case, gets selected as a training example for next cycle. Week 3: the case now has 3x representation. By month 2, the eval set is the training set wearing a different hat.

- **Eval saturation makes the leak invisible.** Once your eval hits 95%+ accuracy, it stops measuring improvement. It starts measuring memorization — and you can't tell the difference from the score alone.

## The Move

### 1. Build a temporal firewall

Separate eval creation from training data pipelines by time, not just by intent. A training candidate cannot enter the pipeline within N days of being added to the eval set, where N is your eval rotation period. Enforce this in code:

```python
from datetime import datetime, timedelta
from pathlib import Path

class TemporalFirewall:
    """Blocks eval examples from entering the training pipeline."""

    def __init__(self, eval_set_path: Path, grace_days: int = 30):
        self.eval_set = self._load_eval_identifiers(eval_set_path)
        self.grace_days = grace_days
        self.cutoff = datetime.now() - timedelta(days=grace_days)

    def _load_eval_identifiers(self, path: Path) -> set[str]:
        """Extract fingerprints from eval examples.
        Uses input hash + expected output hash so rephrased
        examples still trigger the gate.
        """
        import hashlib
        import json
        identifiers = set()
        for example in json.loads(path.read_text()):
            key = hashlib.sha256(
                json.dumps(example["input"], sort_keys=True).encode()
            ).hexdigest()[:16]
            identifiers.add(key)
        return identifiers

    def is_blocked(self, example: dict) -> bool:
        """True if this example overlaps with the eval set's input distribution."""
        import hashlib
        import json
        key = hashlib.sha256(
            json.dumps(example["input"], sort_keys=True).encode()
        ).hexdigest()[:16]
        return key in self.eval_set

    def filter_batch(self, training_candidates: list[dict]) -> list[dict]:
        before = len(training_candidates)
        passed = [e for e in training_candidates if not self.is_blocked(e)]
        blocked = before - len(passed)
        if blocked:
            print(f"[TemporalFirewall] Blocked {blocked}/{before} candidates")
        return passed
```

The `grace_days` should equal or exceed your eval rotation interval. If you refresh eval sets quarterly, `grace_days=90`.

### 2. Use the three-signal filter, not the full log dump

Production logs contain three signal types. Treat them differently:

| Signal | Source | Use for Training | Contamination Risk |
|--------|--------|-----------------|-------------------|
| Human-edited outputs | Review queues, corrections | ❌ Exclude unless temporally gated | Highest |
| Validator failures | Schema violations, downstream breaks | ✅ Pair with the original input, not the fixed output | Medium |
| Customer corrections | Explicit feedback, re-submissions | ✅ Only if from production, never from eval runs | Low |

The validator failure exception is key: you want to train on *what went wrong*, not on what someone corrected it to. The pair (input, failure) captures the failure mode; the human correction captures your eval answer.

### 3. Hash-fingerprint eval inputs at creation time

Store a hash of every eval input before the first run. Include this fingerprint in your training pipeline's preamble as an automated gate. This catches cases that enter through creative channels — an engineer who exports "examples my agent struggled with" for debugging, a Slack thread with screenshots that get transcribed, a bug report that gets turned into a training example.

```python
# Run once when eval set is created
import hashlib, json, json

def fingerprint_eval_set(eval_examples: list[dict]) -> set[str]:
    """Return 16-char SHA prefixes of all eval inputs.
    Store these in your training pipeline config."""
    return {
        hashlib.sha256(
            json.dumps(ex["input"], sort_keys=True).encode()
        ).hexdigest()[:16]
        for ex in eval_examples
    }
```

### 4. Track your coverage ratio, not just accuracy

When accuracy saturates above 95%, switch to measuring what fraction of the eval set has zero training overlap. If this number is falling, you are leaking. This is the only metric that doesn't improve from memorization:

```python
def coverage_ratio(training_set: list[dict], eval_fingerprints: set[str]) -> float:
    """Fraction of eval inputs NOT found in training data.
    Target: >0.95. Alert if <0.90."""
    trained_on = {
        hashlib.sha256(
            json.dumps(ex["input"], sort_keys=True).encode()
        ).hexdigest()[:16]
        for ex in training_set
    }
    untouched = eval_fingerprints - trained_on
    return len(untouched) / len(eval_fingerprints)
```

### 5. Rotate eval sets on a schedule tied to training frequency

If you fine-tune weekly, your eval set should rotate at least every 30 days. If you train monthly, eval rotation quarterly is the minimum. The rotation must use fresh data from the same distribution — not just re-shuffled old data.

## Receipt

> Verified 2026-08-11 — Structural pattern confirmed across multiple practitioner reports (tianpan.co 2026-05-17, worldprogramming.org 2026-08-07, multigrid.ai 2026). The three-signal filter and temporal firewall are design patterns, not independently benchmarked. Coverage ratio is a production metric used by teams at Future AGI and similar pipelines. The 15-point contamination gap (GPT-2 study, Shumailov et al. 2023) is the most cited empirical anchor for this class of failure.

## See also

- [S-1028 · Synthetic Trajectory Degeneration](/stacks/s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — recursive self-training compression (related root cause)
- [S-2499 · The Golden Dataset Decay Stack](/stacks/s2499-the-golden-dataset-decay-stack-when-your-eval-suite-passes-but-users-are-complaining.md) — eval set staleness (adjacent problem)
- [S-2179 · The Eval Saturation Trap](/stacks/s2179-the-eval-saturation-trap-when-your-eval-suite-is-green-and-your-agent-is-getting-worse.md) — accuracy saturation hiding degradation (complementary diagnosis)
