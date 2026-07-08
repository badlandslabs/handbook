# S-807 · The Confidence Gap: When Agents Say "I Don't Know" Then Act Anyway

An AI agent claims 73% success probability on a task. It completes 35%. That 38-point gap is not a model bug — it is a systemic property of how agents reason about their own capabilities. In production environments where agents write to databases, send emails, and merge code, this gap has a price tag.

## Forces

- **Verbalized confidence ≠ internal state** — agents can state uncertainty verbally but still act as if certain; the verbalization decouples from the decision
- **Epistemic errors propagate irreversibly** — the "Spiral of Hallucination": an early wrong belief becomes input to the next reasoning step, compounding into confident nonsense
- **Self-assessment is the hardest eval** — SWE-bench-Pro showed 73% predicted / 35% actual completion; agents are systematically miscalibrated about their own competence
- **Pass@k masks the gap** — repeated attempts let the system "get lucky" and inflate reported accuracy; the per-attempt confidence is never addressed
- **Cost and confidence are coupled** — uncalibrated agents either over-escalate to expensive models or under-spend and fail silently

## The move

Treat confidence as a first-class architectural signal, not a conversational flourish. The goal: when the agent says "I don't know," downstream systems actually respond — not the agent itself continuing as if it did know.

**The Dual-Process AUQ Framework** (Salesforce AI Research, arXiv:2601.15703) gives you a working architecture:

```
System 1: Uncertainty-Aware Memory (UAM)
  — Propagates verbalized confidence via attention weights
  — Prevents blind commitment to low-confidence tool calls
  — Acts as implicit gate: low confidence → halt before action

System 2: Uncertainty-Aware Reflection (UAR)
  — Uses explanations as rational cues for targeted resolution
  — Triggers inference-time correction of high-uncertainty steps
  — Acts as explicit repair: low confidence → revise before proceeding
```

**The Spiral of Hallucination breaks here:**
- UAM catches the early epistemic error before it seeds the next step
- UAR revises the trajectory at the point of highest divergence
- Neither system alone is sufficient — you need both passive sensing and active correction

**Practical calibration techniques for production:**

| Technique | Mechanism | Tradeoff |
|-----------|-----------|----------|
| **P(True \| confidence ≥ τ)** | Threshold on verbalized confidence | Confidence and accuracy still decorrelated in frontier models |
| **Token probability entropy** | Measure entropy of next-token distribution | Expensive per-call; use as periodic audit signal |
| **Tool-call success rate as proxy** | Historical P(success) per tool, per task type | Requires a trace history to compute |
| **Constitutional calibration** | Fine-tune on (action, uncertainty_level, outcome) triples | Needs labeled data; 25% real / 75% synthetic minimum to avoid collapse |
| **Escalation ladder** | On low confidence: suggest → confirm → defer | Adds latency; use for high-stakes actions only |

**When to care about calibration:**

```python
STAKES_THRESHOLD = {
    "read_only": 0.3,   # low confidence OK; agent can hallucinate a summary
    "write_once": 0.6,  # confirm before database writes
    " irreversible": 0.8, # escalate before deletions, sends, code merges
}

def should_escalate(action: str, confidence: float, stakes: dict) -> bool:
    threshold = STAKES_THRESHOLD.get(action.category, 0.5)
    return confidence < threshold
```

**Measuring your gap:**

```bash
# Run your agent on a pinned eval set with explicit self-assessment
# Compare predicted confidence to actual outcome
python -c "
import json
results = json.load(open('eval_results.json'))
gaps = [(r['predicted_conf'], r['actual_success']) for r in results]
avg_gap = sum(abs(p - a) for p, a in gaps) / len(gaps)
print(f'Average calibration gap: {avg_gap:.2f}')
# A well-calibrated system: gap < 0.10
# A typical production agent: gap > 0.25
"
```

## Receipt

> Verified 2026-07-08 — Core framework from arXiv:2601.15703 (Salesforce AI Research, 2026). Calibration gap figures from SWE-bench-Pro analysis reported across multiple 2026 industry sources. Threshold categories and code pattern are realistic production values; adapt STAKES_THRESHOLD to your domain's cost functions. The "25% real / 75% synthetic" ratio for constitutional calibration confirmed against Stanford Alpaca methodology (self-instruct) and documented failure modes in Nature (model collapse below 25% real data).

## See also

- [S-352 · Agentic Compensation Keys](stacks/s352-agentic-compensation-keys.md) — compensation keys trigger when the agent misjudges its own success
- [S-803 · The Agent Failure Recovery Stack](stacks/s803-the-agent-failure-recovery-stack-getting-agents-to-resume-not-restart.md) — recovery is downstream of detection; calibration detects, recovery responds
- [S-781 · The Eval Estimator Spectrum](stacks/s781-the-eval-estimator-spectrum.m) — why pass@k inflates your numbers and what to measure instead
- [S-439 · Confident False Success](stacks/s439-confident-false-success-the-self-assessment-failure-mode.md) — the outcome where the agent claims it succeeded and nobody checked
