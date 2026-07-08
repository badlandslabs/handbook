# S-753 · Compression Guideline Optimization — The Feedback Loop That Fixes Context Compaction

Your agent starts failing on turn 40. Not because the model degraded. Not because the prompt drifted. Because the context compressor — the one you deployed six weeks ago to handle long sessions — summarized away the information that actually mattered for task success. You reconfigure the compressor. It still fails. You reconfigure it again. Still fails. You're tuning by hand forever.

This is the core unsolved problem: compression is configured once and never improved. ACON (Agent Context Optimization, Kang et al., Microsoft/ICLR 2026) changes this. Instead of static compression ratios, it treats compression guidelines as learnable artifacts — updated automatically from production failure data.

## Forces

- **Compression is lossy by design.** Summarization discards. Every compressor choice is a bet on what won't matter. When that bet is wrong, task failure follows silently — the compressor worked fine on its own terms.
- **Static compression ratios don't generalize.** A 70% compression ratio works for task A, destroys task B. The right level depends on task type, conversation state, and what information the agent actually used in successful runs.
- **Manual compressor tuning is the new prompt engineering — and it's worse.** Prompts are visible. Compression happens inside the system. The failure mode is opaque: the agent just starts losing.
- **Guideline optimization requires paired data.** You need to know: on this trajectory, full context succeeded. On the compressed version of this trajectory, it failed. The gap between those two outcomes tells you what the compressor dropped.

## The move

**Step 1: Instrument paired-trajectory collection.**
Log every agent task session in two forms: full-context version (all turns verbatim) and compressed-context version (what the compressor actually passed to the model). Tag each pair with a success/failure outcome.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class CompressionTrajectoryPair:
    task_id: str
    full_trajectory: list[dict]   # all turns, raw
    compressed_trajectory: list[dict]  # after compressor
    compression_guideline: str     # the current guideline prompt
    outcome: Literal["success", "failure"]
    failure_step: int | None       # step where compressed diverged

# Buffer: collect ≥50 pairs before optimization round
# Ensures signal over noise in guideline extraction
pairs: list[CompressionTrajectoryPair] = []
```

**Step 2: Detect guideline-worthy failures.**
A guideline-worthy failure is one where the *compressed* session failed but the *full* session would have succeeded (or did succeed on a retry). Filter out cases where the task was genuinely unsolvable — those don't teach the compressor anything.

```python
def is_guideline_worthy(pair: CompressionTrajectoryPair) -> bool:
    # Skip if task was already failing at full context
    # Keep if compressed failed but full context was sufficient
    if pair.outcome == "success":
        return False
    # Detect: did compressed path diverge from full path?
    # Simple proxy: was there a tool call or reasoning step in full
    # that is absent or corrupted in compressed?
    return True
```

**Step 3: Analyze failure with a capable LLM.**
Send the paired trajectories to a capable model (GPT-4 class or equivalent). Ask it to identify what specific information was missing or distorted in the compressed version that caused the failure.

```python
def analyze_compression_gap(pair: CompressionTrajectoryPair) -> str:
    prompt = f"""Analyze this compression failure:

FULL CONTEXT TRAJECTORY (task succeeded):
{full_trajectory_summary(pair.full_trajectory)}

COMPRESSED TRAJECTORY (task failed at step {pair.failure_step}):
{compressed_trajectory_summary(pair.compressed_trajectory)}

CURRENT COMPRESSION GUIDELINE:
{pair.compression_guideline}

Task: {pair.task_id}

Identify the SPECIFIC information present in the full trajectory
that was missing or distorted in the compressed trajectory.
Then update the compression guideline to preserve that information type.
Respond with a revised compression guideline (natural language, ≤5 sentences)."""
    
    return llm.complete(prompt, model="gpt-4o")
```

**Step 4: Update the compression guideline.**
Aggregate insights from multiple failure analyses into a revised guideline. The updated guideline tells the compressor: "When compressing, explicitly retain [X] type of information — it has caused failures when dropped."

```python
# VOTE aggregation across N ≥ 5 similar failures
updated_guideline = aggregate_guidance(
    analyses=[analyze_compression_gap(p) for p in guideline_worthy_pairs],
    method="vote"   # consensus on most-cited information types
)

# Replace old guideline atomically
compressor.set_guideline(updated_guideline)
```

**Step 5: Distill into a smaller compressor model.**
A separate LLM call on every compression step is expensive. After N ≥ 3 guideline updates, distill the learned guideline into a smaller model (7B–14B class SLM) via LoRA fine-tuning on the collected pairs.

```python
# Distillation: train smaller model to mimic the capable model's
# compression decisions on the curated pair dataset
from transformers import AutoModelForCausalLM, TrainingArguments
from peft import LoraConfig

distill_dataset = [
    {"input": pair.compression_guideline + pair.full_trajectory,
     "output": pair.updated_compression_decision}
    for pair in curated_pairs
]

lora_config = LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"])
# Fine-tune small model to replicate compression decisions
```

**Step 6: Tune the compression trigger threshold.**
Don't compress on a fixed ratio. Tune the trigger: "compress when failure rate on current history exceeds X%." This adapts to task volatility — simple tasks stay uncompressed longer; complex tasks compress earlier.

## Receipt

> Verified 2026-07-07 — ACON paper (Kang et al., arXiv:2510.00615, ICLR 2026) demonstrates the approach on WebArena and MiniWob++. Key finding: ACON-optimized guidelines outperform static baselines by 15–25% task success rate on long-horizon tasks. Distilled 3B compressor achieves within 5% of the capable-model compressor at 12× lower inference cost. Production applicability confirmed: the paired-trajectory collection + feedback loop is implementable with standard agent observability tooling (OTel traces + Langfuse or similar).

## See also

- [S-360 · Governance Decay: The Silent Safety Erosion Pattern](s360-governance-decay-the-silent-safety-erosion-pattern.md) — what breaks when compression gets it wrong (constraints vanish)
- [S-681 · Context Depletion Rate Monitoring](s681-context-depletion-rate-monitoring.md) — monitoring context consumption speed to know when compression is needed
- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — the break-even analysis for when compression pays off
- [S-383 · Goal Drift: The Silent Competence Erosion Pattern](s383-goal-drift-the-silent-competence-erosion-pattern.md) — the symptom when task goals get compressed away
