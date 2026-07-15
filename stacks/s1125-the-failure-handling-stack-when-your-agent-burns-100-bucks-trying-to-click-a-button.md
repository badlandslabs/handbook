# S-1125 · The Failure Handling Stack — When Your Agent Burns $100 Clicking a Button

Your agent hit a CAPTCHA, failed to solve it, kept trying from different angles, and burned through $100 of API credits before anyone noticed. It wasn't broken — it was doing exactly what you told it to do: keep trying until the task is complete. The fix isn't better instructions. It's a recovery architecture.

## Forces

- **Agents fail in shapes traditional software doesn't.** Semantic drift (high activity, zero progress), silent token budget exhaustion, recursive reasoning loops, and mid-task state loss. Conventional watchdog patterns detect crashes but miss these higher-order failure modes.
- **The self-healing paradox.** The same retry and recovery mechanisms that keep agents running are the ones most likely to run them off a cliff. A compaction bug in Claude Code once burned ~250,000 API calls in a single day — the agent executed its recovery logic flawlessly, just without a ceiling.
- **Loop vs. slow-but-converging.** Teams treat all non-finishing agents the same. In reality, an agent making incremental progress (even 1% per step) should run; one flatlining on a progress metric while emitting tokens should fire recovery. The two require different responses.
- **Error propagation is the central bottleneck.** A single failure cascades through planning, memory, and action modules. Teams handle individual errors but miss that the error taxonomy determines the recovery strategy.

## The Move

Build a layered failure architecture — not a single retry wrapper, but concentric defenses matched to error type.

- **Hard step cap first.** Place a non-negotiable ceiling on agent steps before anything else. A step cap alone prevents runaway cost. Common values: 10–20 for short tasks, 50–100 for complex ones, with explicit escalation paths at each threshold. This is not an optimization — it's insurance.
- **Classify errors into three buckets.** Transient (network blip, 429 rate limit) → retry with backoff. Tool-parameter failures (wrong enum, missing ID) → validate inputs before execution and surface a structured error. Semantic failures (agent stuck, wrong approach) → escalate or hand off, not retry.
- **Distinguish stuck from slow.** Track a progress metric per step (e.g., result set size, line count, page state). If the metric is flat across N consecutive steps while token activity continues, fire the recovery ladder. If it's rising, let it run. Check progress at 3–5 step intervals.
- **Build a recovery ladder (cheapest first).** (1) Re-prompt with the error message and a hint. (2) Rotate to a different tool or approach. (3) Summarize and restart from a checkpoint. (4) Human-in-the-loop gate for high-stakes or ambiguous steps. Never jump to (4) when (1) might work.
- **Validate tool inputs before execution.** Tool parameter hallucination — calling the right tool with a fabricated ID or wrong enum value — is a leading failure mode. Enforce schemas at the tool boundary, not inside the agent.
- **Implement a cost circuit breaker.** Set a per-run and per-day cost ceiling. One documented case: a single buggy agent burned 250K API calls in 24 hours. Cost breakers catch this before it becomes a finance incident.
- **Checkpoint state at decision points.** Store the agent's memory, tool results, and position at natural task boundaries. On crash or escalation, the resume path is clear instead of starting from scratch.

## Evidence

- **Engineering blog — Harsh Rastogi (Modelia.ai / Asynq.ai, March 2026):** Documents five production failure modes including tool parameter hallucination, infinite loops, and contradictory reasoning. Solution: validate ALL tool inputs before execution, add explicit error type routing. — [Source](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Industry research — Zylos Research (January–March 2026):** Three primary sources covering self-healing market data ($7.92B, 2025), error taxonomy (semantic drift, token exhaustion, recursive loops), and a five-stage recovery cycle (detect → diagnose → repair → verify → adapt). Key stat: 67% of AI system failures stem from improper error handling, not algorithmic issues. — [Source 1](https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery), [Source 2](https://zylos.ai/research/2026-02-17-ai-agent-self-healing-auto-recovery/), [Source 3](https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns/)

- **Primary source — Magnus Müller, CEO at Browser Use (April 2026):** Documents the CAPTCHA loop problem empirically: "Some LLMs, when they see a captcha and they cannot solve it, would just try forever. They would try until you run out of money." Root cause: LLM models don't understand their actions failed. Loop is a symptom, not the disease — adding "try 3 times then stop" treats the symptom. — [Source](https://www.twosetai.com/insights/when-llm-agents-get-stuck-in-loops/)

- **HN discussion — "Building Effective AI Agents" (June 2025, 543 points):** Community consensus: the most successful production implementations use simple, composable patterns over complex frameworks. Anthropic's guidance: start with LLM APIs directly, implement error handling at the orchestration layer, not inside the agent. — [Source](https://news.ycombinator.com/item?id=44301809)

- **Case study — BuildMVPFast (March 2026):** Documents a production incident: agent hit a tool error on step 6, retried with slightly different parameters that matched a wildcard delete query, deleted 847 production rows. Every individual step looked fine. The problem was the sequence. Lesson: agent debugging requires trace-level observability across hundreds of spans — LLM API debugging techniques don't transfer. — [Source](https://www.buildmvpfast.com/blog/debugging-ai-agents-production-error-recovery-self-healing-2026)

- **Specialized pattern library — AgentPatterns.ai:** Defines the three "stuck shapes" (repeater, wanderer, dead-end) and the recovery ladder. Key insight: "the cheap fix that breaks a repeater fails on a wanderer" — recovery strategy must match the failure shape. — [Source](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/)

## Gotchas

- **Hard step caps prevent runaway but don't fix the root cause.** An agent that hits the cap and reports "task incomplete" still failed. You need the escalation path, not just the cap.
- **Retry loops treat every failure the same.** A 429 rate limit and a wrong-API-key error both get "retry 3x." The first is transient and safe to retry; the second retries into the same failure forever. Route by error type.
- **"Try again" re-prompting without changing the input often re-triggers the same failure.** If a tool call failed because the parameters were wrong, re-prompting with the same state just generates the same wrong parameters. The recovery needs to change the input, not just the instruction.
- **Cost circuit breakers are often the last guardrail teams add, but should be among the first.** By the time cost monitoring catches a runaway agent, damage is done. Set a ceiling before deployment.
- **Human-in-the-loop is not a substitute for good recovery logic.** Pausing an agent mid-task and asking a human to decide is expensive and slow. It should be the last rung on the ladder, not the first response to any error.
