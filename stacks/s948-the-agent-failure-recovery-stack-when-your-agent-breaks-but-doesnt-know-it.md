# S-948 · The Agent Failure Recovery Stack — When Your Agent Breaks But Doesn't Know It

Your agent is looping. It called the same tool 23 times. Nothing failed — no crash, no error code, no exception thrown. It kept reasoning, kept acting, kept "recovering." The API invoice told you it was done: $847 for a task that should have cost $0.12. This is the failure recovery problem: agents fail silently because their loop condition is delegated to the LLM, which optimistically believes one more step will help.

## Forces

- Agents use self-correcting loops (ReAct-style: reason → act → observe → reason again) that are their greatest strength and their most dangerous failure mode
- An unbounded reasoning loop is architecturally identical to a bounded one until it isn't — there's no crash to alert you
- The recoverable/non-recoverable divide is not obvious at runtime; a retriable API error looks the same as a confidence collapse until you know the context
- The cost curve is non-linear: 10 tool-call steps at 85% reliability each finish only ~20% of the time (0.85^10 ≈ 0.197) — the remaining 80% either loop or fail silently
- Human escalation must preserve full conversation context or the human starts blind
- External verification signals (test execution, tool validation) consistently outperform verbal self-reflection alone

## The Move

Layer five independent safeguards that cover different failure modes at different levels:

- **Hard step cap at the loop level.** If the agent doesn't finish in N steps (commonly 10–15), stop, snapshot state, and escalate. This is the single most important guardrail and the one most teams skip. Two documented incidents: a Claude Code recursion loop burned $16,000–$50,000 in five hours (July 2025); a four-agent LangChain pipeline loop ran eleven days for $47,000 — both worked correctly in testing.
- **Tool-level retries with exponential backoff.** Distinguish retriable errors (network timeout, 5xx, rate limit) from fatal ones (auth failure, 4xx schema mismatch) before deciding to retry. Never let the LLM decide whether to retry a failed tool call — hard-code the logic.
- **Stateful rollback via checkpointing.** LangGraph's `MemorySaver` or `PostgresCheckpointSaver` snapshots state at every node boundary. A single bad tool call can be rewound in 3 lines without losing the user's context or restarting a 12-step run. Postgres for durability and audit trails; Redis for raw speed.
- **Semantic loop detection via state hashing.** Hash the agent's recent state (tool calls + observations) to detect when the same state repeats with different actions. A "soft loop" — different tool calls but no new information — is harder to catch than a hard loop (identical actions) but equally wasteful. Agent Patterns documents costs jumping from ~$0.08 to ~$12 on the same task type.
- **Cost circuit breaker per step.** Enforce a per-task budget evaluated before each step executes, not after. Real-time token and cost tracking that can halt execution mid-run. One documented case: an agent summarizing a document entered a refinement loop, continuously polishing until it hit the cost limit.
- **Escalation with full context preservation.** When the agent exhausts recovery options, transfer to a human with the complete reasoning trace — not just the current state. The dividing line: recoverable (API failures, retriable timeouts) vs. non-recoverable (data loss, irreversible writes, confidence collapse below threshold). Production data shows optimal escalation rates of 10–15%.

## Evidence

- **GitHub design guide:** AI agent failure taxonomy — hallucinated tools, tool errors, state corruption, hard loops, soft loops, semantic loops, retry storms. Recommends LangGraph and Microsoft Agent Framework for native checkpoint/resume primitives. — [ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Real incident documentation:** Claude Code recursion loop burned $16,000–$50,000 in 5 hours (July 2025); four-agent LangChain loop ran 11 days for $47,000. Both worked in testing — agents did exactly what they were told, indefinitely. — [freeCodeCamp / dannwaneri/production-safe-agent-loop](https://www.freecodecamp.org/news/how-to-build-a-production-safe-agent-loop-from-exit-conditions-to-audit-trails)
- **Cost curve analysis:** Agents using ReAct-style loops terminate based on LLM judgment, not explicit conditions. Documented case of an agent stuck in document refinement loop. Per-step budget enforcement prevents the non-linear cost spiral. — [jcardena.com](https://blog.jcardena.com/en/agentic-ai-in-production-the-failure-modes-and-cost-curves/)
- **Production handoff research:** 70% of organizations use AI agents in operations; two-thirds require human verification of agent decisions. Optimal confidence thresholds: 80–95% depending on risk. Architecture shifting from human-in-the-loop to human-on-the-loop. — [Zylos Research](https://zylos.ai/research/2026-01-30-ai-agent-human-handoff/)
- **LangGraph checkpointing:** Thread state vs. immutable checkpoints. 3-line rollback pattern rescues multi-step runs from a single bad tool call. Postgres for durability, Redis for speed. — [AI Dev Day India](https://aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html)
- **Reddit r/LocalLLaMA production report:** Multi-step tool chains (scrape → extract → transform → save) cost 6–8x expected tokens due to LLM "thinking" between every step. Simple `max_iterations` insufficient — teams need semantic progress detection. — [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1qh8xj6/those_of_you_running_agents_in_productionhow_do/)
- **Agent Patterns catalog:** Hard loops (same actions), soft loops (different actions, same state), semantic loops (same reasoning pattern recycled). Normal cost ~$0.08; looping cost ~$12 for identical task. — [agentpatterns.tech](https://www.agentpatterns.tech/en/failures/infinite-loop)

## Gotchas

- **Never let the LLM decide when to stop.** The ReAct loop's termination condition is a fuzzy judgment call made by the LLM, which optimistically believes one more step will help. Hard-code the exit condition.
- **A soft loop looks nothing like a hard loop.** The agent takes different actions each step, gets no new information, and eventually times out. State hashing catches this; step-count caps do not.
- **Checkpointing without a resume plan is half-measured.** Saving state is useless if you don't have a defined recovery path (retry from checkpoint, escalate to human, or mark task as failed with full trace).
- **Retries without backoff create retry storms.** When an external API is down, N concurrent agents each retry 3x simultaneously. Add jitter and a shared circuit-breaker that signals "this service is unhealthy, stop all retries for 30 seconds."
