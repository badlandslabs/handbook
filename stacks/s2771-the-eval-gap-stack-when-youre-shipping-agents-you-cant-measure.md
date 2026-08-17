# S-2771 · The Eval Gap — When You're Shipping Agents You Can't Measure

You're shipping a customer-facing AI agent. You updated the prompt last Tuesday. It passed your review. It shipped. You have no idea if it's better or worse than before. You don't run evals — you don't even know what "passes" would mean. Meanwhile, across 6,259 production agents in a large-scale reliability study (early 2026), the aggregate success rate was 56.6%. You're probably below that. This is the **eval gap**: most teams have no systematic way to know whether their agent is getting better or worse.

## Forces

- **LLM-as-a-judge feels like a solution but has a reliability crisis.** Judges are stochastic — same input, different output — and common practices (single evaluations, inter-rater reliability metrics) don't capture true consistency. One study of 21 judges found exact-match agreement systematically overstates discriminative ability (arXiv:2606.19544).
- **The flywheel nobody builds.** Production failures are the highest-value test cases — authentic edge cases, real input distributions, concrete definitions of "broken." But most teams don't capture them, so they keep shipping the same edge cases to users.
- **pass@k vs. pass^k is a reliability vs. capability trap.** pass@k asks "can this agent ever succeed?" pass^k asks "does this agent succeed every time?" For customer-facing agents, pass^k is what matters — but a 75% per-trial success rate looks fine on pass@k and is only 42% on pass^k.
- **Offline and online eval serve different purposes.** Offline test sets gate releases. Online production monitoring catches the 30–40% of failures that don't surface in offline testing. Teams do one or the other; both are needed.
- **The lab-to-prod gap is massive and underestimated.** An agent scoring 90% in testing can drop to 70% in production. Enterprise agents can see gaps up to 37%. Most evaluation happens in lab conditions that don't reflect real traffic, real tools, or real users.

## The move

Build an evaluation flywheel that feeds production failures back into a golden dataset, gates releases on pass^k, and keeps online monitoring running at all times.

- **Capture from production, not notebooks.** Instrument every agent run with structured traces (tool calls, retrieval steps, reasoning paths). Every production failure is a candidate test case — extract the input, the failed trajectory, and the expected correct behavior. This is the highest-signal data you will ever get.
- **Run multiple trials; gate on pass^k, not pass@k.** An agent with 75% per-trial reliability has only a 42% chance of passing 3 consecutive trials. If users expect consistent quality every time, your release gate should measure pass^k across k≥3 trials. pass@k is useful for development (how capable is this?), pass^k is the production metric (can users trust this?).
- **Validate your evaluator before you trust it.** LLM-as-a-judge introduces a second probabilistic system on top of your agent. Before relying on it, calibrate against human annotations: run judge scores on a labeled sample, compute Spearman correlation, and reject judges with weak correlation. Without this, you are measuring noise.
- **Measure groundedness and semantic distance, not just task success.** A task can "succeed" (agent reached the end of its flow) while hallucinating context or using the wrong tool. Track whether the agent retrieved correct context, whether its final answer is semantically close to ground truth, and whether it called the right tools in the right order.
- **Harden the golden dataset over time.** Start with synthetic test cases from subject matter experts. Layer in production failures. Remove cases that are no longer discriminative (100% pass rate = no signal). The dataset is a living artifact; stale tests give false confidence.
- **Dual-track: CI/CD offline gates AND production online monitoring.** Offline: run the full golden dataset against every prompt change, model swap, or tool update. Fail the PR if pass^k drops. Online: instrument live traces with automated scoring on a sample of production runs. Catch what offline misses — real users, real data, real edge cases.

## Evidence

- **Benchmark study:** Across 4.49 million tests on 6,259 production agents in 10 geographic regions, aggregate success rate was 56.6% (arXiv:2507.21504v1, Mohammadi et al., KDD 2025). Lab-to-production gaps up to 37% observed for enterprise agents.
- **Production regression flywheel:** Arthur describes the loop: production failure → trace capture → test case extraction → golden dataset addition → CI/CD gate. Every failure becomes infrastructure for preventing that failure's recurrence. — [https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **pass^k math:** AWS AgentCore evaluation blueprint demonstrates that a 75% per-trial success rate yields only 42% on pass^3. Customer-facing agents require consistency metrics, not capability metrics. — [https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-a-production-blueprint-with-strands-and-agentcore/](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-a-production-blueprint-with-strands-and-agentcore/)
- **LLM-as-judge validation crisis:** Study of 21 judges across 9 providers on MT-Bench, JudgeBench, and RewardBench found that exact-match agreement overstates discriminative ability. Stochastic outputs and fixed randomness do not guarantee reliability. — [https://arxiv.org/abs/2606.19544](https://arxiv.org/abs/2606.19544) and [https://arxiv.org/abs/2412.12509](https://arxiv.org/abs/2412.12509)
- **Teams flying blind:** Per LangChain's 2026 State of AI Agents report, only 52.4% of teams run offline evaluations and only 37.3% run online evals — meaning most teams ship without systematic quality measurement. — [https://mastra.ai/articles/ai-agent-evaluation](https://mastra.ai/articles/ai-agent-evaluation)
- **Eval tooling:** DeepEval (Confident AI) provides pytest-style agent unit testing with multi-trial support, trace-level scoring, and CI/CD integration. — [https://deepeval.com/docs/getting-started-agents](https://deepeval.com/docs/getting-started-agents)

## Gotchas

- **Don't use pass@k as your release gate.** It rewards capability (can this ever work?) over reliability (can users trust this every time?). If your agent has a 90% pass@k and a 65% pass^3, every third customer interaction fails.
- **LLM judges are not reliable out of the box.** Run calibration checks against human-labeled examples. Without this step, your "eval" is measuring the judge model's mood as much as the agent's quality.
- **Synthetic golden datasets go stale fast.** Cases that your agent always passes provide zero signal. Rotate them out. Cases from production failures that have been fixed may also lose discriminative power — track pass rates per test case.
- **Offline evals miss what production does.** The eval gap between lab and prod is real and structural. Offline testing is necessary but not sufficient — you need online monitoring on live traces to catch the long tail.
- **Soft failures are still failures.** An agent that completes its task but uses the wrong tool, retrieves irrelevant context, or produces a subtly wrong answer has failed — even if the final output looks plausible. Track intermediate steps, not just end-state.
