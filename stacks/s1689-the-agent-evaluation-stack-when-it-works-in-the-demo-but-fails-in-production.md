# S-1689 · The Agent Evaluation Stack — When It Works in the Demo but Fails in Production

Your agent nails the demo. Three clean tool calls, perfect reasoning trace, user impressed. Then production hits: a different data format breaks the classifier, the agent takes 47 steps instead of 3 and bills $12 in tokens, a silent logic error produces wrong output with no exception raised, and nobody notices until a user files a bug three days later. The question isn't whether agents are hard to evaluate — it's how to measure what actually matters before you ship.

## Forces

- **Agent reliability compounds counterintuitively.** An agent with 75% per-trial reliability has only a 42% chance of passing all three trials under pass³. Teams that test 3 times and call it done are not measuring reliability — they're measuring luck.
- **Most agent failures are silent.** Unlike a crashed microservice that logs a stack trace, agents quietly return wrong answers, skip tool calls, or stall mid-task with no exception raised. You discover the failure when a user complains.
- **Trajectory variance makes reproducibility hard.** The same task can produce different tools, different orderings, and different outcomes. Evaluating only the final output misses the path — and the path is where reliability actually lives.
- **Eval infrastructure is an afterthought.** Only 52.4% of teams run offline evaluations on test sets; just 37.3% run online evals (LangChain 2026 State of AI Agents report). Most teams ship agents with no measurement system at all.

## The Move

Build a layered eval stack that measures task success, trajectory quality, and component behavior — and runs automatically on every change.

**1. Define task success as a binary signal, not a score.**
The final answer is either right or wrong. Use deterministic checks wherever possible (exact match, schema validation, file existence) — not LLM-as-judge — for objective ground truth. Reserve LLM-as-judge for things that genuinely require judgment: tone, relevance, whether a summary captures key points.

**2. Measure trajectory quality independently from outcome.**
Track tool-call accuracy (right tool, right arguments), step efficiency (did it take 3 steps or 47?), planning quality (did it form a sensible plan before acting?), and cost per task. An agent can complete a task successfully but waste $8 doing it — that's a failure worth surfacing.

**3. Run sufficient trials — more than you think you need.**
Non-determinism means a single run tells you almost nothing. Run at minimum 10–30 trials per task before drawing conclusions. Track pass@N rates: if pass@10 is 80%, that means 1 in 5 tasks still fail after 10 attempts. The reliability bar depends on your use case — internal tooling tolerates 80%; customer-facing automation likely needs 95%+.

**4. Instrument traces, not just outputs.**
Every agent run should produce a structured trace: the full sequence of tool calls, arguments, responses, and intermediate reasoning. Traces surface new failure modes you didn't anticipate, enable human review of ambiguous cases, and let you answer "which component broke?" when a task fails.

**5. Put evals in CI/CD, not in a spreadsheet.**
Every prompt change, tool modification, or model swap should trigger the eval suite automatically. A green CI build for your agent means the eval suite passed — same as any other software. Integrate cost-per-task and step-count thresholds as regression gates: if a change doubles median cost, block the deploy.

**6. Implement fail-safes that cap damage.**
Self-healing loops need hard limits. A missing retry cap on a failing step can burn 250K API calls in a day. Set max retries, max steps per task, max cost per run, and circuit breakers that open when error rates spike. These aren't failure handling — they're blast radius containment.

**7. Monitor in production, not just pre-deploy.**
Online evals (sampling live runs, scoring with LLM judge, tracking task completion rate) catch failures that test sets miss: data distribution shift, API behavior changes, edge cases only real users trigger. A 5% drop in task completion rate in production is a deploygate event.

## Evidence

- **Engineering blog:** Tian Pan (software engineer, puncsky) on self-healing agents — categorizes failures into transient (retry-able), logic errors (silent, no exception raised), and regression errors (requires statistical monitoring). Documents that most agent failures "don't announce themselves — no crash, no alert, no stack trace." — https://tianpan.co/blog/2025-09-22-self-healing-agents-in-production

- **Company guide:** Mastra.ai "AI Agent Evaluation" (June 2026) — cites LangChain 2026 State of AI Agents report: only 52.4% of teams run offline evals, 37.3% run online evals. Provides the 75% reliability → 42% pass³ math. Breaks eval into component-level, trajectory-level, and end-to-end layers. — https://mastra.ai/articles/ai-agent-evaluation

- **Company guide:** Confident AI / DeepEval (June 2026) — organizes agent eval into four metric groups: tool calling, planning, task completion, and reasoning. Advocates deterministic checks for objective metrics, LLM-as-judge for subjective ones, and structured traces as the eval substrate. DeepEval has 17K+ GitHub stars, 8M+ PyPI monthly downloads as of July 2026. — https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide

- **GitHub repo:** tkarim45/agent-eval-harness — open-source harness for tool-using LLM agents (Claude-focused) measuring task success, tool-call accuracy, step efficiency, and cost. Includes trajectory viewer. — https://github.com/tkarim45/agent-eval-harness

- **Research benchmark:** TheAgentCompany (OSDI 2024, updated 2025) — benchmarks LLM agents on consequential real-world enterprise tasks. Finding: the most competitive agent completes 30% of tasks autonomously, revealing how far production-grade autonomy still has to go. — https://arxiv.org/abs/2412.14161

- **Engineering guide:** AgentMarketCap "Self-Healing Agent Pipelines 2026" — documents the "recovery ceiling" problem: a missing retry cap let 1,279 Claude Code sessions run 50+ consecutive compaction failures each, burning ~250K API calls. Warns that self-healing mechanisms without hard limits are the most likely source of runaway failures. — https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery

- **Engineering guide:** Brandon Lincoln Hendricks — "Circuit Breaker Patterns for AI Agent Reliability: A Production Implementation Guide" (March 2026) — argues circuit breakers for AI agents must protect against reasoning failures, not just network failures, since LLM API calls can return valid HTTP 200s with malformed or dangerous content. — https://brandonlincolnhendricks.com/research/circuit-breaker-patterns-ai-agent-reliability

## Gotchas

- **LLM-as-judge is useful but not authoritative.** Judges have their own biases and can be gamed. Treat LLM-judged scores as directional signals, not ground truth. When stakes are high, add human review sampling.
- **Eval datasets drift.** If you eval against a fixed test set that doesn't change, you eventually measure memorization rather than capability. Rotate tasks, add new cases from production failures, and track whether eval pass rate improves as you iterate — if it plateaus, your eval set may be saturated.
- **Cost and reliability are a joint metric.** An agent that's 99% reliable but costs $5 per task is a different product than one that's 85% reliable at $0.10 per task. Track both per-task cost and reliability together; optimize for the product tradeoff, not either in isolation.
- **Trace storage grows fast.** Full traces with tool responses can be 10–100KB per step. A 10-step agent with 30 trials per task generates gigabytes per eval run. Budget for trace storage and retention policies — you don't need to keep every historical trace forever, but you need enough for regression comparison.
