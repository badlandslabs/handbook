# S-835 · The Agent-Eval Stack — When Task Completion Is Not Enough

You have an agent that "works" — it completes tasks. But you have no idea if it's reliable, cost-efficient, or silently breaking on edge cases. You ship a prompt change and discover three weeks later that it broke on 12% of production queries.

## Forces

- **Static benchmarks are broken.** SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, and FieldWorkBench are all contaminated or exploitable, with traditional benchmarks overestimating agent capabilities by 20–50%. A pass rate on these does not translate to production reliability.
- **Agent outputs are non-deterministic.** The same input can produce different valid trajectories. `assert output == "expected"` is meaningless. You need metrics that evaluate the *path*, not just the destination.
- **Single-dimension metrics lie.** Task-completion rate alone tells you nothing about cost (an agent that makes 200 tool calls to solve what 20 could solve is a budget disaster), latency (users won't wait), or safety (an agent that completes the task by bypassing guardrails is worse than one that fails gracefully).
- **Eval-as-once is not eval-as-always.** A test suite you run once at deploy time is not evaluation — it's a snapshot. Production agents degrade as models change, prompts drift, and downstream APIs evolve.

## The Move

Evaluate agents on **multiple dimensions**, at **multiple layers**, across **multiple trials**, with **LLM-as-judge** as a load-bearing component — not just an offline harness.

### 1. CLASSic evaluation dimensions

Measure five dimensions, not just accuracy:

| Dimension | What to track | Why it matters |
|---|---|---|
| **Cost** | Tokens per task, API calls, infra spend | Enterprise viability; an agent that "works" but costs 10× a human is not a product |
| **Latency** | End-to-end task time, time-to-first-tool-call | User experience; agents that take 45s to do a 5s job create bad UX |
| **Accuracy** | Task completion, answer correctness, tool-call accuracy | Baseline quality |
| **Stability** | Pass-rate variance across N trials | Stochastic systems need repeated measurement; a 70% pass rate means 30% failure |
| **Security** | Prompt injection detection, out-of-scope adherence, guardrail bypass rate | An agent that completes tasks by bypassing safety is worse than one that refuses |

### 2. Three-layer eval stack

Evaluate at three levels, not just outcome:

- **Outcome level:** Did the agent complete the task? (Task completion rate, pass/fail per task)
- **Trajectory level:** How did it get there? (Step efficiency, plan quality, plan adherence — an agent making 200 steps where 20 would suffice has a trajectory problem)
- **Component level:** Which specific span caused the failure? (Tool selection correctness, argument correctness, retrieval quality, reasoning quality)

Trajectory and component-level metrics are diagnostic — they tell you *where* the failure happened, not just that it happened. Use them to triage regressions: a drop in task-completion rate with stable trajectory quality means the model degraded; a spike in tool-selection failures with stable task-completion means a downstream API changed.

### 3. LLM-as-judge, used two ways

LLM-as-judge has crossed from offline eval harness into **runtime quality gate** — over 57% of surveyed production agent teams now run judge LLMs at runtime, not just in test suites.

Two distinct patterns:

**Offline eval mode:** Use a judge LLM (GPT-4o, Claude 3.7 Sonnet, or a distilled judge like Prometheus 2 7B / Galileo Luna-2 3B–8B) to score outputs against rubrics in your CI/CD pipeline. Evaluate faithfulness, answer relevancy, plan quality, tool selection correctness. Run on curated test sets derived from **real production failure cases**, not synthetic benchmarks.

**Runtime verifier mode:** Gate agent outputs with a judge LLM at execution time — check tool-call arguments before they're sent, verify intermediate reasoning steps, catch hallucinated facts before they propagate. Higher latency cost, lower failure-in-production cost. Appropriate for high-stakes actions (financial transactions, data deletion, external API calls).

**Calibrate your judge:** LLM-as-judge is not ground truth — judges have their own biases (leniency bias, position bias, self-preference). Calibrate against human labels on a sample of 50–100 cases before trusting judge scores to gate production.

### 4. Stochastic eval: run N trials, not N=1

Agent behavior is non-deterministic. A single run is a single sample from a distribution. Report pass rates over ≥10–20 trials per task. Use variance (σ) as a first-class metric — high variance means unreliable behavior that will bite users unpredictably.

### 5. Keep your test set private and live

Public benchmarks are gameable and contaminable. The fix is not to find a better benchmark — it's to:

1. Maintain a **private eval set** curated from real production failures
2. Add new failure cases to the eval set continuously (Thoughtworks calls this reaching from ~20% automated coverage to ~80%+ as the application matures)
3. For coding agents, use **SWE-bench-Live** (1,319 real GitHub issues from 2024+, with automated Docker-based environment construction) instead of static SWE-bench
4. Run **adversarial/simulation tests** — simulate users who try to break the agent, inject edge cases, test recovery from tool failures

### 6. Integrate eval into the sprint, not just pre-deploy

Eval is not a gate at deploy time — it's a continuous practice woven into development:

- Run eval suite on every prompt/model change (CI gate)
- Run eval suite weekly on a schedule against production traffic samples
- Run eval suite on every new tool addition (tool correctness degrades as the tool surface expands)
- Use production observability to surface failure patterns and feed them back into the eval set (closing the loop from production → eval → production)

## Evidence

- **Engineering post (Anthropic):** Three-layer eval framework — Task (problem/test case), Trial (each attempt), Grader (scoring logic). Agents operate over many turns with branching paths; evaluating only the final output misses where failures occurred. Recommends trajectory-level evaluation (plan quality, step efficiency) combined with outcome-level evaluation (task completion). — [Anthropic Engineering: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (Jan 2026)

- **Survey (arXiv 2507.21504):** Comprehensive survey of LLM agent evaluation covering benchmark contamination, trajectory-level metrics, multi-agent evaluation, and the gap between benchmark performance and real-world deployment. Confirms that static benchmarks systematically overestimate agent capabilities. — [arXiv:2507.21504 — Evaluation and Benchmarking of LLM Agents: A Survey](https://arxiv.org/abs/2507.21504) (Jul 2025)

- **Research brief (Zylos, 2026-01):** CLASSic framework (Cost, Latency, Accuracy, Stability, Security). Reports that 57%+ of production agent teams use LLM-as-judge at runtime, not just offline. Documents six judge-LLM patterns: offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, inference-time reward models. — [Zylos Research: AI Agent Testing & Evaluation — The Complete 2026 Guide](https://zylos.ai/research/2026-01-12-ai-agent-testing-evaluation)

- **Engineering post (Thoughtworks):** Three-phase eval maturation: (1) ~20% automated with synthetic test cases, (2) ~80%+ automated after business user testing surfaces real personas and failure modes, (3) production observability with traces, latency, cost, and failure-pattern monitoring. — [Thoughtworks: Evaluating AI agents in production — A practical framework](https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production) (Jun 2026)

- **Research brief (Zylos, 2026-05):** Eight prominent AI agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkBench) all found to be contaminated or exploitable. Benchmark overestimation of 20–50% for publicly available datasets. Proposes contamination-resistant alternatives: procedural generation, private test sets, live environments. — [Zylos Research: AI Agent Evaluation and Benchmarking: Beyond Task Completion](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking) (May 2026)

- **arXiv paper (SWE-bench-Live):** SWE-bench-Live — 1,319 real GitHub issues from 2024+, spanning 93 repositories, with automated Docker environment construction via RepoLaunch pipeline. Addresses contamination by using live, continuously-updated issues rather than static historical datasets. — [arXiv:2505.23419 — SWE-bench Goes Live](https://arxiv.org/html/2505.23419v2)

- **Open-source framework (DeepEval):** pytest-style LLM eval framework with G-Eval, hallucination, answer relevancy, RAGAS metrics. Supports agent-specific metrics: TaskCompletionMetric, StepEfficiencyMetric, PlanQualityMetric, PlanAdherenceMetric, ToolCorrectnessMetric, ArgumentCorrectnessMetric. — [GitHub: confident-ai/deepeval](https://github.com/mbrukman/confident-ai-deepeval)

## Gotchas

- **Do not use public benchmark pass rates as your quality signal.** They overestimate real-world performance and are gameable. Use them as a sanity check, not a gate.
- **LLM-as-judge has a leniency bias problem.** Judges score higher than human reviewers on the same outputs. Calibrate with human-labeled samples before using judge scores to gate production.
- **N=1 eval runs are statistically meaningless for agents.** Always run multiple trials and report variance. A single pass/fail tells you nothing about reliability.
- **Adding a new tool expands your failure surface without expanding your eval coverage.** Every new tool needs its own tool-correctness and argument-correctness test cases.
- **Trajectory-level eval catches regressions that outcome-level misses.** An agent that degrades from 20 steps to 80 steps for the same task will show stable task-completion rate but tank step-efficiency — catching this requires trajectory metrics.
- **Production observability without a feedback loop to the eval set is window dressing.** Capturing traces and failure patterns in production is only valuable if you add those cases to your eval suite before the next deploy.
