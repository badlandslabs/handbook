# S-1062 · The Production Drift Stack — When Your Lab Evals Pass and Your Production Fails Silently

Your agent passes every benchmark. Hitl accuracy looks great. Then you discover it's been making systematically wrong decisions for a specific user cohort — for weeks — without triggering a single alert. The problem isn't the model. It's that lab benchmarks and standard metrics are blind to the failure modes that only emerge in continuous production operation.

The production drift stack is the evaluation approach that catches what lab evals miss: compounding decision errors, tool failure cascades, and drift patterns that accumulate silently until the damage is already done.

## Forces

- **Standard metrics are calibrated for snapshots, not trajectories.** AUC, precision@k, and accuracy scores tell you about the average case at a point in time. They miss systematic bias toward subgroups and they don't measure whether errors compound or self-correct across sequential decisions.
- **Lab benchmarks evaluate the model; production evals must evaluate the system.** Your tool bindings, error recovery paths, and orchestration logic introduce failure modes that never appear in MMLU, HumanEval, AgentBench, or BIG-bench — all of which are designed for controlled, single-session, lab-scale settings.
- **Ground truth disappears in long-horizon tasks.** When an agent decomposes a task across dozens of steps, there is no labeled final answer to score against. You need process evaluation, not just outcome evaluation.
- **The lag between failure and detection is the failure.** Standard metrics that only detect 3 of 7 production failure modes — and only after multiple evaluation cycles — leave a long enough window for real damage.

## The move

Measure what lab benchmarks miss: trajectory-level failure patterns, tool-level degradation signals, and cross-cycle drift — not just end-state accuracy.

- **Track the decision trajectory, not just the outcome.** Instrument every tool call, every branch point, and every recovery action. A final correct answer achieved through wrong reasoning is a latent failure waiting to surface on the next similar case.
- **Measure tool call precision and recall separately.** Confident AI's research shows that component-level checks — did the agent call the right tool? with the right arguments? — catch failures that end-to-end task completion metrics miss entirely. A task can "succeed" while a tool call silently fails in a way that propagates.
- **Use LLM-as-judge with human calibration, not as the primary signal.** Goldens (labeled reference examples) catch regressions in CI; LLM-as-judge provides broad coverage; human rubric review on a sampled trace set validates that your automated metrics aren't gaming themselves. Confident AI's Jeffrey Ip reports that this three-layer approach is the standard at teams achieving high reliability in production.
- **Detect distribution collapse before it shows up in accuracy.** When the agent's output distribution narrows over time (it stops exploring alternatives and converges on a "safe" response pattern), accuracy metrics look fine while the agent is silently degrading on novel cases. Track entropy of response distributions alongside accuracy.
- **Set operating envelope monitors, not just quality scores.** Cost per session, latency per step, and token budgets are failure signals. Confident AI recommends tracking cost and latency in the same traces as quality — an agent that starts taking 3x more steps per task is already in a degraded state even if the final output looks correct.
- **Re-run critical scenarios on every model or prompt change.** Models are stochastic. A single pass on a golden test case is unreliable. Confident AI recommends re-running goldens in CI pipelines so that a flaky pass doesn't mask a real regression.
- **Close the loop with cross-cycle regression detection.** The Amazon engineering blog recommends comparing agent behavior across evaluation cycles — not just within a cycle — to catch drift patterns that emerge gradually. This is distinct from per-run metrics and requires a temporal evaluation layer.

## Evidence

- **arXiv paper (2026):** A systematic study of 7 failure modes unique to production agentic systems at billion-event scale found that standard metrics (AUC, precision@k, accuracy) fail to detect 4 of the 7 entirely and detect the remaining 3 only after multiple evaluation cycles. Specific failure modes include cascading decision errors, silent tool degradation, distribution collapse, cross-surface inconsistency, explanation decoupling, latency-driven correctness erosion, and proxy goal convergence. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **Company engineering post:** Amazon's AI agent evaluation framework (2025) emphasizes that agentic AI evaluation must assess accuracy of tool selection, coherence of multi-step reasoning, efficiency of memory retrieval, and overall task completion — dimensions that traditional black-box evaluation misses entirely. HITL (human-in-the-loop) evaluation is described as critical for multi-agent systems specifically to catch coordination failures, inter-agent communication breakdowns, and conflict resolution failures that automated metrics miss. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)
- **Industry survey:** Cleanlab's survey of 1,837 engineering leaders found that only 95 had AI agents live in production — and fewer than 1 in 3 of those were satisfied with their observability or guardrail solutions. 70% of regulated enterprises reported rebuilding their AI stack every 3 months or faster. Only 5% cited accurate tool calling as their top challenge, suggesting widespread underestimation of tool-level failure modes. — [Cleanlab AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Framework docs:** Confident AI's evaluation guide (April 2026) documents the three-layer eval stack (goldens for regression, LLM-as-judge for broad coverage, human rubrics for calibration) and the specific practice of tracking cost and latency alongside quality in the same trace data. — [Confident AI Blog](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **Don't rely on end-state accuracy alone.** A system can achieve AUC 0.87 and still produce decisions that are "internally coherent but systematically wrong for a specific user cohort" (Pandey, 2026). Accuracy metrics are the last thing to break and the first thing to give false confidence.
- **Don't treat evaluation as a one-time pre-deployment gate.** Gartner projects that by 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring rather than model capability gaps. The evaluation system must be continuous and temporal, not a launch-day checkpoint.
- **Don't skip component-level checks.** The temptation is to judge an agent only by whether it completed the task. Tool call accuracy, argument correctness, and recovery path quality are leading indicators that predict task failure before it manifests in the final output.
