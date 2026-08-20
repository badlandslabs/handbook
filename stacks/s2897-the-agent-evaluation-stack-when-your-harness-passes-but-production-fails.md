# S-2897 · The Agent Evaluation Stack — When Your Harness Passes but Production Fails

Your benchmark score looks great. Your agent ships. Two weeks later, you discover it has been routing customer complaints to the wrong department with perfect confidence for 14 days straight. The harness passed. The agent never flagged the errors. Standard evaluation methodology — the kind that works for chatbots — does not transfer to agents. Agents fail in ways that don't show up in pass/fail on a final answer.

## Forces

- **Benchmark scores ≠ production reliability.** SWE-bench and MMLU measure narrow capabilities; they say nothing about whether your agent picks the right tool, handles hallucinated parameters, or respects approval gates in a multi-step workflow.
- **Human evaluation dominates but doesn't scale.** 74% of production teams primarily use human evaluation (306 practitioners, 26 domains) — reliable, but the bottleneck that makes iteration painful.
- **Trajectory vs. outcome mismatch.** A binary pass/fail on the final result misses the entire path. The agent can reach the right answer through the wrong process and score 100%.
- **The harness is part of the system.** Scaffold choices — context formatting, time limits, retry policies, when to execute a tool — shift results 10–20 percentage points on the same model and task. You are not benchmarking the model; you are benchmarking the entire system.
- **Non-determinism compounds over long horizons.** A 50-step trajectory multiplies variance. A different branch at step 4 produces a completely different state by step 30. A single run tells you almost nothing about reliability.

## The move

Build an evaluation harness that scores **trajectories, not just outcomes** — asserting expected tool sequences, parameter ranges, and intermediate states — and gate deployment behind it.

**Trajectory-level assertions, not just final-answer grading.** Check that the agent called the right tool in the right order, with parameters within expected ranges, before checking whether the outcome was correct. Wrong sequence + right answer = fail.

**Use production-signal benchmarks as calibration targets.** Match the benchmark to the failure mode you fear:
- SWE-bench / SWE-bench-Verified for code agents
- τ-bench for customer service / tool-dialogue agents
- WebArena / Terminal-Bench for browser / CLI agents
- BFCL for pure function-calling

**Implement pass@k and pass^k, not just pass@1.** pass@1 measures whether the agent can do it at all. pass^k measures whether the agent does it consistently across k attempts. Production reliability = consistency, not capability.

**Calibrate an LLM-as-judge on your specific domain.** General LLM judges drift on domain-specific criteria. Fine-tune the judge with 20–50 hand-labeled examples from your actual production traces. The calibration investment is small; the signal improvement is large.

**Gate deployment on eval regressions, not just eval improvements.** A regression gate (block if score drops >5% from baseline) catches silent degradation that benchmark averages hide. Add cost-per-task and step-count limits as proxy metrics — sudden spikes indicate looping or over-exploration.

**Instrument trajectories for human review.** Store full tool-call traces with input/output snapshots. Route low-confidence trajectories (judge score < threshold) to human review automatically. Don't wait for production failures to find edge cases.

## Evidence

- **ICML 2026 empirical study (MAP):** First large-scale study of production agents — 20 case studies, 306 practitioners, 26 domains. Key findings: 74% rely primarily on human evaluation, 68% of agents execute ≤10 steps before human intervention, 70% use off-the-shelf models with no weight tuning, and reliability (consistent correct behavior over time) is the #1 development challenge. — [arXiv:2512.04123](https://arxiv.org/abs/2512.04123)

- **Anthropic Engineering Blog (HN discussion, ~8 months ago):** "The effort-to-outcome curve is basically exponential — with almost no effort, you can get 70% of the way there." The last 10% requires "hundreds of agents, multiple models, complex evaluation frameworks" costing "several hundred $/run." A reliable harness is the path to closing that gap. — [HN #46081704](https://news.ycombinator.com/item?id=46081704)

- **Sierra τ-bench:** A tool-agent benchmark that evaluates multi-turn collaborative problem-solving with both humans and APIs, requiring agents to follow domain-specific policies. Distinguishes between agents that reach right outcomes through wrong paths vs. agents that reason correctly. Used by enterprise teams to compare agent reliability before production deployment. — [tau-bench.com](https://taubench.com)

- **SWE-bench / SWE-bench-Verified:** Docker-based evaluation harness for code agents solving real GitHub issues. Verified subset (human-validated) more reliably evaluates model capability. Current state-of-the-art: Claude Opus 5 scores 97% on SWE-bench, 91.7% on IOI. The Docker harness is the operational model for reproducible agent evaluation. — [github.com/swe-bench](https://github.com/swe-bench)

- **LLM-as-Judge calibration:** LLM judges are widely used in production agent evaluation but exhibit systematic drift on domain-specific criteria. Fine-tuning with 20–50 domain examples significantly improves calibration. Without this, judge scores can diverge 20+ percentage points from human assessment. — [The LLM Stack - Agent Evaluation](https://prakashkagitha.github.io/llm-stack-book/08-agents-harness/08-agent-evaluation.html)

## Gotchas

- **Benchmark leaderboard rankings ≠ your production performance.** SWE-bench uses Python code in Docker containers. Your agent operates in a custom environment with different tool definitions, context windows, and retry policies. The leaderboard tells you about model capability, not system reliability.
- **pass@1 is not a reliability metric.** An agent that solves 80% of tasks on the first try but fails consistently on the other 20% gets the same pass@1 as one that solves everything eventually. Use pass^k (consistency across k attempts) or trajectory reliability as your primary production metric.
- **Human eval can't keep up with iteration speed.** As you ship faster, human reviewers become the bottleneck. Teams that don't automate trajectory assertions end up either slowing down or shipping blind. Automate the assertions; keep humans for calibration and edge-case discovery.
- **Changing the harness changes the scores.** If you tune your agent against a specific harness and then switch harnesses, scores can shift 10–20 points. Treat the harness as a production dependency, not a throwaway evaluation tool. Version and regression-test the harness itself.
