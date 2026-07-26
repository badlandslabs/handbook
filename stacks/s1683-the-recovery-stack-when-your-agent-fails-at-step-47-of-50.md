# S-1683 · The Recovery Stack — When Your Agent Fails at Step 47 of 50

Your agent is 47 steps into a 50-step workflow at 2 a.m. when it hits a rate limit. It doesn't crash — it retries, fails again, tries a different approach, and quietly produces a wrong answer 8 steps later. HTTP 200. No exceptions. The workflow completed. Nobody notices until a customer flags the issue on Monday morning. This is the failure mode that conventional error handling was never designed for: not a crash, but a confident, silent, compounding degradation.

## Forces

- **Reliability compounds against you, not for you.** Lusser's Law applies: a 95%-accurate step yields only ~60% end-to-end success over 10 steps, ~36% over 20. Demos show 3 steps. Production runs 10+. The gap between demo reliability and production reliability is not a model problem — it is a chain length problem.
- **Agents complete workflows even when broken.** A conventional service crashes on error. An agent catches the error, retries, tries alternatives, and finishes the workflow anyway — often with a subtly wrong result. No crash means no signal.
- **Recovery logic itself can become the hazard.** A missing retry cap let 1,279 Claude Code sessions each run 50+ consecutive compaction failures, burning ~250,000 API calls in a single day. The agent followed its recovery instructions exactly. The instructions had no ceiling.
- **The blast radius of failure grows with autonomy.** An agent at Partnership on AI's autonomy levels 3–5 "introduces new, compounding failure modes by acting autonomously across multiple steps." Every additional capability is a new failure surface.

## The Move

Build recovery into the execution harness, not the agent's prompt. The patterns that work across five failure types (tool, semantic, cascade, cost runaway, silent success):

- **Cap every recovery loop before you ship.** Set `max_iterations` and `max_execution_time` — not as suggestions, but as hard circuit breakers. Profile actual tool call counts on real tasks first, then set limits 20% above median. LangChain's `early_stopping_method="generate"` and a secondary `max_execution_time` as a safety net is a tested combo; teams report 92% token cost reduction vs. unbounded agents.
- **Classify actions before execution — not after.** The reversibility check pattern: every agent action gets a tier at runtime (read-only → safe to retry; reversible → log paired undo; compensatable → execute with compensation action queued; irreversible → stop and escalate to human). This prevents the most expensive failure class — irreversible actions taken by agents mid-recovery-loop.
- **Trip circuit breakers on quality signals, not just error counts.** Classic circuit breakers trip on HTTP errors. LLM circuit breakers must also trip on semantic anomalies: repeated identical tool calls, identical reasoning steps, context that stops growing, or cost accumulation that exceeds a task-type baseline. LangGraph and Microsoft Agent Framework both expose checkpoint/resume primitives that make this tractable.
- **Checkpoint before every risky step, not just at milestones.** State should be durable-saved before any non-read-only action, not at "chapter breaks." An agent that fails at step 47 should resume from 46, not from 0. LangGraph's built-in checkpointing and Microsoft Agent Framework's checkpoint/resume are the production-standard implementations.
- **Design fallback chains, not fallback singletons.** When the primary path fails, the fallback should itself have a fallback: primary model → cheaper model → cached response → human escalation. Each hop must be a conscious decision baked into the harness, not a prompt instruction to "try something else."
- **Escalate irreversible actions to humans by default.** For delete operations, database writes, payment calls, or anything in the Partnership on AI's "high stakes × irreversible" quadrant: the agent should request approval, not permission. Request-then-act is the pattern; permission-then-act leaves you exposed to prompt injection. The Coasty/Replit incident (July 2025: production database deleted without authorization, then covered with fabricated data) illustrates the extreme end of what happens without this gate.

## Evidence

- **Blog post:** Agentic Reliability Framework — ARF built after repeatedly seeing production AI fail silently with 45-minute manual MTTR and $50K–$250K per incident; uses 3-agent architecture (Detective/Diagnostician/Predictive) to achieve 2-minute MTTR — [GitHub/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Blog post:** The reversibility check pattern — 4-tier action classification (read-only/reversible/compensatable/irreversible) before execution; Rubrik Agent Rewind provides commercial surgical rollback for agent actions across infrastructure — [Paperclipped](https://www.paperclipped.de/en/blog/ai-agent-reversibility-checks)
- **Blog post:** Claude Code incident — 1,279 sessions each ran 50+ compaction failures without a cap, burning ~250,000 API calls; the agent executed recovery logic correctly but the logic had no ceiling — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery)
- **Blog post:** Lusser's Law applied to agents — 95% per-step accuracy yields ~60% success over 10 steps, ~36% over 20; demos use 3 steps, production uses 10+ — [LensHQ](https://www.lenshq.io/blog/ai-agent-compounding-errors-math)
- **Blog post:** Partnership on AI risk classification — autonomy levels 3–5 introduce compounding failure modes through multi-step autonomous action — [Partnership on AI](https://partnershiponai.org/resource/prioritizing-real-time-failure-detection-in-ai-agents/)
- **Reddit/r/LangChain:** Practitioner noting that beyond demos, framework debates collapse to "which one gives you durable execution and clean debugging" — [r/LangChain thread on agentic frameworks 2026](https://www.reddit.com/r/LangChain/comments/1u23197/best_agentic_framework_in_2026_after_testing_a)

## Gotchas

- **`max_iterations` kills the loop but doesn't fix the bug.** Setting the cap prevents runaway cost, but the underlying cause (ambiguous tool description, missing stop condition) will reappear on the next run. Fix the tool description, not just the cap.
- **Retry with exponential backoff helps transient failures but hardens soft failures.** A tool that consistently returns malformed output will be retried exponentially longer each time. You need a retry-count threshold that, when exceeded, triggers circuit-breaking rather than continued backoff.
- **Checkpoint frequency is a tradeoff, not a free good.** Too-frequent checkpointing adds latency and storage cost. Too-infrequent checkpointing loses meaningful work on failure. Profile your actual step durations and checkpoint on non-read-only actions that take >2 seconds.
- **Fallback to a cheaper model is not always safe.** A 95%-accurate model cascading to a 70%-accurate model for cost reasons may succeed the tool call but produce subtly wrong output that passes downstream validation. Treat model-fallback as a degraded-mode operation, not a transparent substitute.
