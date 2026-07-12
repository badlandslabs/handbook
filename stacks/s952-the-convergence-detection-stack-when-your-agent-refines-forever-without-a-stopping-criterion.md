# S-952 · The Convergence Detection Stack — When Your Agent Refines Forever Without a Stopping Criterion

Your agent is polishing a document. Or refining a plan. Or iterating on a response. It looks better each pass — but you're watching tokens burn with no guarantee the next pass improves anything. The model doesn't know when to stop. You need a mechanical stopping criterion, not intuition.

## Forces

- **Unbounded refinement is the default.** An agent that revises its own output will revise it indefinitely unless the system enforces a stopping condition. LLMs don't have internal "good enough" signals — they'll happily spend 10,000 tokens polishing prose that was already at 90% of maximum quality.
- **No test harness means no natural stop.** For code-generation agents, `pytest passed → stop` works trivially. For prose, specs, summaries, and design documents, there is no machine-checkable criterion. "It looks better" is not a stopping rule.
- **Human judgment is too slow and too inconsistent.** Waiting for a human to review each iteration defeats the purpose of automation. And different humans have different thresholds — the stopping point becomes unpredictable.
- **Over-refining wastes money; under-refining leaves bugs.** The cost of being wrong in either direction is real, but the trade-off is invisible without measurement.

## The move

**Monitor three signals across consecutive refinement passes. Stop when all three converge.**

The three signals (from agentpatterns.ai):

| Signal | Measures | Converging ✓ | Diverging ✗ |
|--------|----------|--------------|-------------|
| **Output similarity** | Semantic hash or embedding distance between pass N and N−1 | Δ → 0 | Δ growing |
| **Token delta** | Output tokens added/removed per pass | Shrinking | Growing |
| **Explicit quality vote** | Self-critique score or external judge score | Flat or improving | Declining |

**The rule**: Stop when output similarity has plateaued *and* token delta is negligible *and* the quality vote shows no improvement for K consecutive passes.

```python
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from openai import OpenAI

client = OpenAI()

@dataclass
class ConvergenceState:
    """Tracks three signals across refinement iterations."""
    output_hash: str = ""
    output_length: int = 0
    quality_votes: list[float] = field(default_factory=list)
    pass_count: int = 0
    consecutive_plateau_passes: int = 0

    SIMILARITY_THRESHOLD: float = 0.97   # cosine sim of semantic embeddings
    LENGTH_DELTA_THRESHOLD: float = 0.02  # fractional change in token count
    QUALITY_PLATEAU_K: int = 2           # stops after K passes with no quality gain


def semantic_hash(text: str) -> str:
    """Cheap semantic proxy: hash of normalized text."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-8)


def quality_vote(text: str, criteria: str = "accuracy, clarity, completeness") -> float:
    """External LLM judge scores the output 1-5 on given criteria."""
    prompt = f"""Score this output on a 1-5 scale for {criteria}.

Output:
{text}

Respond with only the numeric score and a one-word label: e.g. "4/5 acceptable"
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20,
        temperature=0,
    )
    raw = response.choices[0].message.content
    # Extract numeric score
    import re
    m = re.search(r"(\d)", raw)
    return float(m.group(1)) if m else 3.0


def has_converged(state: ConvergenceState, prev_hash: str,
                  prev_length: int, prev_votes: list[float]) -> tuple[bool, str]:
    """
    Returns (should_stop, reason).
    """
    state.pass_count += 1

    # Signal 1: output similarity plateau
    hash_sim = 1.0 if prev_hash == state.output_hash else 0.0
    # Signal 2: token delta plateau
    length_frac = state.output_length / max(prev_length, 1)
    length_delta = abs(1.0 - length_frac)
    # Signal 3: quality vote plateau
    if len(state.quality_votes) >= 2 and len(prev_votes) >= 1:
        quality_improved = state.quality_votes[-1] > prev_votes[-1]
        if not quality_improved:
            state.consecutive_plateau_passes += 1
        else:
            state.consecutive_plateau_passes = 0
    else:
        state.consecutive_plateau_passes = 0

    # Converged: hash identical, token delta negligible, quality stopped improving
    hash_converged = hash_sim >= 0.99
    length_converged = length_delta < state.LENGTH_DELTA_THRESHOLD
    quality_plateaued = state.consecutive_plateau_passes >= state.QUALITY_PLATEAU_K

    if hash_converged and length_converged and quality_plateaued:
        return True, f"converged after {state.pass_count} passes"

    # Partial convergence: hash and length stable, quality still improving
    if hash_converged and length_converged:
        return False, f"output stable but quality still improving ({state.consecutive_plateau_passes}/{state.QUALITY_PLATEAU_K})"

    return False, f"pass {state.pass_count}: hash_sim={hash_sim:.2f}, len_delta={length_delta:.3f}, quality_plateau={state.consecutive_plateau_passes}/{state.QUALITY_PLATEAU_K}"


def refine_with_convergence(
    initial_text: str,
    refine_prompt: str,
    criteria: str = "accuracy, clarity",
    max_passes: int = 10,
) -> tuple[str, ConvergenceState]:
    """
    Iteratively refine text until convergence signals fire.
    """
    state = ConvergenceState()
    prev_hash = ""
    prev_length = 0
    prev_votes: list[float] = []

    current = initial_text
    for i in range(max_passes):
        should_stop, reason = has_converged(state, prev_hash, prev_length, prev_votes)
        if should_stop:
            print(f"[convergence] Stopping: {reason}")
            break

        # Refinement pass
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a precise editor. Improve the text based on the critique provided."},
                {"role": "user", "content": f"Current text:\n{current}\n\nRefinement instruction:\n{refine_prompt}"},
            ],
            temperature=0.3,
        )
        current = response.choices[0].message.content

        # Update state
        prev_hash, prev_length = state.output_hash, state.output_length
        prev_votes = list(state.quality_votes)
        state.output_hash = semantic_hash(current)
        state.output_length = len(current.split())
        state.quality_votes.append(quality_vote(current, criteria))

        print(f"[convergence] Pass {i+1}: {reason}")

    return current, state
```

**Minimum viable version** — if you can't run a judge model on every pass:

```python
# Minimal: hash similarity + token delta, no quality vote
def has_converged_minimal(prev: str, current: str, plateau_k: int = 3) -> tuple[bool, int]:
    prev_hash = semantic_hash(prev)
    curr_hash = semantic_hash(current)
    if prev_hash == curr_hash:
        return True, 0
    prev_len = len(prev.split())
    curr_len = len(current.split())
    delta = abs(curr_len - prev_len) / max(prev_len, 1)
    return delta < 0.01, 0
```

## Receipt

> Receipt pending — 2026-07-11

## See also

- [S-516 · Trajectory-Level Loop Detection](s516-trajectory-level-loop-detection.md) — trajectory hashing catches same-action repetition; convergence detection catches semantic refinement plateau
- [S-821 · The Production Failure Stack](s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — cost governors as hard budget ceiling; convergence detection as soft quality ceiling
- [S-114 · Reasoning Scratchpad Budget](s114-reasoning-scratchpad-budget.md) — CoT token budget is a related axis; convergence detection answers "should the loop keep running?" not just "how many tokens did it burn?"
