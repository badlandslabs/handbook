# S-2902 · The Agentic Failure Recovery Stack — When Your Agent Fails Invisibly and Nobody Knows Until the Budget Is Gone

An agent calls a payment API, gets a 429 rate limit, waits 2 seconds, retries, gets another 429, waits 4 seconds, retries — then loops that cycle for 47 minutes until someone notices. Traditional error handling (try/catch, HTTP status codes) covers the obvious failures. Agentic systems add a layer of silent, budget-burning failures that return HTTP 200 but produce semantically wrong output, enter infinite tool-call oscillation, or crash mid-workflow and restart from scratch instead of from the last good state.

## Forces

- **Agents fail in ways that don't throw exceptions.** The payment API returned 200 but the agent hallucinated the endpoint. The email was sent but to the wrong address. The LLM produces confident nonsense with no exception to catch.
- **Retry loops are silent budget leaks.** A missing `recursion_limit` or `max_iterations` guard lets an agent retry a failing operation exponentially until your API quota is gone. This is the most common production failure mode teams discover the hard way.
- **Restart ≠ recovery.** When a long-running agent crashes, restarting it from the same prompt doesn't restore state — the agent's "knowledge" of where it was in the workflow is gone. Decision drift compounds: the restarted agent may make different choices from the same context.
- **Soft errors outnumber hard errors in production.** Rate limits, timeouts, and ambiguous outputs are 10x more frequent than actual API outages. The recovery strategy must match the failure type, or you waste recovery attempts on unsolvable problems.
- **Self-correction only works if the agent can observe its failure.** If the agent doesn't know it failed — if the tool returned "success" but the result is wrong — correction never triggers.

## The Move

Layer your failure handling in three tiers, matched to failure type:

**Tier 1 — Failure Classification & Routing**
- Classify every non-success into: transient (retry-able), persistent (fallback), or semantic (validator required). Route each class to its handler.
- Common production failure taxonomy:

| Type | Example | Handler |
|---|---|---|
| Rate limit (429) | API quota hit | Retry with exponential backoff |
| Server error (500/503) | Provider outage | Fallback to another model/provider |
| Timeout | Reasoning too slow | Increase timeout or simplify task |
| Invalid output | Malformed JSON | Retry with stricter prompt |
| Hallucinated tool | Calls non-existent function | Validate tool schema before exec |
| Infinite loop | Same tool re-called with rephrased args | Semantic loop detection, not just counter |

**Tier 2 — Guardrails That Actually Guard**
- Set `max_iterations` — a hard stop after N steps regardless of whether the agent thinks it's making progress. Teams report cutting token costs 60–90% with this alone.
- Add **semantic loop detection** beyond naive iteration counters. Agents rephrase the same failing call ("weather chicago" → "weather in chicago today") to bypass exact-match hash checks. Use text similarity scoring on the last N tool calls to catch oscillation.
- Implement a **circuit breaker**: after N consecutive failures on the same operation, stop attempting and escalate to a human or queue for manual review. Prevents cascading failures from taking down downstream systems.
- The specific pattern validated in production: `max_iterations=15` + compare last 3 thoughts for semantic similarity + step-level timeout.

**Tier 3 — Checkpoint/Resume for State Durability**
- Save state after each "superstep" (completed unit of work), not just at workflow end. When an agent crashes, it resumes from the last checkpoint — not from the beginning.
- Checkpoints capture: current agent state, pending messages, pending requests/responses, shared state. Microsoft Agent Framework ships three built-ins (InMemory, File, CosmosDB).
- Recognize the **decision drift problem**: a crashed agent restarted with the same prompt does not reproduce the same workflow. A day-1 agent that was 60% through a data normalization task will not pick up where it left off from context alone — checkpoint state must be explicit, not inferred.
- For stateless restarts (no checkpoint infrastructure), the `agent-checkpoint-resume` pattern: replay the execution log against the same environment to reconstruct exact pre-crash state, then resume from that snapshot.

**Self-Correction as a First-Class Loop**
- Reflexion (Shinn et al., NeurIPS 2023) formalized this: instead of weight updates, agents learn from failure by incorporating verbal feedback into their memory. After each failed attempt, the agent generates a self-reflection ("I failed because X, next time I will try Y") and uses that to guide the next attempt.
- Production implementation: a separate "Verifier Agent" (smaller, faster model) validates tool outputs independently. If the Verifier says "no," it triggers a self-correction loop — same as a hard error.
- Keep correction depth bounded. After N correction attempts, escalate rather than spiral into increasingly unlikely attempts.

## Evidence

- **GitHub README:** `agent-checkpoint-resume` — demonstrates the decision drift problem with a pure-stdlib example: a financial record normalizer crashes mid-workflow; restarting from the same prompt produces different results because the model's probabilistic decisions diverge. Exact checkpoint-and-resume (serializing state, not just prompt) is required. — [https://github.com/crzyc0d3r/agent-checkpoint-resume](https://github.com/crzyc0d3r/agent-checkpoint-resume)
- **Blog post (Markaicode, March 2026):** Production LangGraph multi-agent walkthrough documents the concrete fix for infinite loops in a real system: `max_iterations=15` + semantic similarity check on last 3 tool calls + per-step timeout. The trace shows it validated by watching the run succeed after the guardrails were added. — [https://markaicode.com/langgraph-production-agent](https://markaicode.com/langgraph-production-agent)
- **GitHub repo (LoopGuard, MIT):** Framework-agnostic zero-dependency library for semantic loop detection. Documents three loop types agents exhibit: Tool-Call Oscillation (alternating between two tools), Semantic Repetition (rephrasing the same query), and Exact State Loops (identical tool calls). Naive iteration counters miss the first two. — [https://github.com/Charbelto/loopguard](https://github.com/Charbelto/loopguard)
- **Academic paper (Shinn et al., NeurIPS 2023):** Reflexion — agents use verbal self-reflection to learn from failures without weight updates. On AlfWorld (interactive environment), HotpotQA, and WebShop benchmarks, Reflexion agents outperform non-reflecting baselines by learning from explicit failure narratives. 3,235 GitHub stars. — [https://github.com/noahshinn/reflexion](https://github.com/noahshinn/reflexion)
- **Reddit r/LocalLLaMA:** Practitioner posts documenting "get stuck in loops w tool calls" — happening "VERY frequently" with LM Studio. Root causes identified in comments: ambiguous tool descriptions, missing stop conditions, no iteration limits. — [https://www.reddit.com/r/LocalLLaMA/comments/1s1bjtr/getting_stuck_in_loops_w_tool_calls/](https://www.reddit.com/r/LocalLLaMA/comments/1s1bjtr/getting_stuck_in_loops_w_tool_calls/)
- **HN Show HN (Optio):** Developer notes agents self-correct when they "can bash up against a guardrail and see the errors." The pattern: resume agent on failure, provide error feedback, let it attempt a fix. — [https://news.ycombinator.com/item?id=47520220](https://news.ycombinator.com/item?id=47520220)

## Gotchas

- **A retry without backoff is a DoS attack on your own infrastructure.** If you retry on a 429 immediately, you'll stay rate-limited. Use exponential backoff with jitter (e.g., `delay = min(base * 2^attempt + random_jitter, max_delay)`).
- **A verifier agent that has the same context as the primary agent will share its blind spots.** Keep the verifier's task narrow and its prompt distinct — its job is validation, not reasoning toward the answer.
- **Checkpoint frequency is a tradeoff.** Saving after every tool call is safe but expensive. Saving only at workflow end loses the recovery benefit. Saving at "superstep" boundaries (completed logical units of work) is the practical sweet spot.
- **Circuit breakers must have a reset mechanism.** A breaker that trips and never resets is a different kind of failure. Include automatic retry-after-N-minutes or manual reset.
- **Self-correction depth limits are not optional.** Without them, a stubborn agent can spend hours on an impossible task. Cap correction attempts and route to human escalation when the cap is hit.
