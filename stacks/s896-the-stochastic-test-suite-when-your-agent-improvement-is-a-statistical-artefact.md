# S-896 · The Stochastic Test Suite — When Your Agent Improvement Is a Statistical Artefact

You ran your "improved" agent against your eval suite and got 87%. You shipped it. Three days later, the production failure rate was identical. You re-ran the same eval: 79%. Your agent didn't change. The variance is the point. Agents are stochastic — the same input can produce different outputs, different tool sequences, different outcomes. A single eval run tells you almost nothing. This is the stochastic test suite problem, and it breaks most agent evaluation efforts before they begin.

## Forces

- **Stochastic output is architectural, not incidental.** Unlike deterministic software, an agent with the same input can take a different trajectory on different runs. A 90% pass rate on 10 runs means nothing statistically — you need enough runs to separate signal from noise.
- **Traditional unit tests are useless here.** Exact-match and regex-based checks catch the wrong failures and miss the ones that matter. An agent that "passes" by returning the right data in the wrong order, via the wrong tool, after two unnecessary retries is scored as correct by a traditional test.
- **Single-dimensional accuracy metrics lie about production readiness.** A task-completion metric alone doesn't capture cost, latency, safety, or whether the agent took a wildly inefficient path to arrive at the right answer. The most dangerous agent is one that usually succeeds expensively.
- **Evals are only as good as their test cases.** Synthetic test cases written by engineers who haven't seen production failures miss the failure modes that actually matter. Real production traces — the actual edge cases that broke last Tuesday — are the gold standard eval input, but most teams don't capture them.

## The move

**Build a production-grounded eval pipeline with three tiers, tracked trajectories, and enough runs to matter.**

- **Capture from production first.** Instrument your live agent with OpenTelemetry traces. When a task completes — success or failure — store the full trajectory (input, tool calls, intermediate steps, final output, cost, latency). These become your eval seed cases, not synthetic prompts.
- **Run deterministic gates before LLM-as-judge.** Check exact-match requirements (did the right tool fire? were required arguments present? did the output schema match?) with fast, free checks. Only escalate to LLM-as-judge for quality dimensions that require judgment: helpfulness, reasoning soundness, safety, brand alignment.
- **Target 30–50 real production cases minimum.** From these, curate a golden eval set. Supplement with adversarially generated cases from red-teaming sessions, but weight production cases higher in your score — they reflect what users actually experience.
- **Run evals across multiple seeds.** For critical deployment gates, run each test case 3–5 times with temperature > 0 and report mean + variance. A "95% pass rate" with 30% variance across runs is a red flag — your agent is unreliable, not excellent.
- **Use trace-level scoring, not just outcome scoring.** Score both the final answer and the trajectory: did the agent use the right tools in the right order? How many unnecessary steps or retries occurred? An agent that gets the right answer after five wasted tool calls has a different production profile than one that gets there in one clean step.
- **Calibrate your LLM judge against human labels.** Run a sample of 20–50 eval cases through human review. Target 0.80+ Spearman correlation between judge scores and human scores before trusting the judge at scale. Without calibration, you're flying blind on automated quality gates.
- **Evaluate at three lifecycle points.** Before deploy (regression gate in CI), after deploy (shadow mode on live traffic), and on a schedule (nightly or weekly to catch drift as models or prompts change).

## Evidence

- **Engineering blog — Confident AI (DeepEval):** Task completion alone misses half the failure modes — trace-level metrics (tool correctness, argument accuracy, step efficiency, planning quality) are what separates a production-ready agent from a demo that works once. They recommend evaluating at end-to-end, trajectory, and component levels. — [https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **Research paper (Zheng et al., NeurIPS 2023):** LLM-as-a-judge agrees with human reviewers ~85% of the time — higher than the agreement rate between two human reviewers on the same task. This validates LLM-as-judge as a viable scale mechanism, but only with careful rubric design, few-shot examples, and structured JSON outputs that force evidence-based reasoning before scoring. — [https://proceedings.neurips.cc/paper/2023/file/91f18a1287b398d378ef22505bf41832-Paper-Datasets_and_Benchmarks.pdf](https://proceedings.neurips.cc/paper/2023/file/91f18a1287b398d378ef22505bf41832-Paper-Datasets_and_Benchmarks.pdf)
- **HN discussion thread (roadside_picnic, Aurornis):** "If you don't have evals, you really don't know if you're moving the needle at all." Senior HN contributors confirm evals are a core part of any production LLM team — without them, a prompt tweak may pass casual review but introduce silent regressions. — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **Benchmark — SWE-bench Verified (OpenAI):** Real-world coding agent evaluation via SWE-bench uses a human-validated test harness to prevent benchmark contamination — demonstrating that eval integrity requires curated, production-derived test cases rather than synthetic prompts. — [https://openai.com/index/introducing-swe-bench-verified](https://openai.com/index/introducing-swe-bench-verified)

## Gotchas

- **Synthetic test cases drift from reality.** Cases written by engineers miss edge cases that only appear in production. Capture real traces, not just engineer intuition.
- **A green eval with a lenient judge is worse than no eval.** An uncalibrated LLM judge that scores everything 4.5/5 will give you false confidence. Calibrate against human labels before trusting automated quality gates.
- **Variance across runs is a production concern, not a measurement artifact.** If your agent scores 60–90% across 5 runs on the same input, that 30-point spread is real — it means users are having inconsistent experiences. Treat it as a reliability metric, not a noise problem.
- **Single-dimension accuracy is the trap that kills production deployments.** An agent that's 99% accurate but costs $4/task and takes 45 seconds per request isn't production-ready. Track cost-per-task and latency alongside quality scores.
