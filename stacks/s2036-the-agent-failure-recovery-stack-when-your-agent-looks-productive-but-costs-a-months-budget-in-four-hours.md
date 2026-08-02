# S-2036 · The Agent Failure Recovery Stack — When Your Agent Looks Productive But Costs a Month's Budget in Four Hours

Your agent isn't crashing. It's running — calling tools, generating outputs, logging every step. And it's wrong. Confidently, consistently, expensively wrong. The tool returned a 200 OK. The model generated a coherent response. Nobody noticed until the invoice arrived: $847 for a task that should have cost $0.03. The agent called the same failing tool 2,847 times in a loop, each iteration indistinguishable from productive work. The fix is not a smarter model. It's the failure recovery stack: explicit, testable guardrails enforced in code.

## Forces

- **Agents fail non-deterministically.** Traditional software crashes with a stack trace. Agents produce confident, coherent output that is partially or entirely wrong — and HTTP 200 masks semantic failure.
- **The failure surface is wide.** A single agent interaction chains intent parsing → vector DB retrieval → external API calls → LLM generation → response validation → output formatting. Each link has distinct failure modes, and cascade contamination means one bad output poisons every downstream step.
- **Happy-path testing misses everything.** In development, the agent works. Tools return clean data. The model reasons correctly. You ship it. Production users do unexpected things, tools return malformed responses, and the agent's confidence never wavers even as it goes off the rails.
- **Without hard stops, cost is unbounded.** A $0.01 request can silently explode into a $5 multi-step loop. Retry budgets, iteration caps, and token limits are not optimizations — they are the difference between a $40 and a $4,000 monthly bill.

## The Move

Implement a layered failure recovery system: catch errors at the right level, self-correct when possible, rollback when necessary, and always enforce hard cost/time boundaries so that failure is expensive but finite.

### Detect failures at the right level

Tool failures (network errors, API 500s, timeouts) are caught by try/catch. These are the easy ones. The hard failures are semantic: the tool returned data, the HTTP code was 200, but the output doesn't answer the question. Use a **Verifier Agent** — typically a smaller, faster model — to check tool outputs before they feed into the next step. If the Verifier says "this doesn't answer the query," trigger a self-correction loop as if it were a hard error.

From the AI System Design Guide (ombharatiya/ai-system-design-guide): *"For critical steps, we pipe the output to a Verifier Agent whose only job is to check: Does this tool output actually answer the query provided? If the Verifier says 'No,' it triggers a self-correction loop."*

### Budget every dimension independently

Set hard caps on four separate axes:

1. **Step budget** — Max model-to-tool-call cycles per task (e.g., 8 steps). Prevents infinite reasoning loops.
2. **Token/cost budget** — Max spend per request (e.g., $0.50). Agent stops gracefully when exhausted.
3. **Retry budget** — Separate transient-error retry budget (e.g., 2 retries per tool) from logic-loop detection. These have different causes and should be tracked separately.
4. **Wall-clock timeout** — Max elapsed time. Catches deadlocks that don't manifest as loop detection.

Each axis is independent and enforced in code, not in the prompt. The LLM cannot override its own budget.

### Detect loops before they burn out

Loop detection tracks: (a) repeated tool calls with identical arguments, (b) argument cycles (same tool called with rotating arguments), and (c) repeated behavioral patterns across steps. A step-counter catch is necessary but not sufficient — agents can loop with different arguments each time, which looks like progress. Track behavioral similarity, not just argument equality.

From a GitHub project documenting a real incident: *"An AI agent spent $847 calling the same tool 2,847 times before I added loop detection. The agent was stuck in a retry loop — same tool, same arguments, same error. It burned through the entire monthly token budget in 4 hours. The task? A simple 'find and summarize' that should have cost $0.03."*

### Self-correction: reflect, don't restart

When the Verifier flags a bad output, invoke a self-correction loop (à la Reflexion/Shinn et al.) before rolling back. The agent reviews its own trace, identifies where reasoning went off-track, and generates a corrected next action. This is cheaper than full state rollback and handles semantic errors the model can self-diagnose.

Self-correction handles 70-80% of recoverable failures. Reserve rollback for: catastrophic state corruption, repeated self-correction failures (budget exhausted), and cases where the agent has contradicted itself and cannot recover coherence from the current trace.

### Use state checkpointing for rollback recovery

For long-running agents (10+ minutes, 20+ tool calls), model the agent as an explicit state machine with checkpointed snapshots. On interruption (timeout, human handoff, service restart), resume from the last valid checkpoint — not from scratch. LangGraph's compiled graph API with persistent checkpoint storage is the canonical implementation; the checkpoint is a recovery point for interruption and restart, not a log entry.

From Easton (2026): *"A checkpoint is a recovery point for interruption, timeout, human handoff, and service restart — not just a log entry."* And: *"LangChain's 2026 State of Agent Engineering report ties more than 60% of production incidents to state management failures."*

### Graceful degradation: always land somewhere

When budgets exhaust or recovery fails, the agent must produce a useful fallback — not crash, not return empty, not loop. Common patterns: return a partial answer with a clear disclaimer, escalate to a human operator, or surface the failure with the trace so a human can retry with modifications. The user should never be left guessing whether the agent finished or got stuck.

## Evidence

- **Engineering Blog:** Microsoft ISE — "Patterns for Building a Scalable Multi-Agent System" — documents a retail customer evolving from modular monolith to coordinator-based multi-agent architecture; details semantic caching for cost reduction and two onboarding approaches (code-based vs template-based) for new agents. — [https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/)
- **Field Note:** TURION.AI — "Multi-Agent Orchestration Infrastructure: Lessons from Production" — documents that multi-agent systems are harder to operate by the order of their agent count; identifies Supervisor+Specialists as the most debuggable pattern; notes that 2023 demos looked great, 2024 production was "cursed," and 2025-2026 patterns have stabilized. — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Real Incident:** GitHub project ai-agent-loop — documents $847 runaway incident: agent called same failing tool 2,847 times in 4 hours on a $0.03 task; hard loop detection and step budgets would have caught it in step 3. — [https://github.com/hijrahassalam/ai-agent-loop](https://github.com/hijrahassalam/ai-agent-loop)
- **Research Paper:** Shinn et al. — Reflexion — self-correcting agents that review their own execution traces and repair on the next iteration; forms the basis of production self-correction loops. — [arxiv](https://arxiv.org/abs/2303.11366)
- **Operations Guide:** LLM CFO Research — "Agent Spend Guardrails: Budgets, Retries, and Loop Control" — documents the multiplication effect of retries, tool loops, escalations, and fallback chains on agent cost; recommends independent budgets per axis and escalation policies for premium model handoffs. — [https://llmcfo.com/research/agent-spend-guardrails](https://llmcfo.com/research/agent-spend-guardrails)
- **Engineering Blog:** Verel Systems — "LangGraph Development: 5 Patterns for Production-Safe Agents" — documents five production safety patterns: state checkpointing, human-in-the-loop gates, retry budgets, tool error handling, and observability hooks. — [https://verelsystems.com/en/blog/langgraph-production-patterns](https://verelsystems.com/en/blog/langgraph-production-patterns)
- **Reddit Discussion:** r/AI_Agents — "Multi agent systems are a total nightmare in production" — practitioner post about shipping 20+ production multi-agent systems; key insight: the systems that stay running are the ones with "boring" deterministic coordination, not sophisticated agent-to-agent handoff. — [https://www.reddit.com/r/AI_Agents/comments/1stzag4/](https://www.reddit.com/r/AI_Agents/comments/1stzag4/multi_agent_systems_are_a_total_nightmare_in)

## Gotchas

- **Loop detection by step count alone misses cycling with varied arguments.** Track behavioral similarity across steps, not just argument equality. Agents can loop while producing different-looking outputs each iteration.
- **Prompts don't enforce budgets — code does.** Embedding "stop after 10 steps" in the system prompt does not stop the agent. Hard caps on iteration count, token spend, and wall-clock time must be enforced in the execution loop, not delegated to the model.
- **Retry budgets and loop detection budgets are different.** A transient API error that succeeds on retry 2 is not a loop. A model calling the same tool repeatedly because it can't find a good answer is a loop. Confusing these causes either over-retrying or false-positive loop detection.
- **State rollback is not free.** Checkpointing adds latency and storage overhead. Don't checkpoint every step — checkpoint at meaningful decision points (before tool calls, after state transitions). Over-checkpointing is itself a performance problem.
- **Graceful degradation is often skipped in initial builds.** Engineers build for the happy path and treat failure handling as a v2 feature. In agentic systems, this means shipping systems where the failure mode is invisible and expensive. Build the fallback path before shipping, not after.
