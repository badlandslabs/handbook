# S-2476 · The Agent Eval Gap Stack — When Your Agent Scores 78 on Benchmarks and 22 in Production

You ship an agent that benchmarks beautifully: WebArena 78%, SWE-bench Verified 58%, GAIA 82%. Your team celebrates. Six weeks later, production dashboards show the agent completes intended tasks at a 22% rate. The gap is not a measurement error — it is a structural mismatch between what benchmarks measure and what production demands. The eval stack you skipped is the one that would have caught this.

## Forces

- **Benchmarks measure completion, not reliability.** UC Berkeley researchers examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found widespread data contamination, environment inconsistency, and evaluation criteria that diverge sharply from real deployment contexts. Enterprise data consistently shows a 30–40% performance gap between benchmark scores and production task-completion rates.
- **Agents are systems, not models.** A single-turn accuracy metric — even a good one — does not capture trajectory efficiency, tool-call failure rates, graceful degradation under partial API outages, or whether the agent reached the right answer through the wrong reasoning chain. Google's engineering guidance calls this "silent failure": the agent produces a correct output via an incorrect process (e.g., citing last year's report instead of this year's, but getting the number right anyway).
- **Quality is the #1 obstacle teams actually face.** The LangChain State of Agent Engineering 2025–2026 survey found 32% of teams cite quality as their biggest blocker to shipping agents. Latency comes second at 20%. Yet most teams still evaluate agents with a thumbs-up/thumbs-down button and a gut feeling.
- **Agents are non-deterministic — the same test can pass and fail on back-to-back runs.** This breaks traditional regression testing: you need a statistical model of "passing" (e.g., 9/10 runs must meet threshold), not a binary gate.

## The Move

Build a layered evaluation system that runs before code ships and continuously in production.

**Offline eval layer — before deployment:**
- Write golden datasets from production traces, not hand-crafted examples. Per Arthur.ai: "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures." Every production failure → trace → test case → golden dataset entry → CI release gate.
- Layer three eval types: (1) deterministic metrics (exact-match, JSON schema validation, tool-call signature checks), (2) LLM-as-judge using rubric-based scoring (G-Eval or custom rubrics targeting ≥0.80 Spearman correlation with human judgment), (3) composite metrics combining cost + latency + quality.
- Use multi-dimensional rubrics — NVIDIA's guidance recommends building 3-tier structures: 7 dimensions → 25 sub-dimensions → 130 scoring items. One-dimensional "did it succeed" scoring misses the silent-failure class.

**CI/CD integration — every PR:**
- Run the full eval suite as a release gate. Fail the build if quality scores regress below threshold. This is Eval-Driven Development (EDD), explicitly endorsed as Anthropic's official practice by Anthropic.
- Use DeepEval (pytest-native, 50+ built-in metrics) for unit-test-style eval assertions, or LangSmith for dataset management + tracing + experiment tracking across prompt versions.

**Production monitoring — after deployment:**
- Track operational metrics continuously: tool-call error rates, API latencies, token consumption per interaction, trajectory length vs. expected length.
- Track quality signals: user feedback, conversation abandonment rates, task-completion rates across interaction types.
- Feed production failures back into the golden dataset. The loop is: failure → trace → test case → golden dataset → CI gate.

## Evidence

- **Blog post:** "Building Regression Test Datasets for AI Agents From Production Failures" — Arthur.ai documents the production-failure-to-regression-test loop in detail, emphasizing that agents' non-deterministic, multi-step nature makes hand-crafted datasets insufficient. — [https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Survey:** "Evaluation and Benchmarking of LLM Agents: A Survey" (arXiv:2507.21504) — Comprehensive academic survey of agent evaluation, finding that existing benchmarks optimize for task accuracy while enterprises need holistic evaluation across cost, reliability, and operational constraints. 85% of companies experiment with gen-AI; only a small fraction deploy agents in production. — [https://arxiv.org/abs/2507.21504](https://arxiv.org/abs/2507.21504)
- **Engineering guide:** Google Cloud's "A Methodical Approach to Agent Evaluation" — Introduces the "silent failure" concept, advocates for CI/CD-integrated evaluation as quality gates, and recommends monitoring operational + quality/engagement metrics in production. — [https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Technical blog:** NVIDIA's "Mastering Agentic Techniques: AI Agent Evaluation" — Compares model vs. agent evaluation taxonomy, recommends building 3-tier rubrics, targeting LLM-as-judge with 0.80+ Spearman correlation, and integrating evals into CI/CD with commit/scheduled/event-driven triggers. — [https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)
- **Case study:** Martin Fowler — "Building Reliable Agentic AI Systems" (Bayer AG + Thoughtworks, PRINCE platform) — Documents a production pharmaceutical agent system with explicit context engineering and harness engineering (orchestration, recovery, observability) as first-class concerns, including multi-layered evaluation. — [https://martinfowler.com/articles/reliable-llm-bayer.html](https://martinfowler.com/articles/reliable-llm-bayer.html)

## Gotchas

- **Golden datasets go stale.** Input distributions shift, user behavior evolves, APIs change. A golden dataset built in January may have no overlap with March production traffic. Re-build from recent production traces quarterly, or trigger rebuilds on significant product/API changes.
- **LLM-as-judge has its own failure modes.** Judges can exhibit position bias (preferring first or last options), self-preference bias (favoring outputs similar to their own), and length bias (preferring longer outputs). Calibrate against human annotations and track Spearman correlation — if it drops below 0.80, the judge is unreliable.
- **Single-dimension pass/fail masks silent failures.** An agent that achieves correct final output through wrong intermediate steps will score "pass" on task completion while being fundamentally unreliable. Measure trajectory — did it use the right tools, in the right order, with the right parameters?
- **Cost and latency are first-class quality signals, not afterthoughts.** An agent that completes 95% of tasks but at 3× the expected cost and 5× the latency is not a 95%-quality agent. Factor token consumption and response time into your rubrics from the start.
