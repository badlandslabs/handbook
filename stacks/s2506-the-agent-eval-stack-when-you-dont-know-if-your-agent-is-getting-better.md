# S-2506 · The Agent Eval Stack — When You Don't Know If Your Agent Is Getting Better

You've tuned the prompt, shipped a new tool definition, and updated the model. Your agent now logs clean traces, runs without errors, and the demo conversation looks great. But you have no idea whether it actually works better than last week. This is the agent eval problem: most teams have no systematic way to know if their agent improved, regressed, or silently degraded. They ship blind.

## Forces

- **Single-turn metrics miss the actual failure modes.** BLEU, ROUGE, and perplexity measure text quality on one input-output pair. Agents fail in the middle of trajectories — wrong tool, missing step, error swallowed silently — and the final output can still look reasonable.
- **The four evaluation dimensions are distinct.** Trajectory quality (did the path make sense), tool use (right tool, right arguments), task completion (did the user get what they asked for), and output quality (is the answer accurate and well-formed) require separate metrics. Most teams conflate them.
- **LLM-as-judge has a ceiling.** A single GPT-4 judge correlates ~0.52 Kendall Tau with human judgment. Multi-agent discussion reaches ~0.57. Neither is a reliable ground truth — they are a proxy that needs its own calibration.
- **Production monitoring and evaluation are different things.** 89% of organizations have observability for agents, but only 52% run structured evaluations against documented test sets. You know something happened; you don't know if it was right.

## The move

Build a three-layer production eval pipeline that evaluates at the right granularity for each stage. The core insight from multiple sources: the unit of evaluation is the trace, not the turn.

**Layer 1 — Offline golden dataset (50–200 cases)**
- Curate representative test cases from real production inputs, not synthetic ones. Include edge cases that broke the agent before.
- Test across all four dimensions: trajectory correctness, tool call accuracy, task completion, output faithfulness.
- Run against prompt changes, model upgrades, and tool schema changes before any deployment.

**Layer 2 — CI gate (20–50 regression cases)**
- Run on every PR. Set pass-rate threshold 2–3 points below current baseline (not 100% — that way lies gaming).
- Assert on recorded tool calls from the trace, not parsed model output. Record `tool_name`, `arguments`, and `observation` as structured fields.
- Track trajectory efficiency: step count vs. an expected budget per task type.

**Layer 3 — Production sampling (5–10% of live traffic)**
- Sample traces randomly, run evaluators asynchronously against them.
- Use z-score drift detection: alert when any dimension's score deviates beyond 2σ from the rolling 30-day mean.
- Route failures to structured human review, not random sampling. Escalation is triggered, not constant.

**Measure evaluator quality, not just agent quality.**
- Run evaluator accuracy against a small human-labeled holdout set monthly.
- Target 0.80+ Spearman correlation between LLM-as-judge scores and human judgment before treating the judge as reliable.
- If the evaluator fails the holdout, recalibrate the prompt or swap the judge model before continuing.

## Evidence

- **Engineering blog (Langfuse):** Four distinct evaluation dimensions for agents — Trajectory (step count, loops, ordering), Tool Use (correct tool, valid arguments, error recovery), Task Completion (boolean root verdict), Output Quality (faithfulness, relevance) — with the recommendation to start with one metric per dimension and expand only when a metric has caught a real regression. — [https://langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **Engineering case study (Noble House Consulting, 2025–2026):** Eval-gated release process for recruiter workflow AI agents — automated eval suite integrated into CI/CD, weekly drift tests, documented 6 failure modes with playbooks. Outcome: 40% reduction in production agent incidents within two quarters. — [https://www.diweshsaxena.com/work/ai-agent-eval-harness-production](https://www.diweshsaxena.com/work/ai-agent-eval-harness-production)
- **Research paper (arXiv:2508.02994, Yu 2025):** Single LLM judges achieve Kendall Tau ~0.52 with human judgment on open-ended tasks; multi-agent discussion reaches ~0.57. For code generation, agent-as-judge achieved near-perfect agreement with a majority vote of 5 human experts, while a lone LLM judge did not. Recommends single judges only for general-domain, moderately complex tasks. — [https://arxiv.org/html/2508.02994v1](https://arxiv.org/html/2508.02994v1)
- **Platform data (Confident AI / DeepEval, YC W25):** 600K+ evaluations run daily, enterprise customers including BCG, AstraZeneca, AXA, Capgemini. GitHub: 8,900+ stars. Framework implements end-to-end, trajectory, and component-level evaluation scopes. — [https://news.ycombinator.com/item?id=43116633](https://news.ycombinator.com/item?id=43116633)
- **Industry report (Replyant, 2026):** 57% of organizations have agents in production; 32% cite quality as the top barrier. Recommended three-layer pipeline: 50–200 offline cases → CI gate of 20–50 regression cases → 5–10% production sampling with z-score drift. Key insight: "Tool selection accuracy below 85% is a context problem, not a model problem." — [https://replyant.com/lab/agent-evals-cicd](https://replyant.com/lab/agent-evals-cicd)
- **Platform post (Arthur, 2026):** The highest-value regression test dataset is not handcrafted — it comes from production failures. Every agent failure in production generates a trace that becomes a test case that becomes a release gate. Loop: Production Failure → Trace → Test Case → Golden Dataset → CI/CD Gate. — [https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **Evaluating the final output is necessary but insufficient.** An agent can reach a wrong conclusion through a broken trajectory and still produce a confident, well-formed answer. Always evaluate the path, not just the destination.
- **Golden datasets decay.** A test set built on last quarter's input distribution becomes less sensitive to current failure modes. Rotate cases quarterly and weight recent production failures.
- **Gaming the eval is easier than fixing the agent.** If your CI threshold is 100% pass rate, engineers will engineer the test set, not the agent. Keep the threshold below your current performance so regressions actually fail.
- **LLM-as-judge correlation with human judgment varies by domain.** A judge calibrated on Q&A may be unreliable on code generation, customer support, or multi-tool reasoning. Validate separately per domain.
