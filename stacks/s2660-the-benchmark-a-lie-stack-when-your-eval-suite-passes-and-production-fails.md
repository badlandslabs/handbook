# S-2660 · The Benchmark A-Lie Stack — When Your Eval Suite Passes and Production Fails

Your agent scores 87% on your internal benchmark. You ship it. Three days later your users are filing bugs, your cost has tripled, and your agent is stuck in loops generating confident nonsense. The benchmark said it was good. The benchmark was lying — because the benchmark was never measuring what actually breaks in production. Lab evals are built for static, single-turn, accuracy-on-curated-datasets. Production agents are dynamic, multi-step, cost-sensitive, and subject to compounding failures that only emerge over time.

## Forces

- **Lab evals measure the wrong thing.** Benchmarks like HELM, MT-Bench, AgentBench, and BIG-bench evaluate task completion accuracy in controlled, episodic settings. They don't model compounding decision errors, tool failure cascades, or output drift over long horizons — the exact failure modes that surface in production.
- **Standard metrics miss 4 of 7 production failure modes entirely.** Research at billion-event scale found that conventional evaluation frameworks fail to detect the majority of real-world failure categories. They catch obvious crashes, not silent integrity failures.
- **A 70% agent that works reliably beats an 80% agent that is unpredictable and expensive.** Enterprise practitioners consistently prioritize operational stability over peak accuracy. Benchmarks reward the latter.
- **Cost is invisible in most evals.** Leading agents show 50x cost variation ($0.10–$5.00 per task) for similar accuracy. An eval that doesn't track cost-per-task is measuring half the system.

## The move

Don't evaluate your agent — evaluate the trajectory. The pattern is to shift from output-scoring to **trajectory-level, multi-dimensional evaluation** that accounts for cost, latency, reliability over time, and failure recovery — not just final correctness.

**Specific tactics:**
- **Score trajectories, not final outputs.** Measure the full decision path: was each step justified, was the tool choice appropriate, did the agent recover from failures, did cost stay within budget? A correct answer via a broken process is a failure.
- **Track the CLEAR dimensions.** Add Cost, Latency, Efficacy, Assurance, and Reliability to your eval rubric alongside accuracy. Enterprise practitioners call this the CLEAR framework — a single accuracy score conflates systems with vastly different operational profiles.
- **Build for failure mode detection, not just success detection.** Inject tool failures, partial outputs, and timeout conditions into your eval harness. Test whether your agent detects and recovers from: truncated JSON, empty responses disguised as success, cascading sub-agent failures, and silent quality degradation.
- **Set cost-per-task gates.** Cap eval budgets per task and fail agents that exceed them, even if the output is correct. A solution that costs 50x more than a simpler one is not a better solution.
- **Evaluate over time, not just in isolation.** Run agents through extended multi-session sequences and check for decision drift, memory degradation, and compounding errors that don't appear in single-turn tests.

## Evidence

- **arXiv paper (2026):** The production eval framework by Mukund Pandey identifies seven failure modes unique to production agentic systems — including tool parameter hallucination, execution loop accumulation, and context window poisoning — that standard benchmarks fail to detect. Standard metrics miss 4 of 7 failure modes entirely and detect 3 others only after lag of multiple evaluation cycles. — [arxiv.org/abs/2605.01604](https://arxiv.org/abs/2605.01604)
- **arXiv enterprise eval paper (Nov 2025):** Sushant Mehta's CLEAR framework study documents 50x cost variation between agents with similar accuracy scores, and finds that multi-agent coordination achieves 90% goal success rates versus 53–60% for single agents — but only when evaluated on reliability and cost metrics, not just accuracy. — [arxiv.org/html/2511.14136v1](https://arxiv.org/html/2511.14136v1)
- **Industry engineering post (Mar 2026):** Harsh Rastogi, AI Product Engineer at Modelia.ai and Asynq.ai, describes a candidate evaluation agent that passed internal benchmarks but in production hallucinated tool parameters, got stuck in loops, and cost 3x the budget — and an image generation agent that approved obviously flawed outputs because it optimized for workflow completion over quality. The fix was trajectory-level eval with injected failure cases. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **HN discussion (2025):** Practitioners on Hacker News report that the "reviewer/worker pipeline" pattern — where a reviewer agent validates worker outputs — commonly fails through cascading context drift, where each agent in the chain slightly misunderstands the task and by the time the reviewer validates, it's checking the wrong thing. Standard benchmarks don't test this. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **A high benchmark score with no cost metric is half a measurement.** Cost-per-task gates catch expensive agents that inflate their accuracy through brute-force retries and over-generation.
- **Output accuracy doesn't predict trajectory quality.** An agent can reach a correct answer via a catastrophically bad process (infinite loops caught externally, hallucinated parameters that happened to work, cost overruns absorbed silently). Score the path, not just the destination.
- **Single-session evals miss drift.** Failure modes like context window poisoning, memory degradation, and compounding decision errors only surface across multiple sessions. Run extended eval sequences, not just one-shot tests.
- **Injecting failure cases feels artificial — it's not.** Real production failures are precisely the truncated JSON, silent rate-limit empty responses, and sub-agent timeouts that eval harnesses rarely simulate. Add chaos injection as a first-class eval step.
- **Don't trust your eval harness to be unbiased.** If your eval dataset was generated by the same model class you're evaluating, expect systematic overestimation of quality. Use out-of-distribution eval cases for honest measurement.
