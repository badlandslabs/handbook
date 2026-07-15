# S-1133 · The Trajectory-First Eval Stack — When Your Agent Succeeds But You Can't Tell If It Got Lucky

An agent returns a correct answer. You ship it. Three weeks later it loops forever on a slightly different input and costs $200 in tokens. Your final-answer eval passed every time — because you never measured the *path*. Trajectory-first evaluation tracks tool selection, step count, loop detection, and recovery behavior alongside output quality. It is the difference between knowing your agent works and knowing *how* it works.

## Forces

- **Correct answer, wrong path.** An agent can reach the right answer via a dangerous or inefficient sequence — calling a privileged tool it shouldn't, retrying 40 times instead of once, or backtracking through a cascade of errors. Final-answer scoring rewards the outcome and ignores the method. In production, the path is often where failures live.
- **Step count is non-deterministic.** The same input can trigger 3 steps or 23 depending on model confidence, context, and randomness. Without tracking step efficiency, you have no baseline for whether a new prompt or model version is making the agent more or less efficient.
- **Tool-call errors compound.** A wrong tool selection at step 2 can make steps 3–N irrelevant. Most evals only score the final output, so a silent tool-call failure at step 2 that the agent recovered from never gets counted — even though it is exactly the failure mode you need to catch.
- **Trajectory scoring is expensive.** Running an LLM-as-judge over every step of every trace is cost-prohibitive at scale. Teams need a strategy for sampling, aggregating, and alerting on trajectory quality without auditing every turn.

## The Move

The core practice: instrument your agent to emit structured traces, then evaluate both the trajectory *and* the outcome. Score at three granularities and route them into your pipeline differently.

**Step-level: instrument and alert, don't grade everything.**
- Wrap every tool call, LLM call, and branch point in a span with a unique ID
- Log: tool name, arguments, response status, duration, token cost, error flag
- Attach parent trace ID so you can reconstruct the full execution tree
- Route step-level anomalies (tool errors, timeouts, unusual latency) to alerting immediately — you don't need LLM grading for a tool returning a 500

**Node-level: score tool selection correctness on a sample.**
- On a curated sample of traces (not every run), use an evaluator to judge: did the agent pick the right tool at this step? Were the arguments correct?
- Braintrust's evaluation framework breaks this into: (1) did the plan make sense, (2) did it choose the correct next step, (3) did it invoke the correct tool with correct arguments, (4) did it properly use the tool's output
- This is where loop detection lives: flag when the same tool-with-same-arguments appears twice in a trace without an intervening state change

**Session-level: aggregate trajectory metrics for trend detection.**
- **Step efficiency ratio** = actual steps ÷ minimum required steps (1.0 = perfect efficiency; 3.7 = agent took 3.7× longer than needed)
- **Tool-call accuracy** on the sample: % of tool invocations that were correct tool + correct arguments
- **pass@k vs pass^k**: pass@k measures capability ceiling (at least 1 success in k tries); pass^k measures reliability (success on *all* k tries). The gap between them reveals non-determinism. AgentClash notes that enterprise release gates should use pass^k — "a 70% agent that works reliably is more deployable than an 80% agent that is unpredictable"
- **Cost per task** at session level: track tokens and API spend per trace, not just per call

**Close the loop: production → eval signal.**
- PagerDuty's implementation with Arize routes production trace anomalies into golden datasets. When a production trace fails a quality check (hallucination, groundedness failure, wrong tool), that input gets added to the eval dataset. This is the feedback loop that keeps offline evals from going stale.
- Monte Carlo's five-metric framework treats trajectory and step efficiency as first-class alongside output quality and tool-call accuracy. Their production monitoring tracks step count versus expected minimum as a regression signal — if median steps jump from 4.2 to 7.8 after a model swap, that's an alert before costs spike.

**The sampling strategy that makes trajectory eval affordable.**
- Run full trajectory scoring (LLM-as-judge at step level) on 5–10% of production traces — enough to catch regressions, not enough to break the budget
- Run step-level instrumentation (tool errors, latency, token count) on 100% of traces — this is cheap structured data, not LLM calls
- Use the 5% sample to calibrate thresholds for the 100% metrics: when tool error rate on the sample correlates with a drop in trajectory quality, set the error rate threshold as the production alert

## Evidence

- **Company engineering post:** PagerDuty + Arize built a production observability pipeline that treats AI-specific failures (hallucinations, groundedness failures, tool-call errors) as first-class incidents. Their golden datasets are maintained as Arize datasets with experiment tracking, enabling side-by-side comparison of outputs across runs. Production trace anomalies feed back into the eval dataset to prevent regression. — [PagerDuty Engineering](https://www.pagerduty.com/eng/pagerduty-arize-building-end-to-end-observability-for-ai-agents-in-production/)
- **Developer guide:** OpenAI's Agents SDK cookbook demonstrates Langfuse integration that captures full nested span trees — every LLM call, tool invocation, and intermediate step — then attaches eval scores to traces via Langfuse's scoring API. Token usage and cost per session are tracked at the trace level. — [OpenAI Developers / Langfuse](https://developers.openai.com/cookbook/examples/agents_sdk/evaluate_agents)
- **Research:** The CLEAR framework's empirical study (300 enterprise tasks, 6 agents) found that agents optimized for benchmark accuracy are 4.4–10.8× more expensive than cost-aware alternatives at comparable efficacy — and that reliability (measured as pass^k consistency across runs) drops from 60% single-run to 25% 8-run consistency, making trajectory-level reliability measurement essential for procurement. — [arXiv:2511.14136](https://arxiv.org/pdf/2511.14136)

## Gotchas

- **Measuring trajectories without instrumenting is impossible.** If your agent doesn't emit structured spans for each step, you cannot reconstruct the trajectory. Do the instrumentation first — it's the prerequisite for everything else.
- **LLM-as-judge at step level is too expensive for 100% of traces.** Sample aggressively. The goal is enough trajectory-grounded scoring to calibrate the cheaper signal (tool error rate, step count) that you run on everything.
- **pass@k is misleading for release decisions.** It tells you the ceiling; pass^k tells you what to expect in production. If your agent passes 8/10 runs (pass@10 = 100%, pass^10 = 0%), you have a reliability problem your leaderboard score won't reveal.
- **Trajectory evals go stale faster than final-answer evals.** When you change a tool's schema or add a new tool, the "correct path" changes. Build in a review trigger: any tool addition or modification should prompt a trajectory eval refresh, not just a final-answer re-run.
