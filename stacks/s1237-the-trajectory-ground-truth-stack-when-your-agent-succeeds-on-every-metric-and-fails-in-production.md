# S-1237 · The Trajectory-Ground-Truth Stack — When Your Agent Passes Every Metric and Still Fails in Production

You ship an agent that scores 94% on your evaluation suite. You push to production. It fails. Your evals showed green. The agent showed 200 OK. The task didn't complete. The problem isn't the agent — it's that your evaluation framework measures the wrong things at the wrong level. You evaluated the final answer. Agents live in the trajectory.

## Forces

- **The eval-to-deployment gap.** Standard LLM benchmarks test whether a model knows the right answer. Agent benchmarks must test whether the agent takes the right *sequence* of actions to reach it. A correct final answer via 47 wrong tool calls is still a broken agent — but most evals score it as a pass.
- **Outcome vs. trajectory tension.** You care about task completion (outcome), but fixing the agent requires understanding *why* it failed along the way (trajectory). Outcome-only metrics tell you nothing about the root cause; trajectory-only metrics miss the actual goal.
- **The human-calibration cost.** LLM-as-Judge is the dominant approach, but judges need calibration against human judgment to avoid drift. Calibrating judges across a diverse test suite is expensive and slow — teams either skip it or trust uncalibrated judges that mask real regressions.
- **Synthetic data compounding.** Teams generate synthetic evaluation cases at scale, then fine-tune on them. If the synthetic cases share surface patterns with each other, the agent overfits to the eval distribution and fails on novel inputs — exactly the failure mode that killed a healthcare compliance project (see Evidence).
- **Stack churn destroys continuity.** 70% of regulated enterprises rebuild their AI stack every 3 months (Cleanlab, 2025). Evaluation infrastructure built on a specific framework or model provider becomes technical debt overnight — making long-term reliability measurement nearly impossible without abstraction layers.

## The Move

Measure agent quality at three distinct levels, with different methods and different judges for each:

**1. End-to-end (task completion).** Did the agent achieve the goal? Use deterministic checks where possible (exact match, JSON schema validation, API response codes), fall back to LLM-as-Judge for open-ended outcomes. This is your binary gate — pass/fail on whether the job got done.

**2. Trajectory-level (path quality).** How did it get there? Instrument the agent to emit structured traces: each tool call, its arguments, the response, and the reasoning step. Score for:
- **Step efficiency** — fewer tool calls to reach the goal is better; flag when an agent loops or re-attempts the same operation
- **Argument correctness** — did it call the right tool with the right parameters? (Confident AI calls this "tool-call accuracy")
- **Plan adherence** — does the observed trajectory match what the task required? Did it skip required steps?
- **Error recovery** — when a tool fails, does the agent try alternatives or spiral?

**3. Component-level (per-span diagnosis).** When a trajectory fails, which specific step broke? This requires trace-level instrumentation — span IDs attached to each tool call and LLM invocation. A failed task with trace data tells you *which* tool call or reasoning step caused it. A failed task without trace data is a mystery.

**Calibrate your judge before you trust it.** Target 0.80+ Spearman correlation with human judgment on a representative sample before running LLM-as-Judge at scale. Use the same judge consistently across runs — model updates shift judge behavior and can mask regressions (Anthropic, 2026).

**Separate trajectory metrics from outcome metrics.** A task that completed with 12 unnecessary tool calls is worse than one that completed with 4 — even if both "succeeded." Efficiency, cost, and latency are first-class quality signals, not afterthoughts.

**Integrate evals into CI/CD, not just pre-deployment.** Trigger evals on every significant code change (commit hooks), on schedule (nightly regression suites), and on events (model version updates, prompt changes). Evaluating only before launch means you're flying blind in production.

## Evidence

- **Anthropic engineering blog (Jan 2026):** "Good evaluations help teams ship AI agents more confidently. Without them, teams get stuck in reactive loops — catching issues only in production, where fixing one failure creates others." They define the core taxonomy: Task (test case with inputs + success criteria), Trial (each attempt), Dataset (collection of tasks), Run (trial against dataset), Score (aggregate results). Stresses that eval value compounds over the agent lifecycle — the first eval is the hardest; subsequent ones get cheaper as you build test infrastructure. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

- **Cleanlab enterprise survey (Aug 2025, n=1,837):** Only 95 of 1,837 respondents had AI agents live in production. Of those, fewer than 1 in 3 were satisfied with observability and guardrail solutions. The top challenge cited wasn't model capability — it was accurate tool calling. A healthcare compliance case nearly derailed because the team had unit tests, integration tests, and demos, but no evaluation harness for hallucination rate, context faithfulness, or tool-selection accuracy. They built a 12-metric framework to get compliance sign-off and ship. — https://cleanlab.ai/ai-agents-in-production-2025

- **Confident AI evaluation guide (2026):** Defines 12 core metrics across three evaluation levels: end-to-end (task completion, answer relevancy, faithfulness, safety), trajectory-level (step efficiency, argument correctness, tool correctness, plan adherence, plan quality, reasoning quality), and component-level (per-span inspection). Key insight: "An agent can look busy, reason intelligently, call the right-looking tools, and still fail to complete the task." — https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide

- **r/LocalLLaMA discussion (Nov 2024):** Practitioners debating "The Eval problem for AI Agents" identified that the hardest bottleneck isn't building the agent — it's knowing when it's actually better after a change. One engineer: "We have 200 test cases. Our old agent gets 60% pass rate. Our new one gets 62%. Is that noise? We don't know." — https://www.reddit.com/r/LocalLLaMA/comments/1qltqfx/the_eval_problem_for_ai_agents

- **Galileo AI framework (Jul 2026):** Targets 0.80+ Spearman correlation between LLM-as-Judge scores and human judgment as a quality threshold. Recommends 3-tier rubrics: 7 dimensions → 25 sub-dimensions → 130 evaluation items. Notes that over 40% of agentic AI projects will be canceled by end of 2027 (Gartner) — and inadequate evaluation is cited as a primary cause. — https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks

## Gotchas

- **Your eval suite has a distribution.** If you generate synthetic test cases from a single prompt or source, your agent can overfit to the eval distribution. Mix real production failures, human-written edge cases, and synthetic data — and rotate them regularly.
- **Model updates break judge consistency.** An LLM-as-Judge evaluated with Claude 3.5 Sonnet in January may score differently with Claude 4 in March — not because the agent changed, but because the judge changed. Pin your judge model version or re-calibrate on every significant update.
- **Success rate alone is a vanity metric.** A 90% success rate with a 30-step median trajectory is worse than an 88% success rate with 5 steps. Always pair outcome metrics with efficiency metrics.
- **You can't debug what you can't see.** Without structured trace instrumentation, a failed task is opaque. The investment in trace spans pays back on every debugging session.
- **Human review is not optional for high-stakes domains.** In regulated industries (healthcare, finance, legal), LLM-as-Judge is a screening layer, not a replacement for human review. Use it to filter obvious failures before human review, not to eliminate humans entirely.
