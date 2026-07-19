# S-1330 · The Consistency Gap Stack — When Your "70% Agent" Actually Succeeds 25% of the Time in Production

Your agent scores 70% on your evaluation benchmark. You ship it. It fails intermittently in ways you cannot reproduce — sometimes it works, sometimes it doesn't, and you cannot predict which. Your benchmark told you it was ready. It was not. This is the consistency gap: a single metric that measures one lucky run instead of measuring whether the agent is actually reliable across repeated attempts.

## Forces

- **pass@k hides instability.** The standard benchmark metric reports "at least one success in k attempts." An agent that succeeds once out of eight tries scores 70% pass@8 but fails 7 out of 8 real deployments. The number looks good; the system is not.
- **LLMs are stochastic.** Temperature > 0 means identical inputs can produce different tool selections, reasoning paths, and outputs. A single run is a single sample from a distribution you have not characterized.
- **Enterprise benchmarks optimize for accuracy, not reliability.** Across 12 main benchmarks, cost, latency, security, and policy compliance are not measured. Shipping on accuracy alone leaves you blind to the properties that matter in production.
- **The lab-to-production gap is documented at 37%.** Multi-agent coordination research shows 90% goal success in ideal conditions versus 53–60% for single agents — but this collapses further in production where network conditions, API reliability, and edge inputs differ from benchmarks.
- **Most teams do not measure pass^k.** Despite it being the easiest single change to align benchmarks with production behavior, the vast majority of agent evaluation pipelines never compute consistency.

## The move

The key move: **measure consistency (pass^k), not just success rate (pass@k), and pair both with a cost dimension.**

- **Track pass^k alongside pass@1.** pass@1 is your baseline; the delta to pass^k is your instability signal. If pass@1 = 70% but pass^8 = 25%, you have a consistency problem, not an accuracy problem. Fix the tool strategy before scaling.
- **Set k from the deployment, not the benchmark.** If your product is a 6-turn customer support flow, pass^6 is the meaningful metric. A one-shot summarizer needs pass^1. Benchmarks that use a fixed k for all agent types mischaracterize the actual reliability profile.
- **Run at temperature > 0 with varied seeds.** Temperature zero with the same seed makes the metric meaningless — it measures determinism, not capability. Vary the random seed per attempt.
- **Use CLEAR: Cost, Latency, Efficacy, Assurance, Reliability.** The five-dimensional framework from Mehta's 2025 arXiv paper (validated against 300 enterprise tasks, ρ=0.83 correlation to production outcomes vs ρ=0.41 for traditional accuracy-only metrics) shows that the Pareto-efficient agent is rarely the most accurate one. Domain-specialized agents achieve 82.7% accuracy vs 59–63% for general LLMs, at 4.4–10.8× lower cost.
- **Compute cost-normalized accuracy (CNA).** Domain-specialized approaches yield 260.4 CNA vs 14.5–58.0 for general architectures. A 70% accurate agent costing $8/1000 calls is worse than a 65% accurate agent costing $0.40/1000 calls.

## Evidence

- **arXiv paper (2025):** Empirical evaluation of six leading agents across 300 enterprise tasks finds agent performance drops from 60% (single run) to 25% (8-run consistency). Domain-specialized agents achieve 72.8% pass@8 vs 52.1–64.5% for general-purpose architectures. CLEAR predicts production success with ρ=0.83 vs ρ=0.41 for traditional metrics. — [arXiv:2511.14136](https://arxiv.org/abs/2511.14136)
- **AgentClash blog (2026):** Analysis of pass@k vs pass^k metrics shows the two metrics answer fundamentally different questions — "does the agent usually finish the job?" vs "does the agent always finish the job?" — and that adopting pass^k is the easiest single change to align benchmark reporting with production behavior. — [AgentClash: pass@k vs pass^k](https://www.agentclash.dev/blog/pass-at-k-vs-pass-power-k)
- **MLCommons ARES (2025):** 34 organizations including Anthropic, OpenAI, Google, Meta, Microsoft convened to establish agentic reliability evaluation standards. Industry data shows 50× cost variation for similar precision across agents, and only 5% of enterprises cite accurate tool calling as a top challenge — most focus remains on surface-level behavior, not reliability. — [MLCommons ARES announcement](https://mlcommons.org/2025/06/ares-announce)

## Gotchas

- **Treating pass@8 as a reliability metric.** pass@8 = 70% means "succeeded at least once in 8 tries." It does not mean "succeeded 70% of the time." An agent with pass@8 = 70% and pass^8 = 25% is a 25% reliability system dressed as a 70% one.
- **Shipping on accuracy without cost or latency envelopes.** A highly accurate agent that costs 50× more or takes 10× longer is not the same product. Define operating envelopes in the same traces used for quality — cost/token budgets and latency SLAs belong in evaluation, not just monitoring.
- **Ignoring the domain-specialization trade-off.** General-purpose agents are the default choice but not the Pareto-efficient one. The 82.7% vs 59–63% accuracy gap at 4.4–10.8× lower cost means the first question before choosing a general LLM should be: does a specialized agent exist for this domain?
