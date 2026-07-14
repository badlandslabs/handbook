# S-1088 · The Production Evaluation Stack — Measuring What Your Agent Actually Does vs. What It Says It Did

Public benchmarks score your agent in an environment that doesn't exist. Production reveals what the benchmark missed. Teams that measure only task completion — not trajectory quality, not operating envelope, not distribution drift — ship agents that look great in demos and fail silently in production.

## Forces

- **Public benchmarks are systematically gamed.** Berkeley's 2026 audit found that every major AI agent benchmark (SWE-bench, GAIA, WebArena, Terminal-Bench, etc.) can be exploited for near-perfect scores without solving a single task. The exploit gap is up to 100 percentage points on individual benchmarks. — [Berkeley RDI](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/)
- **Task accuracy is necessary but not sufficient.** An agent can complete a task and do it dangerously — wrong tool arguments, PII leakage, policy violations. Scoring only the final output misses the entire failure surface. — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)
- **The benchmark-to-production gap is 20–40 points routinely.** Task distribution shift, scaffold dependency, and contamination together routinely depress real-world performance far below leaderboard scores. — [OpenLegion](https://www.openlegion.ai/en/learn/ai-agent-benchmarks)
- **Evaluation is not a one-time gate.** Agent behavior shifts as models update, prompts evolve, and production task distribution drifts. Static eval sets go stale. — [Anthropic Engineering](https://www.anthropic.com/engineering/building-effective-agents)
- **86% of enterprise agent pilots never reach production.** The primary bottleneck is not building the agent — it is proving it works reliably enough to trust. — [AI2 Incubator via AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/08/ai2-incubator-state-of-ai-agents-2025-deployment-reality)

## The Move

Evaluation in two layers: **end-to-end trajectory scoring** and **component-level span checks**. Both run continuously in CI, not just pre-deployment.

**1. Golden test set as regression baseline.** Curate 50–100 representative production tasks with known expected outcomes. Run before every deploy, after every model swap, and after any tool or prompt change. This single practice catches the majority of regressions before they reach users. — [TechJack Solutions / NIST AI RMF](https://techjacksolutions.com/ai/agentic-ai/build/agent-evaluation-benchmarks)

**2. Score both the trajectory and the final output.** End-to-end: did the agent complete the task correctly? Span-level: did it choose the right tool, construct valid arguments, handle errors gracefully, and avoid unnecessary steps? An agent that gets the right answer via the wrong path is a liability. — [Braintrust](https://www.braintrust.dev/docs/best-practices/agents)

**3. Use deterministic gates plus LLM-as-judge rubric scores.** Deterministic checks (exact match, code execution pass/fail, API response schema) provide fast, reliable signals. LLM-as-judge covers the nuances — tone, relevance, groundedness, whether a response actually answered the user's intent. Neither replaces the other. — [MLflow](https://mlflow.org/llm-as-a-judge), [Braintrust](https://www.braintrust.dev/articles/how-to-eval)

**4. Track operating envelopes in the same traces as quality.** Log latency, cost per task, token efficiency, and step budgets alongside quality scores. A technically correct agent that costs $4 per transaction is not viable at scale. — [Confident AI](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

**5. Human review on a sampled trace subset.** Route 5–10% of production traces to human reviewers using structured rubrics. Use this to calibrate the LLM-as-judge and to catch "metric green, user red" failures — cases where automated scores pass but real users are confused or underserved. — [Confident AI](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

**6. Quarterly resampling from production logs.** Every 90 days, pull 200 recent production tasks into the golden set to detect distribution drift. An eval set built on last quarter's tasks becomes a lagging indicator. — [OpenLegion](https://www.openlegion.ai/en/learn/ai-agent-benchmarks)

## Evidence

- **Anthropic Engineering:** Evals shape iteration speed and model upgrade cycles. Teams without evals spend weeks manually testing new models; teams with evals upgrade in days. Evals become the highest-bandwidth communication channel between product and engineering. — [Anthropic](https://www.anthropic.com/engineering/building-effective-agents)
- **LangChain State of Agent Engineering Survey (1,340 professionals, Nov–Dec 2025):** 78% of enterprise technology leaders had at least one agent pilot. Only ~14% scaled one to organization-wide operational use. The dominant bottleneck cited: inability to reliably measure quality in production. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/08/ai2-incubator-state-of-ai-agents-2025-deployment-reality)
- **Braintrust user data:** Teams using production trace-to-test-case pipelines — logging real interactions, curating failures into datasets, running regression evals before deploy — report measurable accuracy improvements and faster model upgrade cycles. — [Braintrust](https://www.braintrust.dev/articles/top-5-platforms-agent-evals-2025)

## Gotchas

- **Public leaderboard scores ≠ production readiness.** Use them for coarse model shortlisting and historical capability tracking. Do not use them as deployment criteria. The 20–40 point gap is structural.
- **Stochastic outputs require re-runs.** Models behave differently on identical inputs across runs. For critical scenarios, run the golden set 3–5 times and track pass-rate distributions, not just pass/fail. A single run can mislead.
- **LLM-as-a-judge drifts with model updates.** The judge model itself is updated over time, causing evaluation scores to shift even when the evaluated agent hasn't changed. Re-calibrate judge prompts against human-labeled samples quarterly. — [Zylos Research](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **Safety and governance are first-class metrics, not afterthoughts.** Red teaming, PII handling, permission boundary testing, and user experience scoring are as critical as task accuracy. A technically correct agent that violates privacy boundaries is a liability. — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)
