# S-958 · The Agent Evaluation Stack — When Your Benchmark Scores Lie and Your Production Pass Rate Is a Mystery

When your agent scores 96% on the benchmark, ships to production, and immediately starts failing 35% of real tasks — and your monitoring dashboard shows nothing wrong because you're only checking the final message — is the moment you realize evaluation is a systems engineering problem, not a metrics problem.

## Forces

- **Final-answer grading is necessary but insufficient.** The answer can be correct while the trajectory is broken. The agent called the wrong API, read stale data, and got lucky. You only catch this if you evaluate the path, not just the destination.
- **Single-run pass rate ≠ multi-run reliability.** Production agents show ~60% success on a single run, dropping to ~25% across eight runs (Galileo, 2026). A single trial is almost meaningless for reliability assessment.
- **Aggregate metrics mask variance.** A 90% aggregate pass rate might mean 100% on simple tasks and 20% on hard ones. The aggregate hides the failure mode that matters most.
- **LLM-as-judge has systematic biases.** Position bias (favors earlier responses), length bias (prefers longer outputs regardless of quality), agreeableness bias (over-accepts outputs), and family bias (favors outputs from the same model family). Error rates in LLM judges exceed 50% without calibration (Galileo, 2026).
- **Benchmark performance ≠ production reliability.** The "evaluation gap" — difference between benchmark performance and production reliability — is the central unsolved problem. GitHub Copilot shows 55% higher productivity on average, but real-world variance across tasks is enormous.
- **Gartner projects 40%+ of agentic AI projects will be cancelled by end of 2027** — not primarily due to model quality, but due to inability to measure whether they work.

## The Move

Build a three-layer evaluation system that separates outcome quality from trajectory quality from operational health, then run each layer at a different cadence with different tooling.

**Layer 1 — Final-Answer Evaluation (outcomes)**
- Score the last message or end-state against expected result
- Fast, deterministic, CI-friendly
- Covers: correctness, completeness, format compliance
- Insufficient alone: an agent can reach the right answer via a broken path, and a broken path breaks the next user query

**Layer 2 — Trajectory Evaluation (reasoning paths)**
- Score the full execution trace: reasoning steps, tool calls, intermediate state changes
- Catches: wrong tool calls, cascading errors, looping, premature termination, recovery failures
- Core trajectory metrics (per Google Vertex AI): `trajectory_exact_match`, `trajectory_precision`, `trajectory_recall`
- Trajectory match modes: "superset" (agent calls everything reference does, plus extras) vs. "exact" (identical calls in order)

**Layer 3 — Production Monitoring (operational health)**
- Per-turn classifiers scoring each step decision in real traffic
- Targets: <90ms latency per classification (one forward pass)
- Catches: novel failure modes, drift, task-category-specific degradation that batch evals miss
- Runs continuously on production traffic, not just on test datasets

**Evaluation Cadence**
- **Pre-deployment:** Structured test suite (Layer 1 + 2), run on every PR/commit. Offline dataset of known tasks. Reproducible, CI-gated.
- **Pre-release:** Human evaluation on sample of trajectories. Calibrate LLM judges against domain expert grades. Establish baseline human-judge correlation (target: 0.80+ Spearman).
- **Production:** Layer 3 monitoring on live traffic. Alert on drift from baseline pass rates by task category. Flag for Layer 2 re-run when novel failure patterns detected.

**Multi-trial requirement**
- Run each task 3–5+ times. Model outputs vary between trials.
- Report pass rate distribution, not just mean. A 70% mean with a [40%–95%] range means something different than [68%–72%].

**LLM-as-judge calibration**
- Ensemble of multiple judge instances with randomized response order
- Majority vote for final score; minority-veto for safety-critical failures
- Calibrate against 50–100 human-annotated examples before trusting the judge
- Set decoding parameters (temperature, top-p) fixed and consistent across evaluations
- Target: ≥0.80 Spearman correlation with human expert judgment

## Evidence

- **Engineering blog:** Anthropic published "Demystifying evals for AI agents" (Jan 2026) establishing the core vocabulary — Task, Trial, Grader, Transcript, Outcome, Evaluation Harness, Agent Harness. Key finding: "Final-message grading misses the most important question: did the task actually succeed in the environment? An agent may produce a correct-sounding final message while leaving the environment in a failed state." — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Benchmarking report:** SWE-bench Verified (2,294 real GitHub issues) shows top agents resolving 49–55% of issues as of 2025, per the Stanford HAI 2025 AI Index Report. Production reliability sits well below benchmark performance — the "evaluation gap" is not a benchmark quality issue but a distribution shift from controlled eval to real deployment. — [https://www.swebench.com/](https://www.swebench.com/)

- **Open-source framework:** Giskard OSS (Apache-2.0, 5,504 stars) provides multi-turn async testing for agents with modular, lightweight evaluation. v3 is a full rewrite designed specifically for dynamic agent trajectories, not single-response grading. Covers: evals, red-teaming, and automated test generation for agentic systems. — [https://github.com/Giskard-AI/giskard-oss](https://github.com/Giskard-AI/giskard-oss)

- **Research survey:** ACM KDD 2025 survey on LLM agent evaluation identifies a two-dimensional taxonomy: evaluation objectives (behavior, capability, reliability, safety) and evaluation process (interaction modes, datasets, metric computation, tooling). Notes enterprise-specific challenges: role-based data access, reliability guarantees, and dynamic environments that static benchmarks cannot capture. — [https://dl.acm.org/doi/10.1145/3711896.3736570](https://dl.acm.org/doi/10.1145/3711896.3736570)

## Gotchas

- **Stopping at final-answer grading.** This is the most common mistake. An agent can produce a correct output while leaving the environment in a corrupted state (wrong database entries, incorrect file modifications, partial API calls). Layer 2 catches what Layer 1 misses.
- **Trusting a single LLM judge without calibration.** Without checking judge-human agreement on a labeled sample, you measure judge behavior, not agent behavior. Uncalibrated LLM judges have demonstrated 50%+ error rates with systematic biases toward longer and earlier responses.
- **Running one trial per task.** Non-deterministic outputs mean a single run gives you one sample from a distribution. You cannot assess reliability from one trial.
- **Confusing benchmark scores with production reliability.** A 94% score on a saturated benchmark (MMLU, HumanEval) is meaningless for production reliability. Even task-specific benchmarks like SWE-bench show significant evaluation gap when agents hit real production environments. Treat benchmark scores as sanity checks, not deployment gates.
- **Ignoring trajectory when iterating.** Teams optimize final-answer accuracy and accidentally make the agent's reasoning worse. Trajectory metrics are the leading indicator; outcome metrics are the lagging one.
- **No CI integration.** Evaluation that only runs manually before release catches regressions too late. Every agent code change should trigger the eval harness.
