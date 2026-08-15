# S-2697 · The Evaluation Flywheel Stack

When your agent works on day one and silently degrades over weeks — and you won't notice until users complain — because you haven't wired production failures back into your test suite.

## Forces

- **Production is the only honest eval.** Synthetic test cases cover what engineers imagined; production failures cover what users actually did. Every failure you don't capture is an edge case you'll hit twice.
- **pass@k hides what pass^k reveals.** Most teams report pass@3 (any of 3 trials succeeds). Production needs pass^k (all of k trials succeed). A 90%-per-trial agent reads as ~100% on pass@3 but only 35% on pass^10. Capability benchmarks don't measure consistency; production demands it.
- **Eval sets go stale.** Production traffic drifts from your calibration set in 4–12 weeks. What users actually ask diverges from what you tested against. Without a refresh mechanism, your eval suite becomes a lagging indicator.
- **Manual annotation is the bottleneck.** Every production trace needs a human label before it becomes a regression test. Teams either annotate everything (expensive) or annotate nothing (eval set atrophies).

## The move

Build a one-way valve from production into your test suite — automatic enough to run continuously, selective enough to avoid noise.

**1. Capture traces at failure boundaries, not all traces.** Instrument your agent to save complete execution traces on: task failure, user escalation, compensation event, or Gateway rejection. Not every run — only runs where something went wrong or a human intervened. This is your primary signal source.

**2. Label traces with the minimum viable annotation.** Each saved trace needs: (a) the input that triggered it, (b) a binary success/fail judgment, and (c) for failures, the root-cause category (wrong tool, bad argument, hallucinated state, context overflow, policy violation). Full human annotation of the "correct" trajectory is optional — binary failure labeling is sufficient to seed regression coverage.

**3. Grow your golden dataset with a production-first policy.** Source cases in this priority order: (1) annotated production failures, (2) human-curated boundary cases from observed failure patterns, (3) adversarial inputs from red-team sessions, (4) public benchmarks for sanity checks. Synthetic/engineer-imagined cases go last.

**4. Wire the dataset into CI as a release gate.** Every model upgrade, prompt change, or tool-modification triggers a full golden dataset run. Any dimension degradation beyond threshold (e.g., 5% drop in task success) blocks the release. This is where most teams fail — they build the dataset but never gate on it.

**5. Detect eval-set drift on a schedule.** Every 30–90 days, compare your golden dataset's input distribution against a sampled slice of current production traces using embedding similarity. If cosine similarity between distributions drops below a threshold, refresh the dataset by sampling and labeling recent production failures. Do not rely on the same eval set for more than 90 days without drift-check.

**6. Measure pass^k, not just pass@k.** Run each task 3–5 times to get a consistency estimate. Report pass@1 (single-trial accuracy) alongside pass^3 (all-3-trials-succeed). If pass@1 is 85% but pass^3 is only 62%, your agent is unreliable regardless of what the single-shot number says.

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" documents the pass@k / pass^k distinction from shipping Claude Code and computer use agents — a 90%-per-trial agent yields 35% pass^10, making consistency the primary production metric. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering blog:** Slava Dubrov's eval pipeline guide describes the trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring loop, with deterministic checks for tool order/arguments/loops and LLM judges only for interpretation-dependent checks calibrated against human labels. — [URL](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites/)
- **Platform blog:** Arthur's regression testing guide makes the case that production failures are superior to synthetic test cases because "broken" is concretely defined (not hypothetical), and documents the loop: production failure → trace → test case → golden dataset → release gate in CI/CD. — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **Don't gate on raw accuracy alone.** A 95%-accurate agent that costs 10× more or takes 3× the steps may be worse for your use case. Include cost-per-task and latency in your regression gates.
- **LLM judges drift.** An uncalibrated judge carries position bias (prefers first/last), verbosity bias (rewards longer answers), self-preference bias (favors outputs similar to its own training distribution), and format bias. Calibrate against human labels before treating judge scores as ground truth.
- **Small golden datasets still have value.** You don't need hundreds of cases to start. 20–50 carefully selected examples from real production failures provide enough signal to iterate early. The set grows; start now.
- **Benchmark scores ≠ production readiness.** SWE-bench (49–55% top resolution as of early 2026) and WebArena measure capability in controlled environments. They tell you if the engine is powerful, not whether your specific agentic system completes your specific workflow in your specific environment.
