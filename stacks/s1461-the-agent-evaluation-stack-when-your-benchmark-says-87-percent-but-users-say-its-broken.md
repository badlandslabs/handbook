# S-1461 · The Agent-Evaluation Stack — When Your Benchmark Says 87% but Users Say It's Broken

Your agent demo works perfectly. Your benchmark reports 87% task completion. Then it ships to production and within days you find it's completing tasks in the demo but silently failing on edge cases — making wrong tool calls, hallucinating from stale context, and costing 4x more per task than budgeted. The benchmark was measuring the wrong thing. The agent looked good because it was evaluated the way you evaluate an LLM, not the way you evaluate a system that takes actions.

## Forces

- **Agents are systems, not models.** LLM evaluation tests a single prompt-response pair. Agent evaluation must test multi-step trajectories where errors compound — a wrong tool selection at step 2 corrupts everything from step 3 onward.
- **Task-completion benchmarks are gameable.** UC Berkeley researchers examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be exploited to achieve near-perfect scores without solving real tasks. A benchmark that can't detect cheating tells you nothing.
- **60% single-run success drops to 25% across eight runs** (Galileo). Inter-run reliability — whether the agent completes the same task consistently — is the metric that matters in production. Static scores on one-shot runs miss this entirely.
- **Trajectory and outcome metrics measure different things.** Outcome metrics tell you if the agent succeeded. Trajectory metrics (which tools were called, in what order, with what arguments, with what retries) tell you why it succeeded or failed. You need both.
- **LLM-as-judge has known failure modes.** Position bias (favoring responses presented first), length bias (preferring longer outputs regardless of quality), and agreeableness bias (over-accepting without critical evaluation) can exceed 50% error rates in naive LLM judge setups.

## The move

The production eval stack operates on three tiers, not one:

**Tier 1 — Trajectory scoring (the most important tier most teams skip).**
Instrument your agent to emit structured traces: every LLM call, tool invocation, argument passed, retry, and state change. Score the trace itself — not just the final output. Key metrics: trajectory exact match, tool-call correctness, argument correctness, step efficiency (fewer steps = better), and error recovery rate. Google Vertex AI provides `trajectory_exact_match`, `trajectory_precision`, and `trajectory_recall` as standard production metrics.

**Tier 2 — Golden dataset regression harness.**
Build a curated dataset of real production inputs paired with expected tool sequences and outputs. Treat this as CI — every agent change runs against the harness. Score: task completion rate, groundedness (does the agent cite retrieved content accurately), faithfulness (does it contradict itself mid-run), and safety (no unsafe tool calls). Without this, you ship blind.

**Tier 3 — LLM-as-judge with bias mitigation.**
Deploy an LLM evaluator to score outputs on dimensions that are hard to codify: response quality, helpfulness, instruction adherence. Calibrate with explicit disclaimers in the judge prompt ("Do not favor responses based on length"). Use ensemble approaches — deploy multiple judge instances with randomized response order, take majority vote. For safety-critical cases, minority-veto ensembles allow any single judge to flag critical issues. Platforms like LangSmith (used in production by Klarna, Cloudflare, Nvidia, LinkedIn, Coinbase, and others), Braintrust, Galileo, Maxim AI, and Arize Phoenix provide this infrastructure.

**The full production loop:** Trace collection (instrument once, collect always) → offline eval on golden datasets (pre-deploy regression) → online eval on sampled production traffic (drift detection) → human expert feedback (strategic layer for edge cases). Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation rather than model capability gaps — the gap between pilots and production is an eval gap, not a model gap.

## Evidence

- **Blog post:** "AI Agent Evaluation: Metrics, Harnesses & Release Gates" — Todd Parker (Axian Solutions Architect) — presents the three-tier eval architecture with specific failure surface mapping (final output, trajectory, error recovery), and cites Gartner's 40% failure prediction. — [https://www.axian.com/2026/03/10/ai-agent-evaluation/](https://www.axian.com/2026/03/10/ai-agent-evaluation/)
- **Research survey:** "Evaluation and Benchmarking of LLM Agents: A Survey" — SAP Labs, KDD 2025 — systematically maps eval objectives (task completion, tool use, planning, safety) against evaluation methods, covering both trajectory-level and outcome-level metrics, with taxonomy of agent benchmark categories. — [https://dl.acm.org/doi/10.1145/3711896.3736570](https://dl.acm.org/doi/10.1145/3711896.3736570)
- **Research brief:** "AI Agent Evaluation and Benchmarking: Beyond Task Completion" — Zylos Research, 2026 — documents the Berkeley finding that eight major agent benchmarks are exploitable, introduces multi-dimensional eval framework (reliability, cost efficiency, safety, long-horizon competence), and notes that 40% of agentic AI projects will be canceled by end of 2027 per Gartner. — [https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Platform docs:** Galileo Agentic Evaluations — launched January 2025, used for pre-built and custom agent evaluators, trace logging, dataset management, and production guardrails. — [https://www.galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Platform docs:** LangSmith Agent Evaluation — production users include Klarna, Cloudflare, Nvidia, LinkedIn, Coinbase, Gong, Harvey, and 20+ other companies; covers offline eval datasets, LLM-as-judge with calibration, and online production sampling. — [https://www.langchain.com/langsmith/evaluation](https://www.langchain.com/langsmith/evaluation)
- **Open-source:** Ragas — open-source evaluation framework for RAG and agent pipelines, provides agent-specific metrics including tool call correctness and task completion scoring. Integrates with LangChain and LlamaIndex. — [https://docs.ragas.io/en/latest/tutorials/agent](https://docs.ragas.io/en/latest/tutorials/agent)

## Gotchas

- **Tracking latency and token counts is not evaluation.** Most teams monitor observability metrics (latency, cost, token usage) and mistake them for quality metrics. They tell you how expensive the agent is, not whether it works.
- **Golden datasets rot.** If you don't continuously refresh them with real production inputs, your harness tests against a distribution that no longer matches reality. The best teams automate dataset updates from flagged production failures.
- **LLM-as-judge needs ground truth for calibration.** A judge that hasn't been validated against human expert labels on a sample of your outputs will confidently rate bad agent behavior as acceptable. Calibrate before trusting.
- **Inter-run consistency is often worse than single-run accuracy.** An agent that scores 90% on average but completes the same task successfully only 40% of the time across 10 identical runs will destroy user trust. Test with repeated runs on the same inputs.
