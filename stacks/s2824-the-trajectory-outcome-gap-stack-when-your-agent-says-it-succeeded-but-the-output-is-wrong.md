# S-2824 · The Trajectory-Outcome Gap Stack — When Your Agent Says It Succeeded But the Output Is Wrong

When your eval suite reports 95% success and production shows 30% silent failure — the agent completed the task, but incorrectly, and told you it worked. The gap between task completion and correct completion is the central evaluation failure mode for production agents in 2025–2026. You need both trajectory metrics and outcome metrics, and most teams only measure one.

## Forces

- **Task completion ≠ correct completion.** Agents confidently declare success while producing wrong outputs. A refund agent may complete the workflow correctly but refund the wrong amount. A coding agent may apply a patch that passes the test suite but breaks production. Your success-rate metric is lying to you.
- **Outcome metrics miss the reasoning chain.** A final-output pass/fail tells you nothing about whether the agent reasoned correctly, chose the right tools, recovered from errors, or hallucinated intermediate state. Two agents with identical success rates can have completely different reliability profiles at the edges.
- **Trajectory metrics are expensive and noisy.** Step-by-step evaluation of agent reasoning chains requires more LLM calls, more compute, and harder ground truth. Teams default to outcome metrics because they're cheap, even when they're insufficient.
- **Standard APM misses agent failures entirely.** Latency, error rates, and HTTP codes are all green while the agent silently corrupts data or calls the wrong API. Traditional observability does not see inside the agent's decision graph.
- **The benchmark illusion.** SWE-bench Verified reliably predicts isolated bug-fix performance in Python repos but does not predict how an agent will handle polyglot codebases, multi-file refactors, or schema drift — the tasks that actually break production.

## The Move

Separate trajectory evaluation from outcome evaluation, then gate merges and deployments on both.

**1. Track two metric families in parallel:**
- **Outcome metrics:** Did the agent solve the problem? (task completion rate, correctness rate, error recovery rate)
- **Trajectory metrics:** How did it get there? (tool call accuracy, step efficiency, plan coherence, hallucination flags)

**2. Implement multi-trial consistency scoring.** Run the same task 3–5 times with temperature > 0 and measure consistency. A 100% success rate on a single run with 40% consistency across trials is a fragile agent. Consistency is a cheaper proxy for trajectory robustness than full trace analysis.

**3. Use LLM-as-judge with calibration, not replacement.** Target 0.80+ Spearman correlation with human judgment before trusting judge scores. Validate the judge annually against human-labeled golden cases — judges drift. For high-stakes outputs, keep a human-in-the-loop sample (Label Studio found 74% of production agents still rely on human review alongside automated judges).

**4. Build a 3-tier rubric: dimensions → sub-dimensions → test items.** Practical target from elite teams: 7 dimensions (e.g., correctness, tool use, coherence, safety, efficiency, recoverability, helpfulness) × ~3–4 sub-dimensions each × specific test items = 130+ measurable assertions per agent.

**5. Integrate eval gates into CI/CD — not as optional quality checks but as merge blockers.** Run trajectory + outcome evals on every prompt change, model swap, and tool definition update. Use commit-triggered, scheduled, and event-driven triggers. The Red Hat team for their it-self-service-agent documented this as a distinct discipline: "agent-native CI/CD."

**6. Create a feedback loop from production traces back to eval datasets.** Capture real failure cases from production, triage them, and add them to the eval suite within 48 hours. Production traffic is the most representative test set you'll ever have — most teams build evals from synthetic data and wonder why they don't catch production failures.

## Evidence

- **Engineering blog (Vindler):** Teams measuring only task completion reported 95% success rates while independent audit found only 70% of completions were actually correct — a 25-point gap invisible to outcome-only metrics. Silent data corruption went undetected for weeks. — [Agent Evaluation at Scale: Lessons from 2025's Production Failures](https://vindler.solutions/blog/agent-evaluation-at-scale)
- **Benchmark analysis (EngineersOfAI):** SWE-bench Verified scores above 50% on the verified subset reliably predict bug-fix capability in Python repos, but teams deploying based on SWE-bench scores discovered their agents couldn't handle 8-file refactors or polyglot codebases — the benchmark measured the wrong thing for their use case. — [SWE-bench Verified](https://engineersofai.com/docs/agentic-ai/agent-evaluation/swe-bench-verified)
- **Research paper (arXiv 2510.09738):** The "Judge's Verdict" benchmark tested 54 LLMs as judges and found that LLM-as-judge achieves 0.80+ Spearman correlation with human judgment only after filtering for strong alignment judges — weak judges in the pool significantly degraded evaluation quality. — [Judge's Verdict: A Comprehensive Analysis of LLM Judge Capability](https://arxiv.org/html/2510.09738v1)
- **Market research (Galileo Labs):** 74% of production agents in 2026 still rely on human-in-the-loop evaluation alongside automated judges. 40%+ of agentic AI projects are expected to be cancelled by 2027 due to inability to measure reliability, not model capability. — [Agent Evaluation Framework: Metrics, Rubrics, and Benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Don't evaluate only on final output.** Correct outputs can come from broken reasoning. If the agent got lucky, it will fail on the next variation. Label Studio documented a refund agent that completed the workflow correctly but issued the wrong amount — final output was "success," the actual outcome was a financial error.
- **Don't trust a single-run success rate.** Run each eval task 3–5 times. An agent at 100% single-run success but 40% consistency across trials is not production-ready, regardless of what your dashboard shows.
- **Don't let the judge go uncalibrated.** LLM-as-judge correlations with human judgment drift over time as model versions change and prompt distributions shift. Re-validate the judge against human-labeled golden cases on a regular schedule — at minimum quarterly, or on every major model change.
- **Don't use production APM for agent quality monitoring.** Latency and error rates tell you the agent ran, not whether it ran correctly. You need trace-level analysis that segments where in the execution graph failures occurred — memory retrieval error vs. tool execution error vs. planning failure each require different fixes.
- **Don't build evals entirely from synthetic cases.** Real production failures are the most representative test cases you have. The feedback loop from production trace → eval dataset is not optional; without it, your eval suite converges on the failures you already know about and misses the ones you don't.
