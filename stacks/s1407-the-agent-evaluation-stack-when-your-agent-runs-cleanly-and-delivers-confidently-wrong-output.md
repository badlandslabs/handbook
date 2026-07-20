# S-1407 · The Agent Evaluation Stack — When Your Agent Runs Cleanly and Delivers Confidently Wrong Output

Your agent completes a 12-step workflow. All tool calls return HTTP 200. The JSON is well-formed. The final answer reads confidently and coherently. A week later, you discover the agent routed 40% of support tickets to the wrong team — silently, with full conviction. This is the agent evaluation problem: agents fail by producing confident nonsense, not by crashing. Traditional software testing catches exceptions and incorrect values; agent evaluation must catch the agent that never knew it was wrong.

## Forces

- **The trajectory is the unit, not the output.** A correct final answer via a broken chain of reasoning is a production incident waiting to happen. You cannot evaluate agents by inspecting only their final output.
- **Accuracy-style metrics miss the failure modes that matter.** BLEU/ROUGE scores on the final text say nothing about whether the agent called the right tools, used correct arguments, or stopped at the right moment.
- **Non-determinism makes regression invisible.** An agent that passes today may fail tomorrow on the same input due to sampling. Without trajectory-level regression suites, degradation is silent.
- **Manual review does not scale.** Human annotation is gold-standard but costs 34.7 hours per failure on average in production (arXiv 2503.20263, FSE 2025). You need automated evaluation that can catch failures before users do.
- **The three-layer problem:** task success (did it complete?), trajectory quality (was the path sound?), and component correctness (which tool or reasoning step broke?) — all need separate measurement.

## The move

The production evaluation stack for AI agents combines **trajectory-aware metrics**, **trace-based instrumentation**, and **a calibrated judge hierarchy** spanning deterministic checks through LLM-as-judge through human annotation.

- **Instrument every agent run as a trace.** Captured spans include: model calls, tool invocations, arguments passed, raw responses, and final outputs. Tools: MLflow Traces, LangSmith, Langfuse, or OpenTelemetry. This is the raw material — without traces, you have no evaluation data.
- **Evaluate at three levels simultaneously.** (1) Task completion: did the agent achieve the stated goal? (2) Trajectory quality: were steps efficient, tools correct, arguments valid, and was the plan sound? (3) Component-level: which specific span caused failure? Confident AI's DeepEval and Galileo provide span-level scoring that maps scores back to the exact step that broke.
- **Layer your judge, don't rely on one.** Deterministic checks (JSON schema validation, regex, exact-match on structured outputs) for low-latency, zero-cost component checks. LLM-as-judge for nuanced quality — helpfulness, faithfulness, plan quality — calibrated against Align Evals or a golden dataset. Human annotation as the final gate for complex, high-stakes tasks.
- **Measure error compounding, not just final accuracy.** If each step is 85% reliable, a 10-step chain is ~20% reliable end-to-end (0.85^10). Track per-step error rates to identify which tools or reasoning patterns degrade under load.
- **Detect false task completion.** The most dangerous failure: the agent stops and reports success without achieving the goal. Catch this with explicit completion validators — small deterministic check functions that verify the output satisfies the task's minimum requirements before accepting the run.
- **Establish a regression suite from day one.** Run evals on every deployment. Track pass rates, latency, cost per run, and tool-call counts as first-class metrics. Set a floor — if the 90th-percentile run exceeds $2 or 45 tool calls, alert.

## Evidence

- **Anthropic Engineering Blog (Dec 2024):** Found that simple, composable patterns outperform complex frameworks in production after working with "dozens of teams" building LLM agents. Key principle: "Start with the simplest solution that could work, and only add complexity when measurement shows it's needed." — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Noqta / FSE 2025 Research (arXiv 2503.20263):** Analysis of 428 real LLM training failures on a production platform found 89.9% require manual log analysis, 34.7 hours average diagnosis time, and 16.92 GB of logs per failure — demonstrating the evaluation gap between what teams have and what they need. — [https://arxiv.org/html/2503.20263v1](https://arxiv.org/html/2503.20263v1)
- **Confident AI DeepEval Documentation (2026):** LLM agent evaluation groups into four metric areas — tool calling, planning, task completion, and reasoning — with three evaluation levels: end-to-end, trajectory, and component. LLM-as-judge bias is mitigated by calibrating against Align Evals golden datasets. — [https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **MLflow Traces Documentation (2026):** Production traces can be captured once and reused across multiple offline evaluation runs, reducing LLM evaluation costs by eliminating redundant inference. Supports annotation with ground truth for reference-based metrics. — [https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/traces](https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/traces)

## Gotchas

- **Waiting for a red alert on a silent failure.** Agents that complete without errors but produce wrong answers will not trigger traditional monitoring. You need explicit completion validators and trajectory-level assertions — not just HTTP status codes.
- **Evaluating with the same model you deployed.** Using the agent's own model as the judge introduces circularity and self-serving bias. Calibrate judges independently: use a smaller, cheaper model for deterministic checks, and a separate judge model (ideally from a different family) for qualitative judgments.
- **Measuring cost and latency too late.** Per-run cost and tool-call counts are leading indicators of runaway loops. A trajectory that costs $30 and 200 tool calls is not an edge case — it is your regression target. Track these from day one, not as an afterthought.
- **One-shot evaluation replacing continuous monitoring.** A static eval suite on deploy catches regressions but misses drift. The evaluation loop must be continuous: production traces feeding back into the eval dataset, triggering re-runs when similar inputs surface unexpected behavior.
