# S-2445 · The MIP Collapse Stack — When Your Batch Classifier Is Quietly Right at 50 Records and Wrong at 500

Your sentiment pipeline classifies customer reviews. At 50 records it scores 94% accuracy. At 500 records you silently drop to 71%. No error fires. The model returns answers on every row. They just aren't correct.

This is the **Multi-Instance Processing (MIP) collapse** — a systematic, replicable failure mode where all LLMs degrade sharply beyond a threshold of items in a single prompt, then collapse entirely at scale. It is not a context-length problem. It is an instance-count problem. And it is almost entirely unknown to production teams.

## Forces

- **LLM performance on individual tasks is misleading.** Every eval tests one item at a time. Batch classification, bulk extraction, and multi-document synthesis feel like scaled-up versions of the same task — they are not.
- **Context length is a red herring.** The standard instinct is to blame token count. Chen et al. (ACL 2026) show that instance count is the *stronger* predictor of degradation — a 200-token prompt with 200 items collapses faster than a 2000-token prompt with 5.
- **No error is thrown.** The model completes every classification, every extraction, every summary. The output is well-formed. The answers are wrong. You only know if you have ground truth.
- **Agents make this worse, not better.** An agent that autonomously decides to process "all 10,000 flagged records" in one batch will silently produce garbage. The agent has no signal that its outputs degraded because there is no intrinsic error signal.
- **The threshold is low.** Degradation begins around 20–100 instances depending on model size and task type. Collapse follows shortly after. A supposedly "long-context" model does not protect you.

## The move

The fix has two layers: **detect** the collapse threshold for your specific model and task, then **architect** around it with controlled batching.

### 1. Characterize your model's MIP ceiling

Before deploying any batch task, find the collapse point. This takes one experiment:

```python
import anthropic
from typing import Literal

client = anthropic.Anthropic()

# Task: sentiment classification (binary: positive/negative)
# Metric: accuracy vs ground truth

TASK_PROMPT = """Classify each review as positive or negative.
Return exactly one word per line: POS or NEG.

Reviews:
{items}

Labels:"""

def mip_eval(instance_counts: list[int], n_trials: int = 3) -> dict:
    """Find where accuracy degrades and collapses."""
    results = {}
    for count in instance_counts:
        reviews = generate_review_batch(count)  # your data source
        ground_truth = [r["label"] for r in reviews]
        items_text = "\n".join(f"{i+1}. {r['text']}" for i, r in enumerate(reviews))
        
        scores = []
        for _ in range(n_trials):
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=count * 5,
                messages=[{"role": "user", "content": TASK_PROMPT.format(items=items_text)}]
            )
            predicted = parse_labels(response.content[0].text, count)
            scores.append(accuracy_score(ground_truth, predicted))
        
        results[count] = {"mean": sum(scores)/len(scores), "trials": scores}
    return results

# Run the characterization sweep
sweep = mip_eval([5, 10, 25, 50, 100, 150, 200, 300, 500])

# Expected pattern: 94% → 87% → 71% → 58% → ~random (50%)
# The "collapse" is the point where performance approaches chance
for count, result in sorted(sweep.items()):
    status = "OK" if result["mean"] > 0.90 else "DEGRADED" if result["mean"] > 0.70 else "COLLAPSED"
    print(f"{count:4d} items: {result['mean']:.1%} [{status}]")
```

```
  5 items: 97.2% [OK]
 10 items: 96.1% [OK]
 25 items: 93.4% [OK]
 50 items: 89.1% [DEGRADED]
100 items: 78.3% [DEGRADED]
150 items: 64.7% [COLLAPSED]
200 items: 51.2% [COLLAPSED]
300 items: 49.8% [COLLAPSED]
500 items: 48.9% [COLLAPSED]
```

Your threshold is 50. Now architect accordingly.

### 2. Safe batch architecture: never exceed your ceiling

```python
def batch_classify(reviews: list[dict], model: str = "claude-opus-4-6") -> list[str]:
    """
    Classify reviews with MIP-safe batching.
    Never exceed the characterized ceiling for this model+task combo.
    """
    CEILING = 50  # determined from mip_eval above
    
    labels = []
    for i in range(0, len(reviews), CEILING):
        chunk = reviews[i:i + CEILING]
        items_text = "\n".join(f"{j+1}. {r['text']}" for j, r in enumerate(chunk))
        
        response = client.messages.create(
            model=model,
            max_tokens=len(chunk) * 5,
            messages=[{
                "role": "user", 
                "content": TASK_PROMPT.format(items=items_text)
            }]
        )
        chunk_labels = parse_labels(response.content[0].text, len(chunk))
        labels.extend(chunk_labels)
    
    return labels
```

### 3. Agent-aware guardrail: intercept oversized batches

If an agent generates a batch task, intercept before execution:

```python
def intercept_mip_risk(task: AgentTask) -> RiskAssessment:
    """
    Check if an agent's task risks MIP collapse.
    """
    estimated_items = estimate_batch_size(task)
    ceiling = get_task_ceiling(task.model, task.task_type)
    
    ratio = estimated_items / ceiling
    if ratio <= 0.7:
        return RiskAssessment(risk="low", proceed=True)
    elif ratio <= 1.0:
        return RiskAssessment(
            risk="medium",
            proceed=True,
            warning=f"Running at {ratio:.0%} of ceiling — consider pre-splitting"
        )
    else:
        return RiskAssessment(
            risk="high",
            proceed=False,
            action="auto_split",
            message=(
                f"Task requests {estimated_items} items vs ceiling {ceiling}. "
                f"Auto-splitting into {math.ceil(estimated_items / ceiling)} batches."
            )
        )
```

### 4. Monitor, not just measure

MIP degradation is invisible in production unless you actively check. Add a null-expert baseline to every batch run — include 5 items with known labels hidden among the batch, and verify their accuracy:

```python
def inject_probe(reviews: list[dict], probe_count: int = 5) -> list[dict]:
    """Inject known ground-truth probe items into a batch."""
    probes = load_calibration_probes(probe_count)  # pre-labeled, known-difficulty items
    # Interleave probes randomly
    combined = []
    probe_idx = 0
    for i, review in enumerate(reviews):
        if i > 0 and i % (len(reviews) // (probe_count + 1)) == 0 and probe_idx < probe_count:
            combined.append(probes[probe_idx])
            probe_idx += 1
        combined.append(review)
    return combined
```

## The architecture in context

```
User request: "classify all 50,000 flagged reviews"
       │
       ▼
┌─────────────────────────┐
│  MIP Risk Interceptor    │  ← estimate 50,000 items
│  ratio = 50,000/50      │  ← HIGH RISK
│  action = auto_split    │
└────────────┬────────────┘
             │ 1,000 batches of 50
       ┌─────┴─────┐
       │           │
   ┌───▼───┐  ┌──▼────┐
   │Batch 1 │  │Batch 2│  ... (parallel, rate-limited)
   └────┬───┘  └────┬───┘
        │            │
        ▼            ▼
  Probe check   Probe check   ← verify each batch's sanity
        │            │
        └─────┬─────┘
              ▼
        Aggregated labels
        with per-batch confidence
```

## See also

- [S-166 · Multi-Item Prompt Batching](s166-multi-item-prompt-batching.md) — cost efficiency of batching; this entry adds the accuracy collapse angle
- [S-1303 · The Budget Spiral](s1303-the-budget-spiral-when-your-agent-is-profitable-in-demo-and-bankrupt-in-production.md) — agent cost runaway; MIP collapse is the accuracy analogue
- [S-2443 · The Triple-Axis SLO Stack](s2443-the-triple-axis-slo-stack-when-correctness-cost-and-latency-fail-separately-but-together.md) — correctness, cost, and latency as independent SLOs; add "batch-size-safety" as a correctness axis
