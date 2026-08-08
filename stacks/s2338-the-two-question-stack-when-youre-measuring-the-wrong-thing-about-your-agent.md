# S-2338 · The Two-Question Evaluation Stack — When You're Measuring the Wrong Thing About Your Agent

Your agent's dashboard is green. Task completion rate: 97%. Latency: within SLA. You ship the change. Two weeks later, your support queue is full of reports about agents confidently completing the wrong task — wrong customer record updated, wrong code merged, wrong form filed. The dashboard never caught it. You were measuring whether the agent finished, not whether it was right.

This is the **two-question gap**: outcome ("did it complete?") versus trajectory ("did it reason correctly?"). Most agent teams only instrument one. That's the failure mode.

## Forces

- **Agents technically complete every task — even broken ones.** Without trajectory-level observability, a corrupted intermediate state looks identical to a clean one in final metrics.
- **Outcome-only evaluation misses the mode that kills production trust.** Agents can land on the wrong answer via a plausible reasoning path and still register as "successful" if you only check the endpoint.
- **Trajectory evaluation is expensive and slow.** Full step-by-step trace capture, storage, and LLM-as-judge analysis multiplies cost by 2–10x per eval run. Teams skimp on it under pressure.
- **Reliability drops dramatically across repeated runs.** A single-run 60% success rate can fall to 25% across eight runs — a pattern that only surfaces with statistical evaluation, not pass/fail unit tests.
- **LLM-as-judge is the pragmatic choice at scale, but it has a calibration ceiling.** Spearman correlation with human judgment rarely exceeds 0.80 even in well-tuned systems.

## The Move

The core technique: **always evaluate on two distinct dimensions simultaneously, with trajectory as the gate for outcome**. Architecture your eval pipeline around these two questions:

- **Question 1 — Trajectory (process):** Did the agent call the right tools, in the right order, with the right parameters? Were intermediate states coherent? Did it detect and recover from errors?
- **Question 2 — Outcome (result):** Did the final state of the world match the intended state? Did the output satisfy the task specification?

### Implementation playbook

- **Capture full traces, not just outputs.** Instrument every tool call, every state mutation, every decision branch. Store as structured trace objects with timestamps, inputs, outputs, and tool metadata. This is your ground truth for debugging failures — without it, you cannot reason about *why* an agent failed.
- **Use LLM-as-judge for trajectory scoring.** Have a separate evaluation LLM review the trace and score reasoning quality, tool selection correctness, and recovery behavior. Calibrate against human judgment on a sample set until Spearman correlation reaches 0.80+.
- **Gate outcome scoring behind trajectory pass.** Only count an outcome as "success" if the trajectory also passes. An agent that lands on the right answer via a broken reasoning path is a production liability — next time it may land wrong.
- **Build a 3-tier rubric structure.** Top level: 7 evaluation dimensions (task completion, tool use, reasoning, safety, efficiency, consistency, error recovery). Beneath each: ~25 sub-dimensions. Beneath each: individual checklist items (~130 total). This is the recommended structure from teams at Galileo Labs who validated it across enterprise deployments.
- **Integrate evals into CI/CD — not as a separate gate.** Trigger on commit (catch regressions fast), on schedule (catch drift over time), and on event (catch pre-production issues before they reach users). A weekly manual eval run is not an eval pipeline.
- **Track cost-per-task as a first-class metric.** Agents that retry excessively, call redundant tools, or enter micro-loops generate cost curves that look like normal latency on outcome-only dashboards. Tag every tool call with a cost center and surface it in the trace view.

## Evidence

- **Engineering blog:** Shopify's Sidekick team found that expanding from 0–20 tools to 20–50 tools introduced "unclear boundaries and tool combination explosions" that no single evaluation run could catch. They solved it with **specialized evaluation agents** — one eval agent per capability cluster — paired with systematic trajectory sampling. Sidekick went from a single tool-calling agent to an architecture where eval coverage scales with capability growth.
  — [Shopify Engineering: Building Production-Ready Agentic Systems (Aug 2025)](https://shopify.engineering/building-production-ready-agentic-systems)

- **Engineering blog:** Amazon's agent teams developed a two-component framework: a **generic evaluation workflow** (standardized across all agent types) plus **use-case-specific evaluation harnesses** (calibrated per domain). They explicitly note that "traditional LLM evaluation methods treat agent systems as black boxes and evaluate only the final outcome, failing to provide sufficient insights to determine why AI agents fail or pinpoint root causes."
  — [AWS Blog: Evaluating AI Agents — Real-World Lessons from Building Agentic Systems at Amazon (Feb 2026)](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

- **Research + industry synthesis:** Galileo Labs documents that agents achieving 60% single-run success drop to 25% across eight runs — and that standard monitoring "shows green because agents technically complete every task, masking corrupted data and reasoning failures." They recommend the 3-tier rubric (7 dimensions → 25 sub-dimensions → 130 items) with LLM-as-judge at 0.80+ Spearman correlation as the operational target.
  — [Galileo AI: How to Build an Agent Evaluation Framework (Feb 2026)](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Do not let your eval LLM and your agent LLM be the same model.** Self-judgment correlation is structurally inflated — the model cannot reliably catch its own reasoning errors. Use a separate, calibrated judge model.
- **Regression sets expire.** Tasks, requirements, and agent capabilities change. A regression set frozen for six months tests the wrong things. Treat your eval dataset as a first-class artifact with a refresh cadence tied to product changes, not a calendar.
- **Binary pass/fail is insufficient for trajectory.** A trace can be "mostly right but one critical tool call was wrong" — which a pass/fail system marks as success. Use graded rubric scores with a threshold, not a boolean gate.
- **You will discover your eval quality problem late if you don't calibrate human judgment first.** Run 20–50 human-evaluated samples before trusting LLM-as-judge scores. The gap between them is your calibration constant.
- **Cost observability without trajectory is useless.** You can see that a task cost $4.70 instead of $0.40, but without a trace you cannot determine *why* — whether it was a necessary multi-step workflow or a loop of redundant tool calls.
