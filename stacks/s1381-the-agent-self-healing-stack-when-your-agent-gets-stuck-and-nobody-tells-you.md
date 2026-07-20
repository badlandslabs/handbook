# S-1381 · The Agent Self-Healing Stack — When Your Agent Gets Stuck and Nobody Tells You

Your agent has been looping for 41 minutes. It hasn't output anything to the user, but it's been calling your search API repeatedly, burning tokens, and making no progress. No error was thrown. No exception was raised. No alert fired. This is the failure mode that standard error handling doesn't cover — the agent that isn't broken, but isn't working either.

## Forces

- **Agents fail silently and plausibly.** Unlike a web service that crashes and logs a 500, an agent that loops or degrades keeps responding. It sounds confident. It uses your APIs. Standard APM (error rates, latency histograms) was built for crashes — it misses behavioral failures where the agent keeps going and keeps looking fine.
- **Error propagation cascades.** A single tool failure corrupts the planning module, which feeds bad context to the action module, which makes the wrong call. By the time the symptom appears, the cause is buried three steps deep.
- **One retry blanket doesn't cover it.** A retry that works for a transient network blip will burn your rate limit budget retrying a bad JSON schema. The recovery action needs to match the failure type — but you can't match it if you haven't classified it.
- **Recovery and detection are separate disciplines.** Firing recovery at the wrong moment is worse than firing nothing: it interrupts legitimate slow work, escalates cheaply-fixable failures to human review, or nudges a wanderer into a deeper dead end.

## The Move

Build a layered self-healing system: detect → classify → select → act. Each layer narrows the response. Only escalate when the cheaper options are exhausted.

**1. Layer failure classification at every call site, not at the top.**

```
Tool failure       → retry with exponential backoff + jitter
Validation failure → self-correct (return validator output to model)
Timeout            → circuit breaker, then fallback
Rate limit         → backoff, then alternate provider
Resource exhaustion → checkpoint, pause, human handoff
```

Every LLM or tool call needs its own retry contract specifying exception classes, max attempts, and backoff per call site. Do not wrap the whole agent in a blanket try/except. — [BestAIWeb: AI Agent Failures: Retries, Fallbacks & Recovery](https://www.bestaiweb.ai/topics/agent-error-handling-and-recovery/)

**2. Implement a recovery ladder with bounded cost per rung.**

From AgentPatterns.ai's stuck-loop recovery framework:

| Rung | Action | Works for | Fails for |
|------|--------|-----------|-----------|
| 1 | Prompt nudge ("try a different approach") | Repeaters | Wanderers |
| 2 | Subtle context injection | Repeaters | Wanderers |
| 3 | Full state rewrite | Wanderers | Repeaters |
| 4 | Human handoff | Everything | — |

The key discriminator: check whether the progress metric is flat (stuck) or rising slowly (converging). Recovery fires only when progress is flat. — [AgentPatterns.ai: Stuck-Loop Recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)

**3. Track node repetition patterns across agent boundaries.**

LangSmith and similar tracing tools log individual calls but miss cross-agent repetition patterns. A research_agent → analysis_agent loop fires twice before showing as a pattern. Implement a runtime wrapper that:
- Tracks node repetition count
- Detects A→B→A→B cycles
- Checks for identical tool call parameters across turns
- Computes a "novelty score" per turn (has this tool+params been seen in the last N turns?)

Fire a stuck-loop alert when novelty score stays at zero for 3+ consecutive turns. — [Reddit r/LangChain: Detecting infinite loops in LangGraph multi-agent systems](https://www.reddit.com/r/LangChain/comments/1r2mdz1/detecting_infinite_loops_in_langgraph_multiagent/)

**4. Use durable execution for long-running workflows.**

Checkpoint agent state at node boundaries — not just conversation history, but the full graph state (variables, pending tool results, routing decision). LangGraph's MemorySaver or Postgres checkpointer creates immutable checkpoint logs per thread. On failure, rewind to the last clean checkpoint and replay from there, not from scratch. — [AI Dev Day: Roll Back a Failing Agent in 3 Lines: LangGraph](https://aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html)

**5. Treat self-correction as a retry with a better error message.**

A validator tells the model exactly what was wrong and constrains the fix, versus a plain retry that repeats the same call and hits the same wall. The model receives structured feedback (JSON schema error, validation message) instead of a generic failure, reducing token burn and improving fix quality. — [BestAIWeb](https://www.bestaiweb.ai/topics/agent-error-handling-and-recovery/)

## Evidence

- **HN Show HN (Jan 2026):** TensorPool Agent — autonomous recovery for distributed GPU training jobs. Monitors for Xid errors, S3 timeouts, NCCL hangs; diagnoses from last checkpoint and restarts without human intervention. 100,000+ multinode training GPU hours logged. Commenters flagged the "silent stall" risk as the primary concern — jobs that don't crash but stop making progress (NCCL ranks waiting indefinitely, gradient norm explosions) are harder to detect than outright failures. — [HN: Show HN: Autonomous recovery for distributed training jobs](https://news.ycombinator.com/item?id=46812909)

- **Engineering post (2026):** Agentbrisk documented a mid-size e-commerce company's refund agent that issued ~$1.2M in unauthorized refunds across 340 transactions over 3 weeks. Root cause: natural language refund eligibility logic in the prompt was interpreted broadly by the LLM. Safeguard that failed: policy enforcement was in a prompt instruction, not a hard constraint. Fix: circuit breaker that escalates any refund over $200 to human review regardless of what the model recommends. — [Agentbrisk: AI Agent Failures: Real Incidents and What Actually Went Wrong](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents)

- **OSS framework:** Agentic Reliability Framework (ARF) — implements a 5-stage self-healing pipeline: Detection → Recall → Decision → HealingIntent → Execution. Combines AI reasoning over operational history with deterministic enterprise execution boundaries. Open source (Apache 2.0), v3.3.9. — [GitHub: petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)

- **OSS tool:** agent-triage — analyzes production agent traces, extracts behavioral rules from system prompts, replays conversations step-by-step with LLM-as-judge, and aggregates root causes across failures. Designed for post-incident diagnosis. — [GitHub: converra/agent-triage](https://github.com/converra/agent-triage)

## Gotchas

- **Retries without idempotency keys duplicate side effects.** A retried "send email" step without an idempotency key sends the email twice. Every retryable step must carry a unique operation ID.
- **Checkpointing conversation history is not enough.** The graph state (pending results, routing variables) must also be checkpointed. Replaying just the conversation can produce a different reasoning path, leading to inconsistent results on resumption.
- **Progress metrics can be gamed.** If you use a naive metric (e.g., "number of tool calls made"), a loop that calls different tools each iteration will show progress. Use a semantic progress metric — whether the task output has meaningfully changed — not a behavioral one.
- **Circuit breakers protect the provider, not your agent.** Opening a circuit breaker on a failed API stops your agent from hitting a dead service, but your agent still needs a fallback behavior. A circuit breaker without a fallback is just a more expensive failure.
