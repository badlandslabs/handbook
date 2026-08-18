# S-2812 · The Evaluation-to-Outcome Gap Stack — When Your Agent Says Done but Isn't Correct

When your agent reports "task complete" at 95% but 30% of outputs are wrong, and you had no way to catch it before users did. The gap between completion and correctness is where production agents die.

## Forces

- **Task completion rate and correctness are different metrics.** An agent can call all the right tools in the right order (completes) while producing a wrong final answer (fails). Traditional monitoring tracks uptime and latency, not whether the answer is right. Teams optimize for the former and miss the latter.
- **LLM outputs are non-deterministic — existing CI/CD testing assumes determinism.** Exact-match assertions and regression suites designed for deterministic software break when the same input produces two valid but different outputs. You need behavioral evaluation, not token-level comparison.
- **Agents can fail silently inside tool calls.** An agent handles a refund API error by silently skipping the refund and marking the ticket resolved. No single-turn accuracy test catches this. The failure is in the trajectory, not the output.
- **Human review doesn't scale.** A team reviewing 20 agent runs per day won't catch the pattern that 1-in-3 runs produces subtly wrong data — especially when the wrong answer reads confidently.

## The move

Measure both trajectory (how the agent reasoned) and outcome (did it solve the problem), then gate production on both.

### Tier 1 — Outcome metrics (the floor)

Track these continuously in production dashboards:

- **Task completion rate**: % of tasks finished without human intervention. Target > 85%.
- **First-pass accuracy**: % of deliverables accepted without revision. Target > 70%.
- **Actual correctness rate**: verified ground-truth comparison on a sample of outputs. This is where the gap appears — completion and correctness diverge.
- **Latency (P50/P95/P99)** and **cost per task** for efficiency.

### Tier 2 — Trajectory metrics (catches the silent failures)

These catch failures that outcome metrics miss:

- **Tool call accuracy**: Did the agent call the right tools with the right arguments? Did it handle errors from downstream APIs or silently skip them?
- **Step completion**: Did the agent complete all necessary steps in the reasoning chain, or did it shortcut?
- **Intermediate state verification**: For agents that depend on prior tool outputs (e.g., a search result used as context for the next step), verify that intermediate state is valid before proceeding.
- **Fallback behavior**: When a tool call fails or times out, did the agent retry, degrade gracefully, or silently continue with bad context?

### Tier 3 — LLM-as-judge for behavioral evaluation

Use a stronger model to score agent outputs against a rubric. This is the production workhorse for scaling evaluation beyond human review:

- Score on **correctness**, **relevance**, **completeness**, and **safety** using a structured prompt with examples.
- Calibrate against human judgment: target **0.80+ Spearman correlation** with human evaluators before trusting scores.
- Run judge evaluations on a **rolling sample** (e.g., 5% of production traffic) in addition to the eval suite.

### Tier 4 — CI/CD integration

Evaluation is only useful if it gates deployments:

- **Eval-driven development**: run the eval suite on every pull request. A prompt change that drops correctness by 10% should block merge.
- **Scheduled regression runs**: run the full eval suite on a schedule (nightly or weekly) to catch drift from model version updates, context length changes, or tool schema modifications.
- **Event-driven triggers**: re-run specific test cases when a tool schema changes, a model is updated, or an SLO is breached.
- **Golden dataset**: maintain a curated set of 50-200 test cases with known-correct outputs. Update it when the agent consistently handles new edge cases correctly, or when production incidents reveal missing test cases.

## Evidence

- **Empirical study (arXiv:2512.01939, Dec 2025):** Analyzed 1,575 real-world LLM-agent GitHub projects and 20,620 developer discussion threads. Found that performance optimization is a "universal weakness across all agent frameworks" and that 96% of top-starred projects combine 2+ frameworks. Identifies four major challenge categories: Logic, Tool, Performance, Version. — [arXiv:2512.01939](https://arxiv.org/html/2512.01939)

- **Production case study — Vindler Solutions (Dec 2025):** A mid-sized SaaS company discovered their agent was "completing" tasks at 95% success rate. Proper evaluation showed only 70% of outputs were actually correct — a 30% hidden failure rate invisible to standard monitoring. Additional data: 39% of AI projects in 2024-2025 fell short of expectations; only 52% of organizations with observability have proper evaluation systems. — [Vindler Solutions Blog](https://vindler.solutions/blog/agent-evaluation-at-scale)

- **Engineering team (Monte Carlo, Nov 2025):** Built an evaluation suite for a Troubleshooting Agent using hundreds of sub-agents for data reliability incidents. Developed three evaluation categories: (1) semantic distance (LLM-judge similarity scoring), (2) deterministic checks (exact-match where possible), and (3) trajectory checks (verifying tool call sequences). Found that soft failures — where the agent completes without error but produces wrong output — are the most dangerous failure mode and require trajectory-level detection. — [Monte Carlo Blog](https://montecarlo.ai/blog-ai-agent-evaluation)

## Gotchas

- **Don't gate on task completion alone.** It's necessary but not sufficient. A task is "complete" when the agent stops — not when it solves the problem. Measure both.
- **LLM-as-judge needs calibration, not just a prompt.** A judge model without human-grounded calibration can be overconfident or inconsistently scored. Use Cohen's kappa to measure inter-rater reliability between the judge and human reviewers. Ship judge prompts only when correlation hits 0.80+.
- **Golden datasets decay.** Agent capabilities evolve, domain knowledge changes, and test cases become stale. A golden dataset that hasn't been updated in 6 months tests yesterday's agent against yesterday's reality. Treat it like production code — review and update quarterly.
- **Eval runs add latency to CI.** A 200-case eval suite running on every PR can add 15-30 minutes to pipeline time. Scope the fast-path gate to 20-30 critical cases; run the full suite on nightly schedules.
- **Observation ≠ evaluation.** 89% of organizations have observability (they know if the agent is running) but only 52% have evaluation (they know if it's right). Building dashboards for latency and error rates is table stakes — it doesn't tell you if the agent is producing correct output.
