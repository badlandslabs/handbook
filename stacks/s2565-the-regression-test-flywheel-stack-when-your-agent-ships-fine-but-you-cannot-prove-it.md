# S-2565 · The Regression Test Flywheel — When Your Agent Ships Fine But You Cannot Prove It

You deployed a new prompt. Your agent completes tasks and responds correctly — in your head. You have no way to know if it is actually better, the same, or quietly worse across your full task distribution. You are shipping on vibes. This stack closes that gap: a production → eval → CI pipeline that turns every real failure into a durable regression test, so you can make a provable claim about quality before shipping.

## Forces

- **AI quality is not binary.** An agent can produce a correct answer through a catastrophically wrong reasoning path — or produce a subtly wrong answer that looks right. Final-output checks miss both failure modes.
- **Synthetic test suites plateau.** Hand-crafted eval cases cover what engineers anticipated. They have near-zero coverage of what users actually do to your agent in production.
- **The most valuable test case is one you cannot invent.** Real user inputs surface the failures you never imagined: Unicode names, adversarial prompts, null fields, context limit surprises. These are the highest-signal cases and they only exist in production.
- **Eval suites rot.** An eval set that never updates from production becomes less representative over time. Without a mechanism to ingest real failures, the suite diverges from reality and provides false confidence.
- **Trajectory and output are different eval surfaces.** 17.14% of agent failures are step repetitions; 13.98% are reasoning-action mismatches — both slip past output-only checks ([Augment Code, 2026](https://www.augmentcode.com/tools/best-ai-agent-evaluation-tools)).

## The move

The flywheel: **production failure → trace → golden test case → golden dataset → CI gate → deploy with confidence.** Each rotation makes the eval set more representative and the release gate tighter.

**1. Instrument every agent run.** Capture full trajectories: tool calls, arguments, intermediate outputs, and final results. This is not logging — it is structured trace capture at the step level. Platforms like Arize Phoenix, Braintrust, and LangChain tracing provide this out of the box. GitHub Copilot's agentic harness uses SWE-bench Verified (500 human-validated bug-fix tasks) as a trajectory benchmark, normalizing on tool selection, context usage, and reasoning effort ([GitHub Copilot engineering post, 2026](https://github.blog/ai-and-ml/github-copilot/evaluating-performance-and-efficiency-of-the-github-copilot-agentic-harness-across-models-and-tasks)).

**2. Route low-confidence traces to human review.** Not every failure is obvious from a score. Annotation queues that route low-confidence cases to human labelers — whose labels feed back into evaluator calibration and regression datasets — close the loop between human judgment and automated scoring ([Arize AI, 2026](https://arize.com/blog/the-best-eval-harness-for-production-ai-a-comparison)).

**3. Convert production failures into golden test cases.** The highest-value regression test dataset is not hand-crafted — it comes from production. Every real failure is an authentic edge case with a concrete definition of "broken" that synthetic generation cannot replicate. The trace captures the exact input, trajectory, and wrong output; the human review adds the correct output label. This is the golden dataset entry ([Arthur.ai, 2026](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)).

**4. Evaluate at trajectory level, not just output level.** Check *how* the agent reached its answer, not just whether the answer is right. Step-level eval catches: wrong tool selection, premature termination, hallucinated intermediate facts, and repetition loops — all invisible in end-to-end output checks. DeepEval v3.0 (2025) introduced component-level evaluation specifically for this: evaluate individual function calls and tool selections, not just the final response ([DeepEval v3.0 release notes, 2025](https://github.com/confident-ai/deepeval/releases/tag/v3.0)).

**5. Wire the golden dataset as a CI release gate.** Run regression tests against candidate prompt changes and model swaps. Block deploys that regress on known failure cases. GitHub Copilot blocks deploys on SWE-bench regression; the harness fails the candidate if trajectory correctness drops. Braintrust frames this as: "a score that doesn't drive an action is just a number on a dashboard" — the action being a CI gate or human review queue ([Braintrust, 2025](https://www.braintrust.dev/articles/how-to-eval)).

**6. Make the flywheel automatic, not ritual.** The loop must run continuously: production traces → automated clustering → eval scoring → golden dataset auto-update → CI. The manual parts (human review of ambiguous traces) should be the exception, not the process. AI-assisted experiment workflows — where a copilot proposes, tests, and iterates on fixes targeting a specific eval threshold — reduce human cycle time ([Arize AI, 2026](https://arize.com/blog/improve-ai-agents-traces-evals-harness/)).

## Evidence

- **Engineering post:** GitHub Copilot's agentic harness benchmarks use SWE-bench Verified for trajectory correctness, with a 2-hour timeout per run and normalized metrics for context window, reasoning effort, tool selection, and MCP server usage. A regression on this benchmark is a release gate. — [GitHub Copilot engineering blog](https://github.blog/ai-and-ml/github-copilot/evaluating-performance-and-efficiency-of-the-github-copilot-agentic-harness-across-models-and-tasks)

- **HN community:** "Ask HN: How are you testing AI agents before shipping to production?" surfaced 7 failure modes with a community consensus that teams test correct output and edge inputs but almost no one systematically tests cascade failures, context limit surprises, or tool-call correctness before shipping. One team had built 50+ test cases across identified failure categories and noted the gap. — [Hacker News, May 2025](https://news.ycombinator.com/item?id=47325105)

- **Industry survey:** A December 2025 survey of teams using proprietary eval sets found that eval sets built from real production failures had significantly higher detection rates for regressions than synthetically generated sets. Source: [GettIA, May 2026](https://www.gettiaconsulting.com/en/actualites/evaluer-agent-ia-production-eval-sets-monitoring)

## Gotchas

- **Eval saturation is real.** A suite at 100% tracks regressions but gives zero signal for improvement. Rotate in new production failure cases to keep the suite fresh and representative of the actual input distribution.
- **LLM-as-judge has calibration drift.** Using an LLM to score outputs introduces a second model whose own quality drifts. Re-calibrate judges against human-annotated samples periodically; do not assume a judge score is ground truth.
- **Synthesized golden outputs are not golden.** A human labeling the correct output from a production failure trace is ground truth. A model predicting what the correct output should be is just another model — it can be confidently wrong.
- **Trajectory-level eval multiplies your test surface.** A 10-step agent has exponentially more failure modes than a single-turn LLM call. Budget evaluation time accordingly; one trajectory-level test is worth more than ten output-level tests.
- **CI gates that always pass are theater.** If your regression suite runs on every deploy but never blocks one, it is a reporting tool, not a quality gate. Set and enforce thresholds that actually fail candidates.
