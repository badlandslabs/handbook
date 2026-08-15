# S-2690 · The Agent Evaluation Stack

When you need proof that your agent actually works — not just once in a demo, but reliably across the full distribution of real inputs, with evidence you can show someone else.

## Forces

- **Model eval and agent eval answer different questions.** MMLU and HumanEval tell you if the engine is powerful. They say nothing about whether the system (engine + tools + loop + memory) can complete a multi-step workflow in a dynamic environment. Teams often confuse the two and spend months optimizing benchmark scores that don't correlate with production quality.
- **The final answer hides how you got there.** An agent can reach the right answer by an unsafe path, reach a wrong answer that reads perfectly, or look impressive once and be unreliable on the second run. Score the output alone and you miss most failure modes.
- **Evals feel like overhead until they catch a silent regression.** Without an eval suite, a prompt tweak that "passes the vibe check" can silently degrade performance on a subset of cases. Evals are the only mechanism that makes improvement cumulative rather than cyclical.
- **LLM-as-judge scales but carries bias.** Because agent tasks rarely have a single correct string to match, automated scoring depends on a model evaluating another model. Judge models have their own failure modes — position bias, verbosity bias, self-preference — and must be calibrated against human-labeled examples before trusted on high-stakes decisions.

## The move

**Build a two-layer evaluation system: offline golden suites for pre-deploy gates, and online sampling for production monitoring. Score on four dimensions, not one.**

### Offline layer
- Curate a **golden dataset** of known-good cases plus edge cases. Every change to prompt, tools, or model runs the full suite — this is the regression gate before shipping.
- Cover the four evaluation dimensions: **Task Success** (did the agent accomplish the objective?), **Tool Use Quality** (right tool, right arguments, correct error recovery?), **Trajectory Quality** (reasonable step count, no loops, correct ordering?), and **Cost/Latency** (how many steps and tokens per task?).
- Use **LLM-as-judge** for trajectory scoring: prompt a capable model with a rubric and examples, then calibrate the judge against human-labeled samples. Accept that judge bias exists and compensate by keeping humans in the loop for high-stakes decisions.
- Frameworks: LangSmith `agentevals`, DeepEval, Arize Phoenix for offline + live monitoring, RAGAS for RAG-centric agents.

### Online layer
- **Sample live traffic** and score it automatically. No eval suite survives contact with production data — real users surface cases the team never imagined.
- Track trajectory length, tool error rates, and retry rates as leading indicators. A spike in tool errors often precedes a task-success drop.
- **Close the loop:** offline evals suggest improvements; online sampling confirms whether those improvements hold in the wild. The two are a continuous cycle, not a one-time gate.

### Failure-mode policies (not just tool implementations)
- **Mode 1 — Tool failure:** Surface errors as tool results, not exceptions. Let the agent see the failure and decide whether to retry, try a different tool, or escalate.
- **Mode 2 — Model failure:** Catch malformed output (wrong tool name, bad arguments) with validation at the tool-calling boundary. Retry with a hint, or route to human.
- **Mode 3 — Loop failure:** Cap max iterations (typically 10–20 for most workflows). Track step-count distribution — a shift toward longer trajectories is a leading signal of convergence failure.

## Evidence

- **Anthropic Engineering (Dec 2024):** Agents and workflows are distinct patterns — workflows use predefined code paths, agents use dynamic model-directed tool usage. Most successful implementations use simple composable patterns rather than complex frameworks. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **HN discussion on production agents (July 2025, 128 points):** "If you don't have evals, you really don't know if you're moving the needle at all. There were multiple situations where a tweak to a prompt passed an initial vibe check, but when run against the full eval suite, clearly performed worse." Evals are vital for improving performance; teams without robust eval practices are not to be trusted. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

- **NVIDIA Technical Blog (May 2026):** Model benchmarks (MMLU, GSM8K, HumanEval) test foundation model capabilities in isolation. Agent benchmarks (GAIA, SWE-bench, WebArena) test end-to-end behavior in dynamic environments. Agent evaluation measures trajectories, tool calls, and outcomes — not just model scores. — [developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)

- **MachineLearningMastery.com (Feb 2026):** Traditional LLM metrics (BLEU scores, perplexity) fail to assess what matters for agents: task completion, tool usage, recovery from failures. Four pillars: Task Success, Tool Usage Quality, Trajectory Quality, and Cost/Latency. — [machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance)

- **Langfuse Engineering (2026):** Offline golden datasets form the pre-deploy regression gate; online traffic sampling catches distribution shifts. Both layers feed back into eval suite maintenance. Trajectory metrics — step count, unnecessary tool calls, loop/retries — are leading indicators of failure before task-success rates drop. — [langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)

- **KindaTechnical (2025):** Three distinct failure modes in agentic loops: tool failure (survive by surfacing errors as results), model failure (survive by validating at tool-calling boundaries), and loop failure (survive by capping max iterations and routing persistent failures to human). Each mode needs its own recovery policy. — [kindatechnical.com/claude-ai/error-recovery-and-retries-in-agentic-workflows.html](https://kindatechnical.com/claude-ai/error-recovery-and-retries-in-agentic-workflows.html)

## Gotchas

- **No eval is the most common mistake.** Shipping an agent without an eval suite means every "improvement" is a guess. Start with a small golden dataset of 20–50 cases — enough to catch regressions, not so many that maintenance becomes a burden.
- **Scoring only the final answer hides the path.** A 15-step trajectory that completes a task is not equivalent to a 3-step trajectory that completes it. The longer path may be more fragile, more expensive, and more likely to fail on edge cases.
- **Judge models have position and verbosity bias.** A model asked to compare two responses will favor the one that appears longer and more detailed, regardless of actual quality. Always run correlation checks against human-labeled samples before trusting judge scores on important decisions.
- **Trajectory length shifts silently in production.** If you only measure task-success rate, you'll miss that the agent is compensating for degraded tool reliability by taking more steps. Track step-count distribution as a leading indicator.
