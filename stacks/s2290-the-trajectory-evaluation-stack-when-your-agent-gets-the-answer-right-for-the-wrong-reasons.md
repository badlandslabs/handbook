# S-2290 · The Trajectory Evaluation Stack — When Your Agent Gets the Answer Right for the Wrong Reasons

Your agent completes a customer refund workflow. The customer gets their money back. Success, right? Except the agent called the wrong policy endpoint, pulled data from the wrong account, and happened to reach a correct-looking answer through a reckless path. It will fail silently the next time the data doesn't cooperate. Endpoint evaluation — did the final answer look good? — would miss this entirely. This is why trajectory evaluation is now the production standard for agentic systems.

## Forces

- **Endpoint scoring certifies answers, not behaviour.** An agent can reach a correct output through a wrong plan, lucky tool selection, or ignored constraints that simply didn't bite this time. Final-answer evaluation gives you false confidence — the 77% failure rate that compounds across a 5-step workflow is invisible if you only look at step 5.
- **Process failures compound.** With each step at ~95% success, a 5-step agentic workflow reaches only ~77% total reliability (0.95^5). A single-step pass/fail metric hides this degradation entirely.
- **LLM-as-judge is useful but has known failure modes.** Position bias, verbosity bias, self-preference, and reference answer anchoring all corrupt judge scores. Using it without calibration is evaluation theatre.
- **Ground-truth datasets are expensive and stale.** Annotated reference datasets for real-world agent tasks require domain experts, get outdated as tools and policies change, and don't capture the long tail of production inputs.

## The Move

Evaluate the full run — every tool call, decision, and intermediate state — not just the final output. Score each layer independently so you can pinpoint exactly where the agent broke.

**Build a two-layer rubric:**

- **Reasoning layer** — Does the plan correctly decompose the task? Are tool selections justified? Are constraints and policies acknowledged?
- **Action layer** — Did the tool calls execute with correct arguments? Did the agent recover from bad tool responses? Did the final state match the user's intent?

**Use trajectory metrics that go beyond pass/fail:**

- **Task success rate** — Did the agent complete the goal?
- **Tool-call accuracy** — Did it call the right tools in the right order?
- **Step efficiency** — Did it take the minimal path, or waste steps on recovery?
- **Groundedness** — Is each claim in the output traceable to retrieved context or tool results?
- **Policy compliance** — Did the agent violate any operational constraints mid-run?

**Minimum viable eval setup (from practitioner reports):** 50–200 real production examples, per-step rubrics, 10+ runs per example, a held-out test set you never tune against, and statistical regression tracking over time.

**Add a replay harness.** Capture agent traces as structured data. Re-run them against new model versions or updated policies without hitting production systems or external APIs. This is the fastest feedback loop for evaluating changes.

**Calibrate LLM-as-judge before trusting it.** Run judge scores against human-annotated samples first. Track agreement rates. Filter for position bias (swap A/B order, check for consistent scoring). Use concrete metrics like groundedness and relevance as anchors rather than open-ended quality scores.

**Integrate into CI/CD.** Treat eval scores as first-class gates — block or flag deployments when trajectory scores drop below threshold. A single aggregate score across your entire agent fleet is a vanity metric; score per agent variant, per workflow, per tool chain.

## Evidence

- **Snowflake Engineering Blog (Nov 2025):** The Agent GPA (Goal-Plan-Action) framework evaluates agents across goals, plans, and actions — surfacing internal errors that endpoint-only evaluation misses. On their benchmark, GPA achieved 95% error detection vs 55% for baseline final-answer evaluation, and 86% error localization vs 49% baseline. Open-sourced via TruLens. — [snowflake.com/en/blog/engineering/ai-agent-evaluation-gpa-framework](https://www.snowflake.com/en/blog/engineering/ai-agent-evaluation-gpa-framework/)
- **James M, Practitioner Blog (June 2026):** "Endpoint evals miss the failure mode that hurts in production — an agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints that did not bite this time." Proposes trajectory rubrics, replay harnesses, and regression suites as the production standard. Minimum viable setup: 50–200 real examples, per-step rubrics, 10+ runs per example. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **GitHub: agent-eval-harness (tkarim45, June 2026):** Open-source harness that measures task success, tool-call accuracy, step efficiency, and cost for tool-using LLM agents. Runs agents over a benchmark with known-correct outcomes and reference tool traces, scores all four dimensions, and provides a trajectory viewer. — [github.com/tkarim45/agent-eval-harness](https://github.com/tkarim45/agent-eval-harness)
- **DeepEval documentation (2025–2026):** Defines AI agent evaluation as measuring reasoning and action layers separately — planning quality, tool selection accuracy, and task completion — so failures can be attributed to the correct layer for targeted fixes. — [deepeval.com/guides/guides-ai-agent-evaluation](https://deepeval.com/guides/guides-ai-agent-evaluation)
- **Hacker News Discussion (July 2025):** Thread on "Principles for production AI agents" surfaced widespread agreement that evaluations are vital, with debate on LLM-as-judge reliability. Commenters noted that "evaluations are vital for improving performance" and that LLM-as-critic has no empirical backing as a standalone judge — calibration against human annotation is required. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **A single trajectory-score number across your fleet is a vanity metric.** Score per agent variant, per workflow, per tool chain. Aggregating hides exactly the signal you need to act.
- **Re-weighting trajectory components without baseline calibration makes historical scores incomparable.** If you must rebalance, fork the metric name or tag the version.
- **LLM-as-judge position bias is real and systematic.** When comparing two outputs, always run A/B and B/A — a judge that consistently prefers the first option will corrupt your measurement.
- **Running evals only in development is not enough.** Production data distribution differs from test sets. Continuous production monitoring with shadow evals is what catches regressions that only appear on real inputs.
- **Security eval is trajectory eval.** NIST's guidance (Jan 2025) treats agent hijacking and constraint violations as trajectory-level failures — you cannot detect them by inspecting final outputs alone.
