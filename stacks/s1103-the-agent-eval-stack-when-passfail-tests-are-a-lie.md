# S-1103 · The Agent-Eval Stack — When Pass/Fail Tests Are a Lie

You shipped your agent. All tests pass. Production is on fire. This is the moment most teams realize their eval strategy was theater.

## Forces

- **The output is not the product.** With single-LLM apps, you score input→output. With agents, the trajectory *is* the product — every tool call, every intermediate reasoning step, every state mutation. A correct final answer from broken reasoning is still a failure waiting to happen.
- **LLM judges echo the agent.** Your judge and your agent share the same blind spots. An agent that hallucinates confidently will often find a judge that rates the output high. Human review scales poorly, but automated judges alone create an echo chamber.
- **Benchmarks are broken.** UC Berkeley researchers audited eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found teams achieving near-perfect scores on benchmarks while solving zero real problems. One team gamed 890 tasks with a single character change.
- **Soft failure tolerance is non-negotiable.** Agents are non-deterministic. Identical inputs produce different execution paths. Binary pass/fail in CI/CD is a blunt instrument — you need thresholds and trajectory-level scoring.

## The Move

**Layer three evaluation systems, then wire the feedback into code changes.**

1. **Golden dataset first.** Curate 50–100 representative tasks with known expected outcomes. This is your regression anchor. Run it before every deployment, after every model update, and whenever you modify the agent's tools or prompts.

2. **Score every span, not just the final output.** Evaluate the trace: tool selection correctness, intermediate reasoning quality, plan adherence, and whether the agent follows through on its own plans. DeepEval's `TaskCompletionMetric`, `ToolCorrectnessMetric`, `PlanQualityMetric`, and `PlanAdherenceMetric` are the canonical breakdown. AWS's Agent-EvalKit evaluates the full execution path — which tools were called, what data was returned, whether the response faithfully reflects that data.

3. **Combine deterministic gates with rubric scores.** Deterministic code-based evaluators catch format and criterion violations fast and reproducibly. LLM-as-judge rubric scores catch nuanced quality variation that rules can't capture. Use both.

4. **Calibrate your judge against human labels.** Run a slice of traces through domain experts periodically. Track where the judge diverges. This is not optional — judges have systematic biases (preferring longer answers, more confident-sounding outputs). Anthropic's engineering guide recommends this as a core practice.

5. **Wire evals into CI/CD with soft thresholds.** Hard fail on regressions in core flows (safety, correctness). Soft fail with alerting for degrades in quality metrics. Evaluate asynchronously — scoring runs after the agent responds, adding no latency to the user-facing path.

6. **Treat evaluation as continuous, not a gate.** Run a rolling sample of production traffic through eval scoring. Set anomaly thresholds that trigger deep-dive reviews. Label Studio's guidance: scale human review by transforming nested JSON trace data into visual decision trees for expert review.

## Evidence

- **Benchmark critique:** UC Berkeley researchers found 8 major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) achievable with minimal real work — gaming 890 tasks with a single character change — while systems achieved 100% scores solving zero genuine problems. — [Zylos Research, 2026-05-13](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Frameworks in production:** AWS Agent-EvalKit (Apache 2.0, 2026) evaluates agent traces by examining tool call sequences and whether responses faithfully reflect retrieved data — not just final output correctness. Anthropic's Claude Agent SDK exposes `PreToolUse`, `PostToolUse`, and `SubagentStop` lifecycle hooks for instrumenting eval at every step. — [AWS ML Blog, 2026-06-11](https://aws.amazon.com/blogs/machine-learning/evaluate-ai-agents-systematically-with-agent-evalkit)
- **The echo chamber problem:** Label Studio (2026) documents that automated LLM judges share the blind spots of evaluated agents, and that correct final outputs frequently mask broken reasoning paths. Their recommendation: scale human review via visual trace trees, and use soft failure thresholds in CI/CD rather than binary pass/fail. — [Label Studio Blog, 2026-03-25](https://labelstud.io/blog/how-to-evaluate-ai-agents-in-production)
- **Three-layer architecture:** The dominant pattern from multiple practitioners (Label Studio, Braintrust, Langfuse docs) is offline regression suites + shadow/online scoring + periodic human calibration. Braintrust implements this as trace classification with configurable sampling rates per flow criticality. — [Braintrust Docs, 2026](https://www.braintrust.dev/articles/continuous-evaluation-ai-agents-trace-classifications-2026)
- **Metric breakdown:** DeepEval evaluates six agent dimensions: task success, tool selection correctness, tool call argument accuracy, intermediate reasoning quality, plan adherence, and cost efficiency. Plan adherence specifically catches "correct answer through wrong reasoning" — the most dangerous class of agent failure. — [DeepEval Guides, 2025](https://deepeval.com/guides/guides-ai-agent-evaluation-metrics)

## Gotchas

- **Don't judge only the final output.** A surface-level output check misses hallucinated intermediate logic, wrong tool sequences, and reasoning paths that happen to arrive at correct answers by accident. Evaluate the entire trajectory.
- **Don't trust benchmarks as quality signals.** Static benchmarks (especially public validation sets) are prone to contamination and leaderboard hacking. Use them as capability probes, not targets to optimize. If a prompt change improves benchmark scores but isn't explainable by a general capability improvement, it's a red flag.
- **Don't hard-fail on non-deterministic agents.** Set thresholds (e.g., pass if ≥80% of runs succeed). Hard binary gates on stochastic systems produce false regressions and alert fatigue.
- **Don't skip judge calibration.** LLM judges systematically prefer longer answers and more confident-sounding outputs. Run them against human-labeled ground truth periodically or you will drift.
- **Don't build evals after the agent.** Instrument evaluation hooks (`PreToolUse`, `PostToolUse`) during agent development, not after. Retrofitting eval into an agent that wasn't instrumented is significantly harder.
