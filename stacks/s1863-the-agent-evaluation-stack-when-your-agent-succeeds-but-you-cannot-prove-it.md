# S-1863 · The Agent Evaluation Stack — When Your Agent Succeeds But You Cannot Prove It

Your agent works. You tested it in the dev environment. You watched it handle the happy path. You shipped it. Three weeks later a user hits an edge case your agent handled confidently — and wrongly — and there is nothing in your logs except a single 200 OK. The problem is not the agent. The problem is that you never built a way to prove the agent was working, only a way to hope it was.

## Forces

- **Agents are non-deterministic by design.** The same input does not always produce the same action. Unit tests cannot guarantee consistent behavior when the model decides differently under context drift.
- **Failures are silent and confident.** Agents generate fluent responses even with incomplete or incorrect context. There is no crash, no exception — just a wrong answer dressed in the right tone.
- **Standard benchmarks are broken.** UC Berkeley researchers found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) can be gamed to near-perfect scores without solving the underlying task. One team gamed 890+ instances of SWE-bench without touching the actual code.
- **Eval engineering is now a distinct specialty.** "Good eval engineering is now as important as good prompt engineering," reported Zylos Research in 2026. Teams that treat evaluation as an afterthought ship agents they cannot trust.

## The Move

Build a **three-layer evaluation pipeline**: offline golden-dataset evals for regression gates, trajectory-level trace capture for debugging, and production monitoring for drift detection. Treat eval engineering as a first-class engineering practice, not a post-launch checkbox.

### Golden dataset pipeline

- Define test cases as structured JSONL with `id`, `input`, `expected_behavior`, `expected_tools`, and `tags`. Each case includes rule assertions for deterministic checks.
- Cover the four evaluation objectives from the KDD 2025 survey: **agent behavior, capabilities, reliability, and safety**.
- Run the dataset against every prompt or model change in CI before deployment. This catches regressions that unit tests miss.

### Trajectory-level trace capture

- Capture the full execution path — messages, tool calls with arguments and results, per-step timings, and token usage — not just the final output.
- Use structured trace formats (LangGraph streaming, Arize Phoenix, Langfuse) so individual steps are inspectable after a failure.
- Score at the trajectory level, not the step level. A single correct step in a wrong sequence is still a failure.

### LLM-as-judge with rubric-based grading

- Use a judge model with a structured rubric that scores task completion, tool use accuracy, safety compliance, and cost efficiency.
- Calibrate the judge against human annotations using Spearman correlation. An uncalibrated judge can flip pass/fail on the same run.
- Run the judge both offline (against golden datasets) and online (against sampled production traces).

### Production trace monitoring

- Capture traces from live traffic, not just synthetic test cases. Production traffic surfaces edge cases no test suite anticipates.
- Alert on metric drift: if the judge score on a sampled trace drops, surface it before users encounter the failure.
- Use production traces to continuously expand the golden dataset — new failure patterns become new test cases.

### CI/CD regression gates

- Gate deployments on eval pass rates. A PR that degrades task completion by more than 5% or introduces a safety flag does not merge.
- Track eval metrics over time. A slow degradation across 20 PRs is invisible without a trend line.

## Evidence

- **KDD 2025 Tutorial:** SAP researchers published a systematic survey of LLM agent evaluation organizing work along two axes — evaluation objectives (behavior, capabilities, reliability, safety) and evaluation process (interaction modes, datasets, metric computation, tooling). The tutorial's GitHub repo (SAP-samples/llm-agents-eval-tutorial) includes a purchase-order benchmark with working evaluation code. — [github.com/SAP-samples/llm-agents-eval-tutorial](https://github.com/SAP-samples/llm-agents-eval-tutorial)
- **UC Berkeley Benchmark Crisis:** Researchers examined eight prominent agent benchmarks and found all eight exploitable — achieving near-perfect scores without solving actual tasks. This renders benchmark leaderboards unreliable for production readiness assessment. — [Zylos Research, May 2026](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **LangGraph Agent Eval Harness:** An open-source toolkit (praveenpke/agent-eval-harness) implements the full pipeline: golden dataset → trajectory capture → rule + LLM-as-judge scoring → CI gate. Runs keyless with a deterministic heuristic fallback when no API key is set. — [github.com/praveenpke/agent-eval-harness](https://github.com/praveenpke/agent-eval-harness)
- **Production trace vs. golden dataset trade-off:** Tessary's analysis argues production traces eliminate dataset drift because evaluation data is always current and carries the evidence needed to trace failures to specific changes. Golden datasets require continuous maintenance. — [tessary.ai, June 2026](https://tessary.ai/blog/production-traces-vs-golden-datasets-llm-evals)
- **InfoQ Evaluation Framework:** A 2026 practitioner's analysis recommends hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) for repeatability with human judgment for tone, trust, and contextual appropriateness. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Evaluating outputs beats evaluating steps.** Checking whether a tool was called is weaker than checking whether the tool call was the right action given the full context. The agent's reasoning chain matters more than individual API calls.
- **Golden datasets rot fast.** A dataset built in January reflects the agent as it was in January. Without a pipeline to ingest production failure patterns back into the dataset, you are testing last month's agent.
- **LLM-as-judge needs its own evaluation.** Judges are not ground truth. Calibrate against human-labeled samples before trusting any rubric. Teams that skip this step get false confidence — the judge passes runs that human reviewers would fail.
- **Coverage is not the same as quality.** Running 1,000 synthetic test cases does not mean the agent is safe in production. The goal is a small, job-specific metric set that changes as production failures change, not maximum test count.
