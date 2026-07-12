# S-958 · The Synthetic Trajectory Fidelity Stack — When Your Eval Data Doesn't Look Like Your Production Agents

Your agent scores 87% on your synthetic eval suite. You ship it. Three weeks later, a production incident report shows the agent consistently fails a class of queries it never encountered in evals — not because the questions were hard, but because your synthetic eval set never contained that query distribution. Your eval was measuring agent quality on data that doesn't match what users actually ask. The score was real. The representativeness wasn't.

## Forces

- **Real agent trajectories are sensitive.** Production traces may contain proprietary data, PII, customer information, or trade secrets. Teams cannot ship these to a benchmark provider, publish them as open datasets, or use them for fine-tuning. Synthetic trajectory generation solves the data scarcity problem — but creates a fidelity problem.
- **Synthetic generation optimises for what you can describe, not what users actually do.** Prompting a frontier model to generate "typical agent trajectories" produces trajectories that look like well-designed agent tasks, not like the messy, ambiguous, edge-case-heavy inputs that real users actually send. The generation process has a built-in optimism bias.
- **Distribution divergence is invisible until production.** If your synthetic eval set lacks adversarial inputs, low-context queries, policy conflicts, or escalation scenarios, the agent will score well on evals while failing on the production distribution that actually contains them. Eval scores go up; failure rate goes up in parallel.
- **The mismatch has four dimensions.** ICLR 2026 research (ESDAE) identifies systematic divergence across: task instruction distribution, tool call patterns, environmental constraints, and failure mode profiles. Teams typically check only one (task coverage) and miss the other three.

## The move

ESDAE (Evaluating Synthetic Data for Agent Evaluation, Wang et al., ICLR 2026 Workshop) formalises this as a four-axis problem:

```
Fidelity Dimensions
├── Task Instruction Alignment   → Do synthetic tasks match real input distribution?
├── Tool Call Pattern Alignment  → Are tool selection frequencies and sequences realistic?
├── Environmental Constraint Alignment → Do constraints (rate limits, auth, schema) mirror production?
└── Failure Mode Alignment       → Do synthetic failures reproduce real failure modes?
```

The **synthetic trajectory fidelity score** (STFS) is the composite across these four axes. High scores on three axes and a zero on failure mode alignment is still a critical gap — it means your agent is unvalidated on the most important production behaviours.

### Detecting the gap before it reaches production

**1. Cohort analysis against production logs.**
Run shadow-mode production inference alongside your eval suite. For every production trajectory, classify whether it would be covered by your eval set. Track the coverage rate by query type, user segment, and time of day. If coverage drops below 80% for any cohort, that cohort is unvalidated.

**2. The adversarial input probe.**
Generate synthetic inputs designed to be hard: zero-context queries ("help"), policy conflicts, multi-agent context where the agent's task conflicts with another agent's output, and hostile user inputs. If your current eval set has zero adversarial inputs, add 15-20%. A dramatic accuracy drop is a fidelity gap signal.

**3. Tool call distribution comparison.**
Compare the tool call frequency distribution in your synthetic set against a sampled production trace (redacted to remove sensitive content). Large divergences on specific tools indicate your synthetic set is underrepresenting those tools' usage contexts.

### Closing the fidelity gap

The ESDAE paper's recommended workflow:

```
[Real Production Traces (redacted)]
         ↓
[Trajectory Attribute Extraction]
    - Task type tags
    - Tool call sequences
    - Environmental constraints
    - Failure mode labels
         ↓
[Synthetic Generation with Distribution Matching]
    Prompt the generator with real attribute distributions
    as constraints, not just task descriptions
         ↓
[Fidelity Scoring]
    STFS = weighted composite of 4-axis scores
    Require ≥0.8 on all axes before use in eval
         ↓
[Eval Deployment]
```

The key shift: **stop prompting generators with task descriptions, start prompting them with real-world attribute distributions**. Instead of "generate 50 customer service agent trajectories," say "generate 50 trajectories where 60% of queries have missing context, 20% contain policy conflicts, and tool call sequences follow this frequency distribution: [extracted from production logs]."

### The overfitting trap

Even high-fidelity synthetic sets have a lifespan. As your agent evolves through fine-tuning and prompt updates, the eval set that matched production yesterday may no longer match today. Re-run the fidelity scoring quarterly or after any agent change that affects tool selection or failure recovery behaviour.

```python
# Fidelity scoring skeleton (inspired by ESDAE four-axis framework)
from collections import Counter
from scipy.stats import wasserstein_distance

def synthetic_trajectory_fidelity_score(
    synthetic_traces: list[Trace],
    real_traces: list[Trace],
) -> dict[str, float]:
    """
    Compute per-axis fidelity between synthetic and real trajectory distributions.
    Each axis returns a score 0-1 where 1 = perfect alignment.
    """
    return {
        "task_instruction": task_instruction_alignment(
            [t.task for t in synthetic_traces],
            [t.task for t in real_traces],
        ),
        "tool_call_pattern": tool_call_pattern_alignment(
            [extract_tool_sequence(t) for t in synthetic_traces],
            [extract_tool_sequence(t) for t in real_traces],
        ),
        "environmental_constraint": environmental_alignment(
            [t.constraints for t in synthetic_traces],
            [t.constraints for t in real_traces],
        ),
        "failure_mode": failure_mode_alignment(
            [classify_failure(t) for t in synthetic_traces],
            [classify_failure(t) for t in real_traces],
        ),
    }

def task_instruction_alignment(synth_tasks, real_tasks) -> float:
    """
    Compare task type distribution using Wasserstein distance
    on embedded task descriptions. Lower distance = higher fidelity.
    """
    synth_embeddings = embed_batch(synth_tasks)
    real_embeddings = embed_batch(real_tasks)
    # Earth Mover's Distance between distribution centroids
    distance = wasserstein_distance(
        synth_embeddings.mean(axis=0),
        real_embeddings.mean(axis=0),
    )
    return max(0.0, 1.0 - distance / 2.0)  # normalise to [0,1]

def tool_call_pattern_alignment(synth_seqs, real_seqs) -> float:
    """
    Compare tool call frequency and bigram transition matrices.
    0.5 weight on marginal frequencies, 0.5 on transition patterns.
    """
    synth_freq = normalize(Counter(tool for seq in synth_seqs for tool in seq))
    real_freq = normalize(Counter(tool for seq in real_seqs for tool in seq))
    freq_score = 1.0 - wasserstein_distance(synth_freq, real_freq)

    synth_bigram = build_bigram_matrix(synth_seqs)
    real_bigram = build_bigram_matrix(real_seqs)
    transition_score = 1.0 - frobenius_norm(synth_bigram - real_bigram)

    return 0.5 * freq_score + 0.5 * transition_score
```

## Receipt

> Verified 2026-07-11 — Framework based on ESDAE (Wang et al., ICLR 2026 Workshop DATA-FM/AIWILD, arXiv:2605.22564). Core dimensions (task instruction, tool call pattern, environmental constraint, failure mode) are directly from the paper. Code skeleton demonstrates the statistical comparison approach (Wasserstein distance for distributions, Frobenius norm for transition matrices). Production deployment requires your own redacted trajectory logs as the real-reference set.

## See also

- [S-569 · The Eval Illusion](s569-the-eval-illusion-when-passing-evals-dont-prevent-production-failures.md) — eval coverage gaps and the confidence trap
- [S-901 · The Golden Set Trap](s901-the-golden-set-trap-when-your-eval-suite-gives-you-confidence-you-havent-earned.md) — when your eval set doesn't represent real tasks
- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — the technical infrastructure for running eval pipelines
- [S-246 · Production Eval Pipeline](s246-production-eval-pipeline-the-four-stage-loop.md) — continuous eval in production environments
