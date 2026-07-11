# S-959 · The Trajectory vs. Outcome Eval Stack — When Your Agent Is Right for the Wrong Reasons

Your agent completes 91% of tasks correctly. You ship it. Three weeks later, an incident report shows it consistently chooses the right API endpoint but passes malformed arguments — it gets lucky with permissive defaults on your test data. Your eval measured outcomes, not reasoning. The agent was correct. Its competence wasn't.

## Forces

- Traditional ML metrics (accuracy, F1, BLEU, ROUGE) assume deterministic outputs and binary ground truth — agents are neither
- Outcome metrics catch failure but can't distinguish luck from skill — a broken plan that stumbles into the right answer scores the same as careful reasoning
- Trajectory metrics catch flawed reasoning but are harder to score and harder to define ground truth for
- LLM-as-judge scales eval but introduces judge bias — the gap between a naive judge and a calibrated one can flip which agent wins
- Benchmark saturation is real: UC Berkeley found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) exploitable for near-perfect scores without solving real tasks
- Eval cost compounds with trajectory length — each multi-step agent run is expensive to replay and score
- Agent evals live on a spectrum from automated (fast, cheap, partial) to human (slow, expensive, complete)

## The move

Separate trajectory evaluation from outcome evaluation and measure both.

**Trajectory metrics — how the agent got there:**
- **Step efficiency:** count of tool calls, reasoning steps, and retry loops. An agent that's correct but 10x slower than necessary fails in production even if the answer is right.
- **Tool correctness:** binary pass/fail per tool call — did it select the right tool with the right arguments? This is deterministic and doesn't need an LLM judge. Compute it directly.
- **Plan adherence:** does the agent's execution match the plan it declared? Use LLM-as-judge with a rubric for "complete and logical decomposition" (RAGAS Topic Adherence, DeepEval's DAG metric for structured decision-tree scoring).
- **Reasoning quality:** does each reasoning step follow logically from the previous? Score with LLM judge using a 1-5 rubric, calibrated against 500+ human-labeled cases.

**Outcome metrics — did it work:**
- **Task completion rate:** binary pass/fail per task in a sandboxed environment where you verify the actual end state, not just the final text response. This is the ultimate metric — it catches the "right for wrong reasons" failure mode.
- **Safety and policy compliance:** red-teaming, PII handling, permission boundary testing. These are binary gates, not scores.
- **Latency and cost per task:** operational constraints are first-class evaluation targets, not afterthoughts. Track token efficiency and cost-to-completion alongside accuracy.

**The eval pipeline:**
- Build a golden test set of 50-100 representative tasks with known expected outcomes. Run before every deployment, after every model update, and whenever you modify tools or prompts.
- Implement canary evaluation: deploy new version to 5% of traffic, monitor critical metrics for 24-48 hours, compare error rates and tool usage patterns between canary and production. Degrade = automatic rollback.
- Mine production failures: when users report a problem or monitoring detects an anomaly, automatically extract the interaction, anonymize it, and add it to the regression test set.
- Integrate into CI/CD with commit-triggered, scheduled, and event-driven evaluation runs.
- Use LLM-as-judge for nuanced dimensions (reasoning quality, answer relevance, faithfulness). Target 0.80+ Spearman correlation with human judgment before trusting aggregate scores. Re-calibrate when judge model updates or system under test changes.

## Evidence

- **Research paper:** UC Berkeley benchmark study — found all eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) could be exploited for near-perfect scores without solving real tasks; one team gamed 890 tasks with a single character change — [Zylos Research, "AI Agent Evaluation and Benchmarking: Beyond Task Completion," 2026-05-13](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking/)
- **Industry analysis:** Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring of agent systems rather than model capability gaps — [Gartner, "AI Risk Management Predictions," 2026](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)
- **Framework documentation:** DeepEval (open-source,Confident AI) implements 12+ agent-specific metrics including task completion, step efficiency, tool correctness, plan quality, and reasoning quality — evaluated per trajectory and tied to trace spans for root-cause diagnosis — [Confident AI, "LLM Agent Evaluation Metrics in 2026"](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **Practitioner guide:** LLM-as-judge requires 500+ human-labeled calibration cases before trusting aggregate metrics; judge model updates, prompt changes, and system-under-test changes all shift calibration baseline and require re-calibration — [Zylos Research, "LLM-as-Judge Patterns for Agent Evaluation," 2026-05-26](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns)
- **Cloud service:** Amazon Bedrock AgentCore Evaluations (announced re:Invent Dec 2025) provides managed LLM-as-judge infrastructure for production agent evaluation — [DEV Community / AWS Community Builders, 2026-03-27](https://dev.to/aws-builders/amazon-bedrock-agentcore-evaluations-llm-as-a-judge-in-production-55oc)

## Gotchas

- **Right answer, broken reasoning is a production liability.** Outcome-only evals miss the cases where the agent got lucky. Always include trajectory metrics.
- **Judge bias is not visible in aggregate scores.** A naively configured judge can systematically prefer verbose responses, longer chains, or the first-named entity. Calibrate before trusting.
- **Benchmarks plateau fast.** A score on a static benchmark tells you the agent can solve that benchmark's tasks, not your users' tasks. Use benchmarks for capability baselines, not production readiness.
- **Token cost and latency are evaluation targets, not just outputs.** An agent that scores 95% but costs 10x more than the baseline and adds 30s of latency may not be better — it depends on your requirements.
