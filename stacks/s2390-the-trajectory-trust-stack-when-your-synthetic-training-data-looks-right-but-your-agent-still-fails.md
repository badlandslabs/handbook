# S-2388 · The Trajectory Trust Stack — When Your Synthetic Training Data Looks Right But Your Agent Still Fails

You generated 50,000 synthetic tool-calling trajectories. You fine-tuned a domain agent on them. The eval benchmark looks great. Production reveals the agent makes basic mistakes no human labeler would make — wrong tool sequencing, wrong argument schemas, wrong edge-case handling. You assumed the pipeline was the bottleneck. It wasn't. The data itself was the failure, and you had no framework to know.

## Forces

- **Synthetic data is cheap and unvalidated by default.** Generating 50K traces costs less than labeling 500 real ones. The cost signal says "scale." The quality signal says nothing.
- **Validity ≠ fidelity ≠ diversity.** A trace can be syntactically correct (valid), match real-trajectory distributions (fidelity), and still not cover the edge cases that break production (diversity). SynAE (CMU/Microsoft Research, arXiv:2605.22564) documents all three failure modes independently.
- **Trajectory data propagates errors downstream.** A single mis-sequenced tool call in a training trace teaches the opposite of what you want. SFT memorizes trajectories, not capabilities — 200K traces of the same wrong pattern will overpower 500 correct ones.
- **The verifier problem.** Who checks that synthetic traces are correct? The same model that generated them, in self-consistency loops. This is circular.
- **Real production traces are scarce, sensitive, or sparse.** Exactly when you need synthetic augmentation most, the ground truth is least available.

## The move

### 1. Score trajectories before training, not after

The SynAE framework (Wang et al., CMU + Microsoft, arXiv:2605.22564) evaluates synthetic trajectory datasets on three orthogonal pillars across four trace components:

| Pillar | What it measures |
|--------|-----------------|
| **Validity** | Does the trace execute correctly? (tool exists, args match schema, sequence is valid) |
| **Fidelity** | Does the trace distribution match real production traces? (token patterns, tool frequency, conversation lengths) |
| **Diversity** | Does the trace set cover edge cases and uncommon tool combinations? (combinatorial coverage, rare-event rate) |

Run SynAE before fine-tuning. A dataset that scores high on validity and fidelity but low on diversity will produce an agent that performs well on standard benchmarks and fails on anything novel.

### 2. Generate traces from verifiable task blueprints

The Trajectory2Task pipeline (Amazon Science, ACL 2026) resolves the circularity:

1. **Multi-turn exploration** — generate valid tool-call trajectories using a capable model in "exploration mode" with sandboxed tools and ground-truth task descriptions.
2. **Task back-generation** — convert trajectories into user-facing tasks with controlled adaptations (ambiguous intent, changing intent, infeasible intent).
3. **Closed-loop verification** — re-execute the generated task against the same trajectory; if the outcome differs, discard.
4. **Fine-tuning on verified rollouts** — only traces from step 3 enter the training set.

The key property: tasks are verifiable *independently* of the model that generated the traces. You don't trust the generator to verify itself.

### 3. Control the three intent distributions

Real user requests cluster into three categories that synthetic data pipelines systematically misrepresents:

| Intent type | What happens in real-world | Common synthetic failure |
|-------------|---------------------------|-------------------------|
| **Ambiguous intent** | User says "book the cheapest flight" — cheapest by price, time, or layovers is unspecified | Pipeline generates precisely-specified tasks; agent never sees genuine ambiguity |
| **Changing intent** | User mid-task says "actually, do X instead" | Trajectories are single-goal; multi-goal transitions are absent |
| **Infeasible intent** | User requests something policy-blocked | Pipeline filters out failures; agent trained only on successful outcomes |

Fine-tune on all three. An agent trained only on successful trajectories will hallucinate success when blocked — the worst possible failure mode in consequential workflows.

### 4. Use production traces as anchor sets, not training data

Never use real production traces as training data (PII, proprietary). Use them as **anchor sets** for fidelity scoring:

```python
# Anchor-based fidelity: measure how well synthetic distribution matches production
from scipy.stats import wasserstein_distance
from collections import Counter

def fidelity_score(synthetic_traces: list[Trace], anchor_traces: list[Trace]) -> float:
    """Score synthetic set fidelity against production anchor set."""
    synth_tool_freq = Counter(t.tool_name for t in synthetic_traces for t in t.steps)
    anchor_tool_freq = Counter(t.tool_name for t in anchor_traces for t in t.steps)
    all_tools = set(synth_tool_freq) | set(anchor_tool_freq)

    # Wasserstein distance on tool frequency distributions
    synth_vec = [synth_tool_freq.get(t, 0) for t in sorted(all_tools)]
    anchor_vec = [anchor_tool_freq.get(t, 0) for t in sorted(all_tools)]

    wd = wasserstein_distance(synth_vec, anchor_vec)
    # Normalize: 0 = perfect match, 1 = completely disjoint
    max_wd = sum(synth_vec) + sum(anchor_vec)
    return 1.0 - (wd / max_wd if max_wd > 0 else 0.0)

def diversity_score(traces: list[Trace]) -> float:
    """Measure trajectory diversity via tool-pair coverage."""
    pairs = set()
    for trace in traces:
        for i in range(len(trace.steps) - 1):
            pairs.add((trace.steps[i].tool_name, trace.steps[i+1].tool_name))
    # Score against theoretical maximum (every ordered tool pair)
    all_tools = {t.tool_name for trace in traces for t in trace.steps}
    theoretical_max = len(all_tools) * (len(all_tools) - 1)
    return len(pairs) / theoretical_max if theoretical_max > 0 else 0.0
```

### 5. Label per-turn, not per-trajectory

Binary pass/fail per trajectory is insufficient. Trajectory2Task (ACL 2026) shows that per-turn correctness labels enable:

- **Selective amplification** — only correct turns enter SFT; incorrect turns enter DPO as negative examples.
- **Failure localization** — which step in a 15-turn trajectory broke? Point to it, fix the tool description, re-generate.
- **Trajectory quality weighting** — weight gradient updates by trajectory-level correctness ratio, not uniform.

### 6. Test for distribution shift before deploying

After fine-tuning, run a **SynAE-style post-hoc eval** on a held-out real production sample:

```
synth_eval.py --anchor ./production_anchor_100.jsonl \
              --synthetic ./sft_model_outputs.jsonl \
              --metrics validity fidelity diversity
```

If fidelity drops >15% against production anchors, the model has memorized the synthetic distribution, not learned the capability.

## Receipt

> Verified 2026-08-09 — SynAE (arXiv:2605.22564) published by CMU + Microsoft Research; Trajectory2Task (arXiv:2601.20144) published at ACL 2026; ICML 2026 accepted RLAnything + AutoTool (Gen-Verse/Open-AgentRL) with 200K tool-selection trajectories. NVIDIA Jan 2026 result: command-line agents fine-tuned on single 80GB GPU in days via synthetic trajectory pipeline. Agent MarketCap (Apr 2026) confirms synthetic data is now default fine-tuning substrate. Production failures from fidelity/diversity gaps confirmed across multiple practitioner reports. The per-turn labeling + verifiable-back-generation pattern is the state-of-art production approach per Trajectory2Task ACL 2026 results showing consistent improvement across ambiguous, changing, and infeasible intent conditions.

## See also

[S-1037 · The Evaluation Gap](s1037-the-evaluation-gap-when-your-agent-scores-high-and-fails-in-production.md) — benchmark vs. production divergence
[S-1010 · The Agent Eval Stack](s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — eval harness design
[S-2382 · The Tool-Use Hallucination Taxonomy](s2382-the-tool-use-hallucination-taxonomy-stack-when-your-agent-calls-a-tool-that-doesnt-exist-wasnt-meant-for-this-and-wont-solve-it.md) — tool call failure taxonomy
[R-12 · Agent RLVR Training Loop](r12-agent-rlvr-training-loop.md) — RL post-training on synthetic trajectories
[R-13 · Agent Trajectory Synthesis](r13-agent-trajectory-synthesis.md) — synthesis patterns for agent training
