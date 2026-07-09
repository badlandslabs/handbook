# S-862 · The Evaluation Bottleneck — When Your Agent Ships and You Can't Prove It Works

You built the agent. It completes tasks, calls tools, and passes your smoke tests. But you don't know its real failure rate in production, whether it's improving across versions, or whether it's silently degrading under different inputs. You've hit the evaluation bottleneck: the agent shipped, but you can't prove it works — or justify trusting it with higher-stakes work.

## Forces

- **Agent outputs are trajectories, not answers.** A bad step-3 corrupts steps 4–10, but a final-output score misses where the corruption entered. Standard LLM benchmarks measure single prompt-response pairs and miss the cascade.
- **Agents are non-deterministic.** The same agent at `temperature=0` can show 72% variance across runs (research reference from agentrial's README, citing arxiv:2407.02100). One-shot benchmarks give anecdotes, not reliability signals.
- **Existing benchmarks are gamed.** UC Berkeley researchers found all eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) could be exploited to achieve near-perfect scores without solving the underlying task — and over 50% of top-scoring solutions used hardcoded or synthetic patterns unrelated to genuine agent capability.
- **LLM-as-judge has a calibration problem.** Multiple HN practitioners report that LLMs fail as consistent critics — they score inconsistently across equivalent inputs, show positional bias in comparisons, and cannot reliably detect subtle failures. An uncalibrated judge produces confident wrong scores.
- **Operational and quality metrics are inseparable in production.** Cost per task, token efficiency, and latency are first-class evaluation targets alongside accuracy. An agent that achieves 95% accuracy by retrying indefinitely is not a 95%-accurate agent — it's a cost and latency problem.

## The Move

**Build a layered evaluation pipeline that separates trajectory concerns from outcome concerns, runs across multiple trials, and operationalizes the results into CI/CD.**

The three-layer framework that elite teams converge on:

- **System Efficiency layer** — latency at task and span level, tokens consumed, tool call counts, cost per task. Identifies when the agent is becoming less efficient even as "accuracy" holds.
- **Session-Level Outcomes layer** — end-to-end task success (did the agent accomplish the goal?), trajectory quality (did it take a reasonable path?), and rollback/error rate. Catches silent failures that final-output scoring misses.
- **Node-Level Precision layer** — tool selection accuracy, argument correctness per step, step utility, handoff fidelity between sub-agents. Isolates where failures enter the chain.

Run evaluations across multiple trials (minimum 10–100 runs per scenario) and report **confidence intervals, not point estimates**. A 100% pass rate on 1 trial with a stochastic agent is noise.

Use **goldens** (golden reference test cases with known correct outputs) for regression detection alongside LLM-as-judge for open-ended quality scoring. Calibrate the judge: target 0.80+ Spearman correlation with human judgment before trusting its scores. Keep human rubrics on a sampled subset of traces to catch "metric green, user red" failures.

Integrate evals into CI/CD: run on commit (regression), scheduled (drift), and event-driven (pre-deploy). Track cost-per-task and token-per-task trends over time in the same traces used for quality.

## Evidence

- **MIT AI Agent Index (2025):** Documents 30+ SOTA agents and finds that real-time monitoring (latency, token costs, throughput under load), reliability/stress testing, and red teaming are the three production evaluation pillars most teams underspend on. — [aiagentindex.mit.edu](https://aiagentindex.mit.edu/data/2025-AI-Agent-Index.pdf)
- **Hacker News discussion on production AI agents (11 months ago, 128 points):** A practitioner with production AI tool experience argues evaluations are "vital for improving performance" and reports that internal experiments found LLMs were "not good critics" — raising the alarm on uncalibrated LLM-as-judge without empirical grounding. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **agentrial (GitHub, MIT license):** An open-source statistical evaluation framework that specifically addresses the multi-trial gap — runs agents N times, computes Wilson confidence intervals, and attributes failures at the step level (tool-selection, multi-step-task, ambiguous-query). Explicitly calls out that LangSmith requires paid accounts/LangChain lock-in, Promptfoo lacks multi-trial CI support, and DeepEval/Arize lack step-level failure attribution. — [github.com/alepot55/agentrial](https://github.com/alepot55/agentrial)
- **Statsig perspectives (Oct 2025):** Practical evaluation guide recommending crisp task-specific rubrics over generic "quality" goals, operational envelope tracking alongside quality metrics, and CI/CD integration as the production evaluation mechanism. — [statsig.com/perspectives/aigent-evals-performance](https://www.statsig.com/perspectives/aigent-evals-performance)
- **AWS Labs Agent Evaluation (v0.4.1, GitHub):** An open-source framework targeting Amazon Bedrock agents with built-in evaluators for agents, knowledge bases, and Amazon Q Business. Supports CI/CD integration and configurable evaluation targets. — [awslabs.github.io/agent-evaluation](https://awslabs.github.io/agent-evaluation)

## Gotchas

- **Don't trust point-estimate pass rates.** A single-run score on a stochastic agent is an anecdote. Always run multiple trials and report confidence intervals — agentrial and similar tools automate this.
- **LLM-as-judge needs its own evaluation.** Without calibrated correlation to human judgment (target 0.80+ Spearman), the judge is a confident wrong scorer. Build human rubric samples to validate it before trusting.
- **Operational metrics are lagging indicators.** By the time cost-per-task spikes, the root cause may be weeks old. Instrument spans from day one — you can't retroactively measure latency distribution or token budgets.
- **Benchmarks predict benchmark performance, not production performance.** All eight major agent benchmarks are gameable. Use them as sanity checks, not gatekeepers. Goldens and real-traffic sampling are more trustworthy signal for production agents.
