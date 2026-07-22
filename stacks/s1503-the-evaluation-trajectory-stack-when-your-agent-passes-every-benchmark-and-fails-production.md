# S1503 · The Evaluation Trajectory Stack — When Your Agent Passes Every Benchmark and Fails Production

You shipped an agent that scored 94% on your test set. Three users in production found it unreliable within a week. You realized you were measuring the wrong thing.

## Forces

- **Single-score metrics lie** — a pass/fail number on a curated test set tells you nothing about consistency across runs, graceful degradation, or where in a multi-step trajectory the agent breaks down.
- **Standard LLM benchmarks don't apply** — BLEU, ROUGE, and even MMLU measure single-turn accuracy. Agents plan, call tools, maintain state, and propagate errors across steps. None of that shows up in a final-answer score.
- **The reliability cliff** — agents can achieve 60% success on a single run, dropping to 25% across eight runs. Standard benchmarks measure one run.
- **Benchmarks can be gamed** — Berkeley researchers audited eight major agent benchmarks and found every one could be exploited to achieve near-perfect scores without actually solving tasks.
- **Evaluation is expensive and slow** — building a golden dataset requires weeks of SME labeling; teams skip it and ship blind.

## The Move

Measure trajectories, not just outcomes. Build a layered evaluation harness that tests at the step level and the system level, uses production traces as test data, and gates deploys on continuous evaluation.

### Step 1: Separate trajectory metrics from outcome metrics

Trajectory metrics capture the full execution path — reasoning steps, tool selections, intermediate results, token usage. Outcome metrics capture whether the final task completed. You need both to debug failures. Trajectory tells you *where* the agent broke; outcome tells you *if* it broke.

### Step 2: Use code-based graders for deterministic checks, model-based graders for nuanced quality

Code-based graders (exact/regex string match, binary pass/fail, tool-call verification, static analysis) are fast, cheap, objective, and reproducible — but brittle to valid variations. Model-based graders (rubric scoring, LLM-as-judge, pairwise comparison) handle nuance but introduce bias and cost. Prefer code-based for tool correctness and functional outcomes; use LLM-as-judge for tone, style, and contextual appropriateness.

### Step 3: Build a golden dataset from production traces, not handcrafted queries

Databricks and others report that the biggest bottleneck in agent evaluation is test data — specifically, teams spend weeks to months having SMEs annotate evaluation sets. The better approach: capture real production traces (human-approved success cases, failure examples caught in monitoring), then use synthetic data generation (grounded in your proprietary data) to expand edge cases. A golden dataset of 50–100 well-annotated examples is enough to establish a regression baseline.

### Step 4: Run evals at the step level AND the end-to-end level

Evaluate each tool-call decision independently AND the full task outcome. An agent can select the right tool 80% of the time but fail end-to-end because a bad intermediate result propagates. Grade both the individual decisions and the trajectory as a whole.

### Step 5: Calibrate LLM-as-judge against human judgment before trusting scores

LLM judges have documented biases — position bias (preferring first response), self-preference (rating their own outputs higher), verbosity bias (rewarding longer answers). Calibrate by running the judge against a small set of human-rated examples. LangSmith and Braintrust both support this workflow.

### Step 6: Gate deploys on evaluation regressions, not just manual review

Set pass-rate thresholds per scorer (e.g., "tool-call accuracy below 90% → block deploy"). Run evals in CI on every prompt or model change. Track scores over time to detect drift — agents that pass today may regress silently as the world changes.

### Step 7: Monitor online in production, not just offline in development

Offline evals catch regressions before deploy. Online evals (scoring real user interactions in production) catch distribution shift, novel failure modes, and tool API changes. Braintrust calls this "evals in the loop": production traces become test cases, and evals run ahead of every deploy.

## Evidence

- **Anthropic Engineering Blog:** Defines the core vocabulary — tasks, trials, graders, transcripts, outcomes, and evaluation harnesses. Distinguishes code-based graders (fast, deterministic) from model-based graders (nuanced, biased) and recommends using each for what it does well. Emphasizes that "each grader evaluates some portion of either the transcript or the outcome." — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **UC Berkeley RDI (2026):** Audited eight major agent benchmarks with an automated exploit agent and found all could be gamed to 73–100% scores using trivial techniques. Concludes that benchmark scores drive real decisions (model selection, investment) but benchmarks don't reliably measure real capability. Released `benchjack` as an open tool for auditing benchmarks. — [rdi.berkeley.edu/blog/trustworthy-benchmarks-cont](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont)

- **Princeton/arXiv (ICML 2026):** Proposes 12 concrete reliability metrics across four dimensions — consistency, robustness, predictability, and safety — arguing that a single success-rate score obscures critical operational flaws. Evaluated 15 models and found recent capability gains produced only small reliability improvements. — [arxiv.org/abs/2602.16666](https://arxiv.org/abs/2602.16666)

- **Braintrust (2026):** Documents the eval loop pattern: production traces → test cases → offline evals in CI → deploy → online evals in production → updated traces. Core data model: `data + task + scorers`. Differentiates between prototype agents (single-run, outcome-only evaluation) and production agents (multi-run consistency, step-level grading, regression gates). — [braintrust.dev/articles/ai-agent-evaluation-framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)

- **Databricks Blog (2025):** Reports that organizations skip golden dataset creation due to the SME labeling bottleneck. Their synthetic data generation API generates evaluation sets grounded in proprietary data, reportedly reducing the weeks-to-months timeline to hours. Customer case: "accelerating time to production and increasing agent quality while reducing development costs." — [databricks.com/blog/streamline-ai-agent-evaluation-with-new-synthetic-data-capabilities](https://www.databricks.com/blog/streamline-ai-agent-evaluation-with-new-synthetic-data-capabilities)

- **Galileo AI Labs (2026):** Reports that agents can score 60% on a single run but drop to 25% across eight runs — a critical reliability gap that single-run benchmarks miss. Recommends both trajectory and outcome metrics as "first-class evaluation targets." — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Vanity scores** — a 94% pass rate on a curated test set means almost nothing. The test set likely covers scenarios the team already knew how to handle. Measure consistency across runs and performance on adversarial edge cases.
- **LLM-as-judge bias** — judges favor longer answers, first-position responses, and outputs from capable models. Always calibrate against human-rated examples before treating judge scores as ground truth.
- **Frozen benchmarks become useless** — once a benchmark is published, capable agents can learn to game it. Use private evaluation sets drawn from production traces, not public leaderboard benchmarks.
- **Step-level failures are invisible at the outcome level** — an agent that calls the wrong tool but recovers might still produce a correct final answer, masking a latent failure mode. Grade intermediate steps.
- **Evaluation debt compounds** — teams skip evals early because "we're just prototyping." By the time they hit the production wall, they have no baseline to compare fixes against. Invest in evaluation infrastructure from day one, even if minimal.
