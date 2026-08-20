# S-2920 · The Multi-Dimensional Eval Stack — When Success Rate Tells You Nothing About Your Agent

Your agent scores 91% on task completion. Your error rate is 0.3%. You feel good about this. Then you discover it's been routing 16% of requests to the wrong handler for three weeks, returning confident HTTP 200s with useless output — and the only person who noticed was a customer who emailed support. Success rate and error rate are infrastructure metrics. They measure whether the agent ran, not whether it ran correctly.

## Forces

- **Task completion ≠ quality.** A run can reach a valid endpoint, return a well-formed response, and still be wrong, incomplete, or harmful — nothing infrastructurally "failed."
- **Cascading errors hide in plain sight.** A bad tool call in step 3 corrupts steps 4–50. Checking only the final output misses the root cause and masks which failures are correlated.
- **Safety is orthogonal to success.** An agent completing 90% of tasks while violating policy 5% of the time is more dangerous than one completing 70% safely — yet most teams conflate the two into a single score.
- **Benchmarks don't translate.** Static task-completion benchmarks (SWE-bench, WebArena) drove agent development but fail to predict production reliability, cost efficiency, or safety. UC Berkeley researchers found eight major benchmarks largely broken as proxies for real-world agent quality.
- **Cost is a first-class quality dimension.** An agent that completes 95% of tasks at 3× the token budget of a competitor is not the better agent — yet cost is almost never evaluated alongside quality.

## The move

Treat agent evaluation as a multi-dimensional measurement problem, not a pass/fail gate. Measure at least four independent dimensions across every run, and instrument your system to catch silent failures before users do.

**Instrument first.** Every agent run must produce a structured trace: the input, every LLM call (prompt + response + token counts + latency), every tool call (name + arguments + response + latency), every decision point, and the final output. Without traces, evaluation is guesswork. Tools like Lucidic (`lai.init()`), OpenTelemetry SDKs, and LangSmith provide this with minimal code changes.

**Define four independent metric dimensions.** Track them separately — never combine into a single score:

| Dimension | What it measures | Key metrics |
|---|---|---|
| **Task completion** | Did the agent finish the job correctly? | Success rate, pass@k, goal achievement rate |
| **Step quality** | How did it get there? | Tool selection accuracy, step efficiency, trajectory length vs. minimum required, plan adherence |
| **Safety / policy** | Did it behave correctly? | Policy adherence rate, prompt injection resilience, hallucination rate, bias detection |
| **Efficiency** | What did it cost? | Tokens per task, API calls per task, latency p50/p95, cost per successful task |

**Catch silent failures with output-grounded assertions.** HTTP 200 is not a quality signal. Define correctness assertions that check the actual output — structured schema validation, reference-grounded comparisons, LLM-as-judge scoring on specific criteria. Tessary documented a routing bug that hit 0.8% of requests, then 16%, and existing evaluations missed it for weeks because nothing checked whether the output was useful.

**Run evals at three scopes.** Per Braintrust and DeepEval's framework:

- **Component-level:** Test individual tool-calling decisions in isolation — did the agent pick the right tool, with the right parameters? Fast, deterministic, caught by unit tests.
- **Trajectory-level:** Test the full ordered sequence — did the agent follow the right plan, in the right order, with the right adaptations? Catches cascading errors.
- **Production-level:** Monitor real traffic with automated assertions, sampling, and LLM-as-judge scoring. Catches silent failures that lab testing misses.

**Evaluate safety independently from task success.** Anthropic's eval guide (Jan 2026) makes this explicit: a "correct" agent that achieves its goal through unsafe means (credential exfiltration, production overwrites, policy violations) is worse than a safe failure. Safety eval must have its own scorecard, its own threshold, and its own veto power.

**Use LLM-as-judge with structured criteria, not overall scores.** A single 1–10 score conflates multiple dimensions and correlates poorly with ground truth. Define specific rubrics: "Did the response cite sources from the retrieved context?" — yes/no. "Were all required fields present?" — yes/no. Multiple targeted assertions > one global judgment.

**Set cost-per-task budgets and alert on breach.** Amazon Bedrock's AgentCore evaluation library tracks cost per task as a first-class metric. Define a maximum economically viable cost per task type, and treat exceeding it as a failure mode equivalent to a crash.

## Evidence

- **Amazon Engineering (Feb 2026):** Published a real-world evaluation framework built from thousands of agents deployed across Amazon organizations. Their core finding: traditional LLM evaluation treats systems as black boxes and evaluates final outcomes only. Agentic AI requires assessing emergent system behaviors — tool selection accuracy, multi-step reasoning coherence, and session-level state management. Their framework has two components: a generic evaluation workflow and a systematic agent evaluation library in Bedrock. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Anthropic Engineering (Jan 2026):** "The capabilities that make agents useful — autonomy, intelligence, flexibility — also make them harder to evaluate. Evaluation strategies must match the complexity of the systems they measure." Their guide defines the eval vocabulary (task, trial, grader, harness) and describes three eval scopes: component, trajectory, and production-level. Explicitly recommends treating safety as an independent dimension. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Tessary (Jun 2025, updated Aug 2026):** Documented how a routing bug touched 0.8% of requests, then 16% in an hour, and evaluations missed it for weeks. Demonstrates that HTTP status codes and error-rate dashboards measure protocol completion, not output correctness. Their detection approach: output-grounded assertions, behavioral diffing against baseline traces, and user-feedback correlation. — [tessary.ai/blog/silent-llm-agent-failures](https://tessary.ai/blog/silent-llm-agent-failures)

## Gotchas

- **Don't combine dimensions into one score.** Averaging task completion, cost, and latency into a single "quality score" hides tradeoffs and makes regression diagnosis impossible. Each dimension should have its own threshold and alert.
- **Don't trust benchmark scores as production proxies.** UC Berkeley researchers found eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR) largely fail to predict real-world reliability. Your internal eval against your actual use cases matters more than any published benchmark.
- **Don't evaluate only the final output.** Agents produce trajectories — checking only the endpoint misses the cascading bad decisions that corrupted the path. A result that "looks right" may have gotten there through an unsafe or inefficient route that will fail on the next input.
- **Don't skip step efficiency.** If the minimum number of tool calls required is three and the agent takes seven, you're paying 2.3× the cost per task unnecessarily. Track trajectory length against a minimum-required baseline, not just absolute counts.
- **Don't let LLM-as-judge be your only production signal.** LLM judges are useful but noisy and can be gamed. Combine them with deterministic assertions (schema validation, reference comparisons) and user-feedback loops.
