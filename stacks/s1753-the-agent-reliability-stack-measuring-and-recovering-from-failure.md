# S-1753 · The Agent Reliability Stack — Measuring What Breaks and Building Recovery

Your agent passes all unit tests, ships to production, and immediately runs $4,000 in API calls looping on a missing field. The evaluation stack isn't about making agents smarter — it's about knowing whether they actually work, and surviving when they don't.

## Forces

- Agents are non-deterministic: the same input produces different outputs, so traditional CI assertions fail — you can't assert `response == "exact string"`
- Trajectory and outcome are different things: an agent can reach a wrong answer confidently via a perfectly reasonable reasoning path
- Agents fail in shapes single-LLM calls don't: recursive loops, semantic failures that return HTTP 200, hallucinated tool names, and cost spirals
- First-attempt task completion in production is below 25% across real-world agents (APEX-Agents benchmark) — failure is the default, not the edge case
- Prompt changes, model swaps, and tool version bumps all break agents silently: existing test suites don't catch it

## The Move

Build a layered reliability system: measure with evals, gate with CI, and recover with structured failure handling.

### Eval Architecture

- Separate **trajectory metrics** (did the reasoning path look right?) from **outcome metrics** (did the task actually complete?). Optimize trajectory first — it's faster and cheaper to evaluate.
- Run **three eval categories** in parallel: semantic distance (is the response close to expected?), groundedness (did it use the right context?), and tool usage (did it call the right tools in the right order?). Monte Carlo's Troubleshooting Agent — 100+ sub-agents diagnosing data incidents — accelerated root cause analysis by 80%+ using this three-layer evaluation suite.
- Target >0.80 Spearman correlation between LLM-as-judge and human judgment. Below that threshold, the judge is unreliable and you need human-in-the-loop sampling.
- Use **trace-based evaluation** (DeepEval, AgentEval): instrument the agent once, attach metrics per span — LLM calls, tool executions, retriever hits. Every run emits a trace you can replay, score, and diff.
- Evaluate on domain-matched benchmarks: SWE-bench Verified for code agents, GAIA for general assistants, WebArena for web agents, MMMU for multimodal. Don't use MMLU to evaluate a customer support agent.

### CI Integration

- Gate every PR with automated agent eval suites. Prompt regression is real: a one-word change in a system prompt can break 12% of test cases silently.
- Run **commit-triggered evals** (fast, narrow), **scheduled evals** (full regression on a timer), and **event-driven evals** (pre-deploy gate). Each has a different scope and cost.
- Track a **Self-Healing Score** (0–100): inject failures and measure Recovery Rate (did it recover without human help?), Recovery Latency (time from failure to resumed progress), and Task Completion Rate post-failure.
- Block merges on regression — if the eval score drops 5% or more, the PR fails. Enforce this with branch protection rules, not convention.

### Failure Recovery Patterns

- **Hard step caps**: set `MAX_STEPS = 12` for general agents, `MAX_STEPS = 6` for agents with expensive tool calls. When exceeded, stop, document the state, and escalate. This is the single most important guardrail — it prevents runaway loops and cost spirals.
- **Cost circuit breakers**: track cumulative spend per task. If an agent exceeds a budget threshold, stop and alert. Agents in production have run up $10K+ bills from recursive loops.
- **State checkpointing**: before each major tool call, save a known-good snapshot. On failure, quarantine the bad state and roll back to the snapshot. The `NassimRahimi/agent-failure-recovery` demo shows this pattern: scanner → quarantine → rollback → validate restored state.
- **Tool-level retries with exponential backoff** for transient errors (HTTP 429, 503, timeouts). Distinct from **whole-agent retries** which re-run the full reasoning loop — use sparingly, they're expensive.
- **Graceful degradation**: if the primary tool fails, have a fallback path. If the fallback also fails, return a structured error with partial results rather than crashing silently.
- **LLM-as-judge for failure detection**: for semantic failures (confident wrong answers returning HTTP 200), you need a secondary model to flag the output as problematic. HTTP status codes won't help you here.

## Evidence

- **Anthropic engineering blog (Nov 2025):** Claude Code uses a two-agent harness — an initializer agent writes task plans to a shared artifact, and a coding agent reads the plan, executes, and updates progress. This bridges context window gaps across sessions for long-running tasks. — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- **Monte Carlo data blog (Nov 2025):** Their Troubleshooting Agent (hundreds of sub-agents) accelerated root cause analysis by 80%+ using three-category eval: semantic distance, groundedness, tool usage. Key lesson: soft failures (wrong tool, low confidence) are more actionable than hard crashes. — https://montecarlo.ai/blog-ai-agent-evaluation
- **CyberQuickly (Apr 2026):** Documented nine production failure classes across 2025–2026 incidents: API rate limiting, semantic failures, recursive loops, auth drift, stale context, hallucinated tools, cost spirals, context overflow, and output quality degradation. First-attempt task completion is <25% across real-world agents. — https://www.cyberquickly.com/2026/04/07/ai-agents-production-failure/
- **GitHub / agent-failure-recovery:** Open-source demo of state checkpointing, rollback, and failure attribution for agent workflows. Shows how to quarantine bad state and recover to known-good snapshots. — https://github.com/NassimRahimi/agent-failure-recovery
- **TDS "12-Metric Framework" (100+ deployments):** Practical thresholds for production: Tool Selection Accuracy >92%, Tool Execution Success >98%, Hallucination Rate <2%, Answer Faithfulness >95%. — https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/
- **Zalor (HN Show HN, ~Mar 2026):** Automated agent testing platform specifically targeting prompt-change regressions. Agents break when you tweak system prompts — Zalor surfaces which test cases regress. — https://news.ycombinator.com/item?id=47270208
- **Agent CI (agent-ci.com):** Production CI platform for agents: per-PR automated evaluation gates, branch protection rules for eval regression, and live agent execution environments per branch. Addresses the gap that "code compiles + unit tests pass" is insufficient for agents.

## Gotchas

- **Evaluating eval quality is often skipped.** Your LLM-as-judge has to be validated itself — target >0.80 Spearman correlation with human judgment. Without this, you're measuring a proxy that's also wrong.
- **Step caps sound simple but are easy to misconfigure.** Setting `MAX_STEPS = 3` for a complex agent is a different failure mode (premature abortion) than no cap at all (infinite loop). Calibrate by running percentile-95 task traces.
- **Rollback without validation is dangerous.** Restoring a checkpoint doesn't mean the restored state is actually safe — you need a validation pass (even a cheap LLM check) before continuing execution after rollback.
- **Cost tracking lags behind failure detection.** By the time you detect a cost spiral, the damage is done. Budget limits need to be enforced per-task, not per-session.
- **Benchmarks reward capability, not reliability.** GAIA and SWE-bench tell you if an agent *can* do a task. They say nothing about whether it does the task *reliably* across your specific toolchain. Build your own eval suite, don't just run leaderboards.
