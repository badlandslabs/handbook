# S-1412 · The Agent Evaluation Stack — When Your Benchmark Says 87% but Your Users Say It's Broken

Your agent scores well on SWE-bench. Your internal test set passes at 94%. You ship it, and within a week users are escalating failures, the support queue is full, and cost-per-task is 3x the estimate. The benchmark was not lying — but it was measuring the wrong thing. This is the agent evaluation problem: the methods inherited from single-turn LLM testing do not capture what makes an autonomous agent reliable or expensive in production.

## Forces

- **Endpoint scoring misses the path.** An agent can reach a correct answer through a reckless trajectory — hallucinated tool call, lucky retry, ignored constraint. Endpoint pass/fail certifies the answer, not the behavior. Trajectory-level scoring catches 20–40% of regressions that endpoint scoring misses.
- **Harness variance dwarfs model variance.** The same base model placed inside different scaffolds — different retrieval, retry logic, context management — produces 10–20 percentage point swings on SWE-bench. Comparing leaderboard scores without disclosed harness details is meaningless.
- **Non-determinism compounds.** A 50-step trajectory multiplies variance at every branch. A model that succeeds 3/5 times on a 10-step task may succeed 0/5 times on a 50-step version. Single pass/fail metrics are insufficient; `pass@k` with multiple trials is the right primitive.
- **Benchmarks lie about production.** Public benchmarks use clean inputs, predictable tool responses, and controlled environments. Production faces ambiguous requests, flaky APIs, rate limits, adversarial inputs, and cost that accumulates with every step. The lab-vs-production gap is reported at ~37%.
- **LLM-as-judge has systematic biases.** Position bias (preferring responses it saw first), verbosity bias (favoring longer outputs), and self-preference (judging its own outputs favorably) are well-documented. An uncalibrated judge can produce opposite conclusions from a calibrated one.

## The Move

Evaluate the trajectory, not just the output. Combine outcome scoring with process scoring, and build a golden dataset that reflects your actual production distribution.

- **Score on two axes simultaneously.** Outcome: did the task actually succeed? Process: did the agent take a sensible path — right tools in the right order, no hallucinated calls, appropriate retries, efficient use of context? A task that succeeded through a broken path is a regression risk.
- **Use `pass@k` not `pass@1`.** Run each evaluation task k times (k=5–10 is common). Report the fraction of runs that succeeded. A 70% `pass@5` means the agent eventually gets there with retries; a 70% `pass@1` means it gets there reliably on first attempt — these have very different operational implications.
- **Build a golden dataset from production, not synthetically.** Collect real user interactions, especially escalations and failures. These are your highest-signal eval cases. Synthetic data from GPT-4 filling in "typical" scenarios misses the edge cases that actually break production. Real-traffic sampling provides ecological validity synthetic benchmarks cannot.
- **Calibrate LLM-as-judge, then treat it as a measurement instrument.** Use reference anchors (gold examples with known scores), measure inter-rater reliability between judge and human reviewers, track flip rate across judge versions. The 2026 tooling (DeepEval, AgentEval Arena, LLM evaluation system) supports this natively. Never present judge scores as ground truth.
- **Track cost and latency alongside accuracy.** A solution that scores 95% but costs 100x more compute is not production-ready. Set a `max_budget_usd` per task (default ~$0.50 in the tools cited); abort runs that exceed it and flag as errored.
- **Run regression detection across model versions.** Compare baseline run trajectories against candidate run trajectories. Flag statistically significant regressions in step-level metrics (tool-call accuracy, retry rate, context usage) even when final outcome scores are flat. RegressionDetector libraries (open-source) provide significance thresholds and deployment recommendations.
- **Instrument the harness itself as part of the eval surface.** When a run fails, diagnose: model reasoning failure, missing tools, weak skill discovery, brittle web access, or a completion check that is too loose. A single pass rate cannot separate these causes — diagnostic traces can.

## Evidence

- **HN discussion:** Benchmark hacking study (arXiv:2605.03546, cited in HN discussion id=48100868) found models accessed external resources during coding benchmarks at 20–36% "cheating" rates, invalidating clean-environment assumptions for SWE-bench family evals. — [https://news.ycombinator.com/item?id=48100868](https://news.ycombinator.com/item?id=48100868)
- **HN discussion:** Evaluating AGENTS.md paper (arXiv:2602.11988, discussed HN id=47034087) showed developer-provided agent instruction files improve performance by only ~4% on average while increasing inference cost by 20%+. LLM-generated context files had a -3% average effect. Result variation across models is large and inconsistent.
- **HN discussion:** SWE-CI benchmark (arXiv:2603.03823, discussed HN id=47295537) — coding agent evaluated on 100 real-world CI maintenance tasks across 233 days of commit history. Claude Opus 4.6 scored 0.71 vs GPT-5.2 at 0.23. Multiple commenters confirmed harness/prompt variance is the dominant performance variable, not raw model capability.
- **Practitioner blog:** Motomtech eval harness guide (2026) — golden test suites score on traits, not exact outputs. "Did the agent call `lookup_patient` exactly once? Did it never expose SSNs? Did it surface uncertainty when confidence was low?" Trait scoring is the right abstraction for production agent eval.
- **Practitioner blog:** James M "Evaluating Agents in Production" (June 2026) — regression suites that survive shipping must include trajectory-level checks, not just final-answer assertions. Security eval is trajectory eval: an agent that accidentally leaks data on the way to a correct answer is still a security failure.
- **Research guide:** Zylos Research LLM-as-judge patterns (May 2026) — calibration protocols, bias taxonomy, and trajectory-specific scoring frameworks. "The gap between a naively-configured judge and a well-calibrated one is wide enough to produce opposite conclusions about agent quality."
- **Benchmark landscape:** Changegamer "Evaluating AI Agents" (updated July 2026) — verified reference table covering SWE-bench, GAIA, WebArena, TAU-bench, BFCL, OSWorld, MLE-bench, AgentBench. Key insight: `pass@k` reliability metrics required because non-determinism makes single-trial scoring unreliable.

## Gotchas

- **Don't trust leaderboard scores at face value.** SWE-bench leaderboard entries rarely disclose harness details. A 5-point leaderboard gap may be entirely harness variance. The SWE-bench Verified sub-benchmark is more reliable because it uses a human-verified gold standard, but still suffers from data contamination (models trained on public GitHub).
- **Don't skip trajectory scoring to save cost.** Endpoint-only scoring misses 20–40% of regressions in practice. The effort to add step-level assertions is modest and the signal is substantially higher.
- **Don't use your evals dataset for fine-tuning.** This is data contamination in reverse — if you train on your test cases, your eval scores become meaningless. Keep eval and training sets strictly separated.
- **Don't equate benchmark improvement with production improvement.** A benchmark gain of 5pp may reflect harness changes, test set leakage, or lucky variance — not genuine capability improvement. Validate against your golden production dataset before claiming gains.
- **Don't run LLM-as-judge on the full evaluation stream.** Full-stream ensemble judging is cost-prohibitive at scale. Ensemble on flagged cases — low-score outputs, user escalations, novel failure patterns — and use lightweight automated checks (exact-match tool calls, regex constraints, cost limits) for the bulk.
