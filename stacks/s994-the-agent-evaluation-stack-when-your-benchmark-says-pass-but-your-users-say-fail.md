# S-994 · The Agent Evaluation Stack — When Your Benchmark Says Pass but Your Users Say Fail

You shipped an agent. The demo looked great. Your internal test set scores 94%. Then it hits production and customers complain about wrong flights booked, files deleted, or answers that sound confident and are completely wrong. The problem isn't the agent — it's that you were measuring the wrong thing.

## Forces

- **pass@k hides the failure rate.** A 70%-per-trial agent has pass@3 ≈ 97% and pass^k ≈ 34%. The metric that looks good is the one that misleads you about what users actually experience.
- **Golden datasets rot.** Evals drawn from the original product spec don't reflect how users actually phrase requests. Teams report their agent passing 98% of golden tests and 60% of real traffic — the dataset has no coverage of the real distribution.
- **LLM-as-judge amplifies whatever bias it starts with.** An uncalibrated judge will confidently reward confident wrong answers. Generic evaluators fail to capture task-specific quality; custom evaluators per task type outperform them significantly.
- **Model drift is silent.** A Stanford/UC Berkeley study documented GPT-4's accuracy on a specific task dropping from 84% to 51% between March and June 2023 with no version change communicated. The model name was identical; the behavior was not.
- **Eval pipelines are an afterthought.** 74% of teams running AI agents in production lack any automated regression test before deployment.

## The move

Measure consistency, not just accuracy. Use pass^k as your primary reliability metric, build a golden dataset from real failures, run two-tier grading (code-based + calibrated LLM judge), and track longitudinal drift with automated gates.

**Reliability first:**
- Track pass^k (consistency across k trials) as primary metric, not pass@k (best-of-k)
- Also measure: cost per task (token count × rate), step-level latency, and tool-call accuracy
- A pass@1 drop of even 5% is a blocking regression — alert on it

**Build a living golden dataset from failures:**
- Start with 50 high-quality examples from real production failures, not synthetic happy paths
- Amplify via synthetic generation: seed with human-curated cases, generate variants from documentation, verify with subject-matter experts
- Version the dataset in git; tag each version to the agent and prompt version it was tested against
- The minimum viable dataset for judge calibration is 100 labeled examples

**Two-tier grading strategy:**
- **Code-based graders:** deterministic checks (was the right API called? with the right arguments? did the output parse correctly?) — fast, cheap, no calibration needed
- **Model-based judges:** for subjective quality — must be calibrated against 100+ human-labeled examples; require Cohen's κ ≥ 0.6 vs human reviewers before use; use task-specific judges, not generic scorers
- Avoid single-judge architectures for high-stakes decisions; panel-of-judges approaches (multiple judges with distinct criteria) better approximate human preference

**Continuous, longitudinal tracking:**
- Run the full eval harness on every PR (like unit tests) — block deploys if pass@1 drops ≥5%
- Track rolling-window scores over time; silent regressions (18-point accuracy drops with green dashboards) are the failure mode to prevent
- Separate "will this break in prod?" from "is this better than last month?" — consistency and capability are different metrics

**CI gate structure (minimum viable):**
- Unit: per-step correctness (did the agent call the right tool?)
- Integration: end-to-end task completion (did the agent achieve the user's goal?)
- Regression: full golden dataset run — pass/fail gate on pass@1, not pass@k
- Budget: cost-per-task guardrail — flag if >1.5× baseline

## Evidence

- **HN thread — "Evaluating Agents":** Practitioner thread on eval challenges. Key insight: end-to-end binary success criteria (did the agent meet the user's goal?) outperforms partial-credit scoring early on. Feed failure traces back into prompt/toolchain optimization. — https://news.ycombinator.com/item?id=45121547
- **DigitalApplied — "Building an AI Agent Evaluation Pipeline: 2026 Methodology":** pass@3 ≈ 97% vs pass^3 ≈ 34% for a 70%-per-trial agent. Documents the calibration requirement for LLM judges: minimum 100 human-labeled examples, κ ≥ 0.6 threshold, two grader classes (code-based deterministic + model-based flexible). — https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology
- **Zylos Research — "AI Agent Longitudinal Evaluation":** Documents GPT-4 accuracy drop from 84% to 51% between March–June 2023 (Stanford/UC Berkeley study) with no version change. Argues point-in-time benchmarks answer the wrong question — longitudinal tracking of capability is required. — https://zylos.ai/en/research/2026-04-14-ai-agent-longitudinal-evaluation-production-regression
- **arxiv 2511.14136 — "Beyond Accuracy: CLEAR Framework":** Across 300 enterprise tasks, accuracy-only optimization produces agents 4.4–10.8× more expensive than cost-aware alternatives with comparable performance. Expert evaluation (N=15) confirms CLEAR better predicts production success (ρ=0.83) vs accuracy-only (ρ=0.41). — https://arxiv.org/html/2511.14136v1
- **LangWatch — "LLM-as-a-Judge: Panel of Judges":** Generic foundational model evaluators consistently fail on task-specific quality; task-specific custom evaluators significantly outperform them. Panel-of-judges approach creates better alignment with human preference than single-judge setups. — https://langwatch.ai/blog/the-panel-of-judges-approach-using-llm-as-a-judge-to-approximate-human-preference
- **Velocity Software — "AI Agent Continuous Evaluation in 2026":** 74% of teams running agents in production lack automated regression tests. Documents three root causes of eval pipeline failure: stale golden datasets, drifting grading rubrics, and missing longitudinal tracking. — https://www.velsof.com/ai-automation/ai-agent-continuous-evaluation
- **HN — "What broke when I tried to evaluate an AI agent in production":** Benchmark-style eval approaches break in production because production inputs don't match synthetic benchmarks; real traces and manual inspection remain necessary. — https://news.ycombinator.com/item?id=47416033

## Gotchas

- **pass@k is not your reliability number.** It tells you the best possible outcome over k attempts. Your users get one attempt. Use pass^k or pass@1 as your production gate.
- **An uncalibrated LLM judge is a liability.** It will confidently score wrong answers high if not validated against human-labeled examples. The calibration step is not optional.
- **Golden datasets require active maintenance.** Cases drawn from the product spec don't reflect how users actually ask questions. Mine failures from production, not from the backlog.
- **Silent drift is the default.** Model providers update API backends without notice. Without rolling-window evaluation, you discover degradation in post-mortems, not before users are affected.
- **Cost-per-task guardrails are easy to skip and expensive to skip.** A single prompt change can increase token usage by 40%. Measure it per step.
