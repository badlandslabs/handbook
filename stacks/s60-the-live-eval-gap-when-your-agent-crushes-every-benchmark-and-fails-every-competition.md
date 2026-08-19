# S-60 · The Live Eval Gap

> When your agent scores 92% on your internal benchmark and scores 27% in a live competition against an unseen corpus — because your benchmark measured retrieval, not generalization.

## Situation

Your agent scores 85% on OfficeQA Pro. Your QA pipeline validates it. You ship it. Three months later, the Grounded Reasoning Cup (GRC 2026) runs your agent type against OfficeQA Pro V2 — a harder, unseen corpus of U.S. Treasury Federal Accounts — and it scores 27%. The agent was never the problem. The benchmark was measuring retrieval on familiar documents. Live competition measures something completely different: the ability to generalize reasoning to an unfamiliar corpus.

This is the **Live Eval Gap**: a systematic divergence between benchmark performance and real-world generalization that is invisible in any single-benchmark evaluation pipeline.

## Forces

- **The benchmark-corpora conflation**: Most agent benchmarks are single-corpus. You optimize for one document collection and call it "performance." The agent overfits the retrieval surface, not the reasoning.
- **The evaluation-as-development artifact**: When the eval corpus is known during agent development, teams iteratively tune retrieval, prompt, and scaffolding for that specific corpus. The benchmark becomes a training set.
- **The out-of-the-box fallacy**: Frontier models tested on GRC 2026 without agentic scaffolding averaged under 30% on OfficeQA Pro V2. Raw model intelligence does not transfer to corpus-specific retrieval.
- **The generalization floor**: Even well-designed agents in the GRC 2026 competition (11 academic teams + Anthropic mentorship) showed that approaches tuned on OfficeQA Pro did not reliably transfer to OfficeQA Pro V2. Generalization cannot be assumed — it must be engineered and measured.
- **The live-eval cost**: Running live competitive evaluation requires a new, held-out corpus, which is expensive and operationally complex. Most teams cannot afford it until competition time.

## The move

### 1. Design for multi-corpus evaluation from day one

Never evaluate on a single corpus. Split your available documents into at least two disjoint corpora: one for development/validation, one for holdout testing. The holdout corpus should differ in structure, vocabulary, or domain — not just a random split of the same documents.

```
Development corpus → tune retrieval, prompts, scaffolding
Holdout corpus    → final acceptance gate, reported to stakeholders
```

### 2. Measure corpus-shift sensitivity explicitly

Track per-corpus accuracy separately. A large delta between corpora is a signal, not noise:

```python
corpora = ["dev_treasury", "holdout_federal_accounts", "dev_sec_filings", "holdout_earnings"]
for corpus in corpora:
    score = run_agent_eval(agent, corpus)
    print(f"{corpus}: {score:.1%}")

# Flag: delta > 15% = generalization risk
delta = scores["holdout_federal_accounts"] - scores["dev_treasury"]
if abs(delta) > 0.15:
    print(f"⚠ Corpus shift detected: {delta:+.1%}")
```

### 3. Treat the benchmark corpus as a known-adversary

In GRC 2026, Stanford won (69.3%) by treating the evaluation as a generalization test, not a retrieval test. The winning strategy:
- Build corpus-agnostic retrieval (dense + sparse hybrid, not tuned to one document style)
- Validate reasoning chains against authoritative external sources, not just the corpus
- Use cross-document consistency checks (if Treasury Bulleting X references a figure from Y, verify Y exists)

### 4. Run periodic live eval sprints

Every 4–6 weeks, run a "corpus swap" eval: substitute a new document collection and measure degradation. This is analogous to red-teaming but for retrieval generalization. It surfaces overfitting before a competition — or before production deployment on a new data domain.

### 5. Anchor on generalization metrics, not absolute scores

An agent at 65% on an unfamiliar corpus is more valuable than one at 85% on the known corpus. Report both. The generalization ratio is the more meaningful signal:

```python
generalization_ratio = holdout_score / dev_score
# 0.90+ = robust, 0.75–0.90 = acceptable, <0.75 = overfit to dev corpus
```

## Receipt

> Verified 2026-08-18 — Databricks Grounded Reasoning Cup 2026 (Data + AI Summit, Aug 18, 2026) evaluated 11 academic teams building AI agents on OfficeQA Pro, then tested against OfficeQA Pro V2 (90 questions, ~120K pages of U.S. Treasury Federal Accounts). Stanford won at 69.3%. Out-of-the-box frontier models averaged <30%. Key finding: approaches tuned on OfficeQA Pro did not reliably transfer to OfficeQA Pro V2 — confirming that single-corpus benchmark optimization is a systematic distortion of real agent capability. Cross-referenced against S-2649 (Evaluation Mirage) and S-818 (Longitudinal Eval): both address temporal eval drift but not corpus-shift generalization.

## See also

- [S-2649 · The Evaluation Mirage](stacks/s2649-the-evaluation-mirage-stack-when-your-agent-passes-every-test-but-fails-in-production.md) — evaluation passes but world state unchanged
- [S-818 · The Longitudinal Agent Eval Stack](stacks/s818-the-longitudinal-agent-eval-stack-continuous-regression-detection-in-production.md) — temporal regression, not corpus-shift
- [S-825 · The Trace-Eval Gap Stack](stacks/s825-the-trace-eval-gap-stack-knowing-when-your-agent-is-lying-to-you.md) — knowing when your agent lies about success
- [S-829 · The Eval-First Stack](stacks/s829-the-eval-first-stack-when-you-dont-know-if-your-agent-is-working.md) — building eval before the agent
