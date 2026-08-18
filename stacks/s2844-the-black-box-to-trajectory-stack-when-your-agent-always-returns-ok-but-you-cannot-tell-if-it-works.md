# S-2844 · The Black-Box-to-Trajectory Stack

When your agent returns "success" on every run — but you have no idea if it's getting better or worse between releases, and you can't tell a lucky trajectory from a good one.

## Forces

- **Output quality is observable; trajectory quality is not** — the final answer might be fine while the agent silently called the wrong API three times, burned 40K tokens on a detour, and got lucky. Metrics that only check output miss the path.
- **Most teams still run on vibes** — HN threads and industry surveys consistently show that the majority of AI teams evaluate agents based on subjective impression, not systematic testing. "It looked good in the demo" is not a regression gate.
- **LLM-as-a-judge has a taste problem** — LLMs are easy to get to praise and easy to get to criticize, but getting them to praise good work *and* criticize bad work on non-trivial inputs is currently unreliable. Single-judge setups carry inherent style bias and only one perspective.
- **Non-determinism breaks standard testing** — even at temperature=0, providers occasionally return different tokens. A single-pass test on a non-deterministic agent is noise, not signal.
- **Operational constraints are first-class evaluation targets** — latency, cost per task, token efficiency, and tool reliability determine enterprise viability as much as output correctness.
- **Benchmarks plateau; production distributions shift** — curated eval sets go stale the moment your user traffic changes. The "right" answer on a benchmark may not be the right answer for your actual users.

## The Move

Evaluate at three scopes, not one. Measure the path, not just the destination.

**1. End-to-end (black-box) checks**
Assert final observable outcomes: did the agent complete the task, produce a correct answer, or resolve the ticket? Use verifiable ground truth where available — a database state, a returned JSON schema, a matched value. This is your regression gate for output correctness.

**2. Trajectory-level evaluation**
Inspect the full execution trace: step count, tool call sequence, unnecessary tool calls, loops and retries, ordering of steps, whether required tools were invoked. A trajectory viewer (e.g., Streamlit-based) surfaces where agents go wrong even when they arrive at a correct answer. LangFuse identifies four trajectory dimensions: step count, unnecessary tool calls, loops/retries, and correct ordering.

**3. Component-level (unit) checks**
Assert individual decisions: was the correct tool selected, with valid arguments? Did the agent recover after a tool failure? Did it use the right API endpoint? These run fast, catch regressions early, and don't require the full agent to run.

**Calibrate your grader**
- Use Cohen's kappa to measure agreement between LLM-as-judge and human labels — a judge that scores 0.3 agreement is not trustworthy.
- Prefer multi-agent evaluation (agents playing different roles, debating or collaborating on assessment) over single-judge setups to reduce individual bias.
- Map metrics to the dimensions that actually matter for your use case: task success rate, tool-call accuracy, recovery rate, cost per task, latency.

**Wire evals into CI**
- Stage 1: Fast routing (<1 min) — reject obvious failures immediately.
- Stage 2: Regression suite (1–3 min) — compare against main-branch baseline.
- Stage 3: Red-team / adversarial (nightly, optional on PRs) — catch silent behavioral drift.
- Fail on statistical regression, not single runs. Run multiple trials per task; track pass@k rather than pass@1.

**Operationalize production monitoring**
Log eval scores per session. Alert when task completion rate drops below threshold. Track drift over time — a score of 0.8 today means nothing without a baseline to compare against.

## Evidence

- **Anthropic Engineering (Jan 2026):** Defines the three eval scopes (end-to-end, trajectory, component-level) and the core vocabulary — tasks, trials, graders, transcripts, outcomes. Recommends multi-trial runs to handle LLM variance, and rubrics for multidimensional scoring. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

- **Hacker News "Ask HN: How are people doing AI evals these days?" (5 months ago, 43 comments):** Survey of real production practices. Consensus: "the vast majority of AI companies I talk to seem to evaluate models mostly based on vibes." Key challenges: non-binary output quality, different models handle function calling differently, hallucination rate as a key dimension. — https://news.ycombinator.com/item?id=47319587

- **72Technologies Blog (Jun 2026):** Practical CI eval pipeline. Three-factor challenge: non-deterministic policy × non-deterministic tools × distribution of inputs. Stage 1/2/3 gating with token budget guardrails and baseline regression detection. Catches silent failures (e.g., agent silently switching from internal DB to web search) that pass output-only evals. — https://www.72technologies.com/blog/agent-evals-ci-regression-tests

- **LangFuse Engineering:** AI agent evaluation framework mapping four dimensions — Trajectory (step count, loops), Tool Use (correct tool, error rate, recovery), Task Completion (goal achievement, resolution rate), and Multi-turn quality. Tool-argument checks belong on tool-call observability, not trajectory-level evaluation. — https://langfuse.com/resources/engineering/ai-agent-evaluation

- **Digits Blog / AI in Production 2025 (Jul 2025):** Hannes Hapke's practitioner presentation. Key finding: open source frameworks (LangChain, CrewAI) are great for prototyping but "bring too many dependencies for production." Recommends implementing the core agent loop directly for production stability. Directly affects eval design: the more dependencies in your agent, the more surface area your evals must cover. — https://digits.com/blog/ai-in-production-2025-slides

- **DeepEval / Confident AI (2025–2026):** Open-source eval framework supporting 10+ agent frameworks (LangChain, LangGraph, OpenAI Agents, Pydantic AI, CrewAI, Google ADK). Implements TaskCompletionMetric, TaskAdherenceMetric, and AgenticMetric for trajectory-level evaluation. Production integration: async logging of eval scores with alerting on drops below 0.5. — https://deepeval.com/guides/guides-ai-agent-evaluation

## Gotchas

- **Don't evaluate outputs alone.** An agent that produces a correct answer via a wildly inefficient or incorrect trajectory is a ticking time bomb. Trajectory metrics catch the detour before it becomes a production incident.
- **Single-judge LLM-as-a-judge is not enough.** Calibrate against human labels (Cohen's kappa). Without calibration, you're measuring the judge's biases, not your agent's quality.
- **One eval run = one data point.** LLM outputs vary. Run multiple trials per task. A single pass is noise; a distribution is signal.
- **Your eval set goes stale.** Production distributions shift. A benchmark that scores 95% today measures yesterday's user behavior. Curate eval datasets continuously from live traffic.
- **Cost guardrails are non-negotiable.** Eval runs consume tokens on every trial. Without a token budget per eval case and a fail-fast strategy, your eval pipeline becomes more expensive than the production system it's protecting.
