# S-1126 · The Evaluation Stack — When Your Benchmark Says 90% and Users Are Still Angry

Your agent scores 90% on SWE-bench. It gets merged into production. Within a week, users are filing complaints about broken workflows and runaway costs. The benchmark didn't lie — it just measured the wrong thing. The agent could fix isolated Python bugs but couldn't navigate a real codebase without making a mess. The fix isn't a better benchmark. It's a multi-dimensional evaluation architecture that measures what actually matters in production.

## Forces

- **The endpoint trap.** Single-number accuracy scores only assess the final output. An agent can reach a correct answer through a reckless, expensive, or policy-violating path — and endpoint scoring will call it a success. Production cares about *how* you got there, not just *that* you did.
- **The benchmark-prod gap.** SWE-bench measures isolated bug-fix capability. BFCL measures function-call correctness. Tau-Bench measures policy-compliant dialogue. None of them measure whether your agent actually completes business workflows, stays within budget, or recovers gracefully from unexpected states. Teams that rely on public benchmarks are flying blind in production.
- **The evaluation-is-not-testing paradox.** Traditional software has deterministic tests with expected outputs. Agents are probabilistic — the same input produces different trajectories. You cannot assert against a single string. You need a statistical measurement framework, not a pass/fail gate.
- **The judge calibration problem.** LLM-as-judge agrees with human reviewers ~85% of the time (higher than two humans agreeing on the same task), but a poorly calibrated judge produces conclusions *opposite* to reality. The gap between a naive judge and a well-calibrated one is wide enough to justify the calibration investment.
- **Cost and latency are first-class metrics.** An agent that achieves 100% task completion at 10x the cost and 5x the latency of a competitor is not winning. Benchmarks don't measure this. Teams shipping agents to real users often discover too late that their "successful" agent is economically unviable.

## The Move

Measure agents across three evaluation levels, four metric dimensions, and at least two judge types:

**Three evaluation levels:**
- **End-to-end:** Did the agent complete the task? (task success rate, pass@k)
- **Trajectory-level:** Was the path efficient and sound? (steps taken, tools used, cost incurred, time elapsed)
- **Component-level:** Which specific tool, retriever, or sub-agent caused a failure? (tracing to isolate)

**Four metric dimensions (per Google Cloud Agent Factory, 2025):**
- **Outcome quality:** Goal achievement, output accuracy, hallucination avoidance, safety
- **Reasoning quality:** Logical step decomposition, coherence of chain-of-thought, planning adherence
- **Tool utilization:** Correct tool selection, correct parameters, efficiency (no redundant calls), relevancy (didn't invoke irrelevant tools)
- **Safety & policy:** Did the agent comply with behavioral policies? Did it escalate when appropriate?

**Two judge types:**
- **Deterministic checks** for exact things: Is the tool name valid? Do parameters match the schema? Is the output format correct? Does the JSON parse? These are cheap, fast, and unambiguous — use them first.
- **LLM-as-judge** for context-dependent quality: Is the answer helpful? Is the reasoning sound? Did the agent follow the policy? Calibrate against a golden dataset of human-labeled examples before trusting the scores.

**The eval pipeline that ships:**
1. Build a golden dataset from **real production failures**, not synthetic scenarios. Every time the agent breaks in production, file a bug that includes the full trace — then add a representative case to the eval suite.
2. Run **50–200 representative tasks** covering main use cases plus known edge cases. Run each task 10+ times to capture variance.
3. Track **trajectory metrics** alongside outcome metrics: steps-to-complete, tokens-per-task, cost-per-task, tool-call count, tool diversity, error recovery rate.
4. Gate on **regression, not just pass rate.** A new version that improves one metric but degrades another by more than a threshold (e.g., cost up 15%, or error recovery down 5%) should block a deploy even if overall success rate is flat.
5. Use **trace replay** to capture full execution paths — every tool call, argument, return value, and reasoning step. Replay these traces against updated agents to detect behavioral drift.

## Evidence

- **Engineering blog (Google Cloud Agent Factory, Oct 2025):** "Agent evaluation is more like a job performance review — assessing a complex system's behavior, including its autonomy, reasoning, tool use, and ability to handle unpredictable situations." Proposes a four-layer evaluation framework: outcome, reasoning, tool utilization, and safety. — [Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/agent-factory-recap-a-deep-dive-into-agent-evaluation-practical-tooling-and-multi-agent-systems)

- **Practitioner blog (jamesm.blog, Jun 2026):** "Endpoint evals miss failure modes that hurt in production — an agent can reach the right answer through a reckless path." Documents a minimum workload-eval checklist: 50–200 real examples, per-step rubrics, 10+ runs per example, statistical regression tracking, held-out set. — [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)

- **Primary research (Confident AI, Jun 2026):** Documents the benchmark-prod gap in depth: "A model that scores 80% on SWE-bench verified could still catastrophically hallucinate tool calls, invoke APIs with malformed parameters, or fail to recognize when a user query has no valid tool answer." Proposes three-level evaluation (end-to-end, trajectory, component) and four metric clusters (tool calling, planning, task completion, reasoning). — [Confident AI](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

- **Research review (Benchmarking Agents, Apr 2026):** Compares tool-use benchmarks: BFCL (function-calling), Tau-Bench (policy-compliant dialogue), ToolBench (breadth across 16K+ APIs), T-Eval (fine-grained diagnostic). Recommendation: "Quote BFCL + Tau-Bench for honest 2026 tool-use claims. Add T-Eval for diagnostic depth." — [Benchmarking Agents](https://benchmarkingagents.com/best-benchmarks-for-tool-use)

## Gotchas

- **Pass@4 inflation is real.** Tau-Bench shows an 8–12 point gap between pass@1 and pass@4. If you report pass@4 numbers without noting the configuration, you're overstating capability. Always report the sampling configuration alongside the score.
- **The golden dataset needs maintenance.** A golden dataset built once and never updated becomes stale — it stops catching new failure modes. Treat it like a codebase: review and extend it on a regular cadence, ideally driven by production failure traces.
- **LLM-as-judge has known biases.** It favors verbose outputs, agrees with positions it has seen in training, and rates the first output in a comparison slightly higher (position bias). Calibrate with known-good and known-bad examples before using judge scores for gating decisions.
- **Cost-per-task is not optional.** If your eval suite doesn't include token counts and estimated cost per trajectory, you will discover your agent is unprofitable only after it runs in production at scale. Track it from day one.
- **Trajectory metrics require instrumentation.** You cannot measure what you cannot observe. Distributed tracing (e.g., OpenTelemetry with a platform like Langfuse, Phoenix, or Honeycomb) is not optional — it's the data layer that makes eval possible.
