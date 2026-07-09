# S-871 · The Trajectory Gap Stack — When Your Agent Passes Every Benchmark and Fails Every Customer

Your agent scores 87% on your internal test set. Your users are filing bugs. The agent reached the right answer through a reckless path — wrong tool first, lucky recovery, hallucinated intermediate claim, ignored a policy constraint. Your benchmark only checked the destination. This is the trajectory gap: the evaluation method measures completion, not correctness of method.

## Forces

- **Benchmarks measure destinations, not journeys.** SWE-bench, GAIA, AgentBench — all score whether the agent reached the goal. A 49% score on SWE-bench Verified tells you nothing about whether the agent got there by reading code correctly or by lucky trial-and-error with leaked test hints.
- **LLM-as-judge creates an echo chamber.** Deploying an LLM judge to score agent outputs means the evaluator shares the blind spots of the evaluated. Correct final outputs routinely mask broken intermediate reasoning and hallucinated tool calls that never got flagged.
- **Production reality doesn't match benchmark inputs.** External dependencies break, URLs go stale, environments differ, and sandbox assumptions collapse. An agent calling `localhost` in a cloud deployment, or getting blocked by Reddit's scraper defenses, fails not because of model quality but because of system integration — and most eval setups never catch these.
- **Non-determinism requires statistical tracking, not pass/fail gates.** Running one eval pass per example and calling it done misses the variance. Agents can pass 90% of the time and catastrophically fail 10% — that 10% might be your healthcare compliance scenario.
- **Per-step failure cascades.** A wrong tool call in step 3 produces garbage context for step 7, which produces a confidently wrong final answer. End-to-end scoring can't root-cause this. DAG-structured step-level evaluation detects these cascades 17× more often than outcome scoring alone.

## The Move

Measure the path, not just the destination. Build an evaluation harness that treats agent quality as a multi-dimensional, continuous measurement problem — not a pass/fail on a curated test set.

- **Capture full trajectories, not just outputs.** Log every tool call, every argument, every intermediate reasoning step, every error recovery. Treat traces as first-class evaluation artifacts.
- **Score at the step level, not the episode level.** Use DAG-structured trajectory evaluation with error propagation tracking. Assign scores to individual nodes (tool call correctness, context relevance, policy compliance) and compute how failures propagate downstream.
- **Build a replay harness.** Once you have captured traces, re-run them against new model versions or policy changes without touching production systems. Enables statistical regression tracking across 10+ runs per example.
- **Combine automated and human evaluation.** LLM-as-judge gives scale and repeatability. Human judgment from domain experts catches what automation misses — tone, trust, contextual appropriateness, and subtle constraint violations. The best pipelines use both, continuously.
- **Track operational constraints as first-class metrics.** Latency, cost per task, token efficiency, tool reliability, and policy compliance aren't afterthoughts. They determine whether a technically capable agent is viable at enterprise scale.
- **Establish a minimum viable eval set.** 50–200 real production examples, per-step rubrics, 10+ runs per example, statistical regression tracking, and a held-out set for unreported generalization. Anything less produces confident wrong answers about agent quality.
- **Use soft failure thresholds in CI/CD.** Because agents are non-deterministic, a single failure in a pipeline shouldn't block a deploy — but a pattern of failures or a statistically significant regression should. Set thresholds based on trajectory quality, not just task completion.

## Evidence

- **Blog post (James M, June 2026):** "Endpoint scoring certifies answers, not behaviour." Documents trajectory-level evaluation practices including per-step rubrics, replay harnesses, and regression suites for multi-step production agents. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **Blog post (Label Studio, March 2026):** Documents the LLM-as-judge echo chamber problem and the shift from single-turn to trajectory evaluation. Reports that 20–40% of regressions are missed by output-only scoring in production agent pipelines. — [labelstud.io/blog/how-to-evaluate-ai-agents-in-production](https://labelstud.io/blog/how-to-evaluate-ai-agents-in-production/)
- **Research paper (arXiv 2604.23581):** DAG-structured step-level evaluation for agentic workflows with error propagation tracking achieves 17× higher failure detection recall than end-to-end evaluation, κ=0.84 human agreement, and 72% root cause accuracy. — [arxiv.org/html/2604.23581v1](https://arxiv.org/html/2604.23581v1)
- **Research summary (Zylos Research, May 2026):** UC Berkeley examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be gamed to near-perfect scores without solving the underlying task. — [zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Hacker News (colinfly, ~March 2026):** Field report from evaluating a production agent with a benchmark-style approach: most failures were system-level — broken URLs dropped score to 22, agent calling localhost in cloud env got stuck at 46, Reddit blocking requests caused dependency failures. Model quality was not the bottleneck. — [news.ycombinator.com/item?id=47416033](https://news.ycombinator.com/item?id=47416033)
- **Article (Towards Data Science, May 2026):** 12-metric evaluation harness from 100+ enterprise deployments across four categories: Retrieval (context relevance, recall, precision), Generation (faithfulness, answer relevance, citation accuracy), Agent (step success rate, tool call accuracy, recovery rate), and Production (latency, cost per task, policy compliance). — [towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents](https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/)

## Gotchas

- **Benchmark leaderboards are not production readiness scores.** An agent scoring 55% on SWE-bench Verified vs 45% tells you almost nothing about which will handle your customer service tickets better. The evaluation gap between lab benchmarks and production is measured at 37%.
- **One eval run per example is statistically meaningless.** Agents are non-deterministic. You need 10+ runs per example to get confidence intervals. Teams that run a single pass and declare victory are measuring noise.
- **Soft CI/CD thresholds are non-negotiable for non-deterministic agents.** Blocking on a single failed run produces brittle pipelines that nobody trusts. Blocking on a statistically significant regression across a distribution of runs produces a system people actually use.
- **Domain expert calibration is required for LLM judges.** Without it, automated judges systematically miss domain-specific constraint violations that look harmless to a general-purpose evaluator.
- **Production eval data goes stale fast.** Agent behavior changes with model updates, prompt changes, and tool schema changes. Your eval set needs a refresh pipeline, not a one-time curation effort.
