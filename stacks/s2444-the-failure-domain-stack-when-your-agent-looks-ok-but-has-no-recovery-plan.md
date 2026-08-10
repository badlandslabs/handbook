# S-2444 · The Failure Domain Stack — When Your Agent Looks OK But Has No Recovery Plan

Your agent returned a 200. The tool call logged success. The LLM said "Done." The actual work — the thing the user asked for — did not happen. This is not a crash. Your monitoring shows green. Your on-call never fired. The agent didn't fail; it gave up. The difference between an agent that runs in demos and an agent that works in production is not the happy path. It's the 40 failure modes the happy path never touches.

## Forces

- **Agents fail without erroring.** The most expensive agent failures produce HTTP 200 — wrong results from syntactically valid API calls, loop completions that achieve nothing, approvals of work that shouldn't have passed. Traditional error handling catches exceptions; agent reliability must catch behavioral failures.
- **Failure types are domain-specific.** Tool parameter hallucination looks like a model problem but is actually a schema/intent resolution problem. Loop detection looks like a runtime problem but is actually a goal-decomposition problem. Treating all failures as the same class produces the same failed response every time.
- **Recovery costs compound with autonomy.** An agent that tries to recover from failures automatically can spend exponentially more than the task is worth. But an agent that escalates on every anomaly costs more in human time. The right recovery strategy is a function of the failure domain, not the agent's general capability.

## The move

**Map failure to domain, then pick the recovery strategy that matches.**

1. **Classify failure at the harness layer** (ARF taxonomy): is this a Channel failure (tool/API unreachable), an Execution failure (tool ran but output malformed), a Reasoning failure (wrong tool chosen, wrong parameters), or a Trajectory failure (agent is stuck in a loop)? Each maps to a different recovery action.
2. **Differentiate retryable from non-retryable.** Network timeouts and rate limits retry with exponential backoff + jitter. Hallucinated tool parameters do not — retrying just produces a different hallucination faster. Schema-mismatched outputs retry with a corrected prompt, not a replay.
3. **Implement loop detection structurally, not punitively.** Track (tool, parameters, result_hash) triples per task. Two identical triples in a row = loop. Three = escalate. Do not rely on the LLM to notice it's looping; by design, a looping agent believes it's making progress.
4. **Circuit-break on cost and failure rate.** If a sub-agent or tool-call pattern fails N times within a rolling window, open the circuit: stop calling it, return a graceful degradation, surface to human. The circuit breaker prevents cascading failure amplification (cf. S-2441).
5. **Build a fallback chain, not a fallback model.** When the primary path fails, the question is not "which model?" but "which simpler path still achieves the user's goal?" A document summarization agent falls back to extractive summarization, not a bigger model. A data extraction agent falls back to rule-based regex extraction, not a retry.
6. **Escalate facts, not guesses.** When recovery fails, the escalation message should be: what the user asked for, what the agent tried, what failed, what partial output exists. Not "I'm having trouble" — the human needs enough context to either complete the task or give the agent a new direction.

## Evidence

- **HN Ask HN (2025):** harperlabs built a 50+ test-case framework covering 7 core failure modes after auditing a customer support agent that processed a $47,000 fraudulent refund via prompt injection. Key insight: "These aren't fringe cases anymore." — [HN #47325105](https://news.ycombinator.com/item?id=47325105)
- **Engineering blog — Harsh Rastogi (Modelia.ai / Asynq.ai, Mar 2026):** Documented 5 production failure modes from real agents: tool parameter hallucination, loop detection failure, approval quality collapse, cost overruns, and contradiction accumulation. Real examples: candidate evaluation agent cost 3x budget looping on invalid tool params; image pipeline approved obviously flawed outputs optimizing for completion over quality. — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **GitHub ARF (petterjuan, 2025–2026, 1,113 commits):** Agentic Reliability Framework's core philosophy: "treat incidents as memory and reasoning problems, not alerting problems." Classifies failures into Environment Contract, Operation Skills, Action Execution, and Trajectory Regulation layers — each maps to a specific recovery harness. OSS edition advisory-only; Enterprise edition enforces execution boundaries. — [github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Research paper — Jeong & Shin (Samsung SDS / Yonsei Univ., May 2026):** "A Self-Healing Framework for Reliable LLM-Based Autonomous Agents" proposes unified taxonomy: failure detection → reliability assessment → automated recovery. — [arXiv:2605.06737](https://arxiv.org/pdf/2605.06737)

## Gotchas

- **Retrofitting recovery onto an agent is 10x harder than building it in.** If you are designing an agent for production, the failure taxonomy and recovery strategies must be specified before the agent is deployed, not after the first incident.
- **Retry logic without a cost cap is a runaway budget.** Every retry doubles the cost of failure. An agent with no cost ceiling on retry can spend more on recovery than the task is worth. Set per-task cost limits and enforce them at the harness layer, not in the agent prompt.
- **Loop detection that relies on output similarity breaks on non-deterministic models.** The same correct tool call with the same parameters produces slightly different outputs each time. Use structural triple matching (tool + params + result_schema_validity), not string similarity.
- **Human escalation without context creates a new failure mode.** A human who receives "something went wrong" will either ignore it or spend more time debugging than doing the task manually. The escalation message is a product decision, not an afterthought.
