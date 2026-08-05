# S-2165 · The Semantic Health Stack — When Your Agent Is Running But Isn't Working

Your agent is running fine. It returns HTTP 200. It calls tools. It generates output. But it's looping on the same three actions, drifting from its original goal, or producing confident nonsense that passes every health check. Your liveness probe says healthy. Your agent is broken. The gap between "running" and "working" is where most agentic failures live undetected.

## Forces

- **Liveness ≠ health.** Traditional health checks detect crashes. Agents crash rarely — they degrade silently, producing plausible-but-wrong output at every step. A heartbeat passing means the process is alive, not that the agent is doing useful work.
- **Activity ≠ progress.** An agent can call tools, generate responses, and show high throughput while making zero net progress toward the goal. Standard metrics (throughput, token count, response latency) are all green while the agent is failing.
- **The detection-recovery gap.** Most teams build recovery before detection. Without a signal that failure occurred, the most sophisticated recovery system never fires. The failure sits in the logs until a human notices.
- **No crash, no trace.** Semantic failures — drift, loops, constraint erosion — don't produce exceptions. They produce output that looks correct until you check it against the actual goal.

## The Move

Build a signal layer between the agent and its environment that detects the four failure modes liveness checks miss. Each layer targets a distinct failure signature.

**1. Loop detection via iteration caps and state hashing.** Compile the graph with an explicit `recursion_limit` (default 25 for most tasks, tunable). Beyond catching infinite loops, track a rolling hash of the agent's last N states — if the same state repeats within a threshold, it signals a reasoning loop even if the agent hasn't hit the cap. The hash captures the *reasoning path*, not just the output. — [Verel Systems, 2025-11-15](https://verelsystems.com/en/blog/langgraph-production-patterns)

**2. Progress health checks that ask "did we move?"** Every N steps (or every tool call), invoke a lightweight grader agent: *Given the original goal and the last 3 actions taken, is the agent making net progress toward the goal?* A "no" from the grader is a health signal your liveness check never produced. This catches semantic drift (high activity, zero goal movement) that throughput metrics hide. — [Zylos Research, 2026-03-02](https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns/)

**3. Constraint drift detection via periodic re-verification.** The longer an agent runs, the more system-prompt constraints degrade (HN practitioners call this "instructions are suggestions — the longer the chain, the more they're ignored"). Inject a constraint re-checker at natural task boundaries: re-read the original constraints and the current agent state, and flag any drift. — [Hacker News, Ask HN discussion, 2025](https://news.ycombinator.com/item?id=47039354)

**4. Output plausibility guards on every tool call.** Traditional validation checks whether the tool returned. Agentic validation checks whether the output is *useful* — does it answer the question the tool was supposed to answer? A verifier agent (smaller, faster model) validates each tool output before it feeds into the next reasoning step. A "no" from the verifier triggers self-correction. — [AI System Design Guide, GitHub, 2025](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

**5. Token budget sentinel.** Agents can exhaust token budgets silently, producing truncated responses that look complete. Set a configurable `max_tokens` cap per step and per-run, and emit a health signal when consumption reaches 80% of the per-step budget — not a failure, but an early warning that allows graceful degradation before the agent goes off the rails on truncated context.

## Evidence

- **Hacker News (Ask HN):** Practitioners report agents "lose track of what they already did, re-implement things, or contradict decisions from 20 minutes ago." The identified root cause: agents cannot be trusted to maintain their own state over long chains. External health signals that survive state compaction are required. — [HN Ask: Limitations of Agentic AI in Real-World Workflows](https://news.ycombinator.com/item?id=47039354)
- **Research (Pandey, arXiv 2605.01604):** Analysis of billion-event-scale production systems identifies seven failure modes unique to production agents. Four of these seven — compounding decision errors, non-deterministic output drift, goal neglect, and planning horizon collapse — are invisible to standard metrics (ROUGE, BERTScore, accuracy) and require purpose-built detection. The paper proposes PAEF (Production Agentic Evaluation Framework) with five monitoring dimensions including semantic progress tracking. — [Evaluating Agentic AI in the Wild, arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **Open-source (Tanay Shah, ai-agent-error-patterns):** Production implementation of circuit breaker + partial success + HITL + graceful degradation patterns using Trigger.dev v4. The library documents that partial batch failures (e.g., 95 items succeed, 5 silently fail) are the most common undetected production failure — occurring in week 2 of deployment after demos show 100% success on small batches. — [GitHub: tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)
- **LangGraph production guide (Verel Systems):** Documents the `recursion_limit` pattern with verified code examples: *"Without it, a confused LLM can loop indefinitely and burn your API budget."* Recommends 25 iterations as a reasonable default, with checkpointing at each iteration boundary for recovery. — [LangGraph Development: 5 Patterns for Production-Safe Agents](https://verelsystems.com/en/blog/langgraph-production-patterns)

## Gotchas

- **Iteration limits stop loops but don't diagnose them.** A recursion limit fires after the agent is already stuck. Pair it with state-hash detection to catch incipient loops before they hit the cap.
- **Health checks cost tokens.** Every grader invocation and constraint re-verification adds inference overhead. Budget for it — typically 5-10% additional token cost — or the detection layer becomes a bottleneck.
- **Plausible output passes naive validation.** Tool calls returning HTTP 200 are not evidence of success. Build semantic output validation (verifier agent) into every tool boundary, not just the final output.
- **Checkpointing without health signals is insufficient.** LangGraph's checkpointing saves state for resume — but if you never detect that a failure occurred, you resume into the same broken reasoning path. Detection must precede recovery.
