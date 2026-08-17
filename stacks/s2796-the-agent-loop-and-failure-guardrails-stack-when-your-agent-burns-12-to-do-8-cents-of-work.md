# S-2796 · The Agent Loop & Failure Guardrails Stack

_When your agent spins for 20+ steps and burns $12 to do what should cost $0.08 — or worse, loops forever with no exit_

## Forces

- Agents have no self-awareness about loops — from the LLM's perspective, every retry is a fresh attempt with renewed optimism. The loop must be broken _outside_ the model.
- Four distinct failure domains require different solutions: transient transport errors (retry with backoff), output validation failures (re-prompt with specifics), state loss (checkpoint and resume), and structural failures (fallback or escalate).
- The cost asymmetry is severe: a normal task takes 3–4 steps at ~$0.08, but a looped agent can spend $12 and deliver nothing.
- Multi-agent pipelines introduce cascading failure modes — one hung agent can block an entire pipeline, exhausting memory and connection pools.
- Iteration limits are the floor, not the ceiling — "hit the limit and escalate to human" is the right mental model, not "try harder."

## The Move

Build guardrails in three layers: **prevent** the loop from forming, **detect** it if prevention fails, and **recover** gracefully with partial results.

**1. Hash-based loop detection — outside the agent's context:**
- Track the hash of `(tool_name, args)` pairs across steps
- If the same hash appears 2–3 times consecutively, interrupt with a circuit breaker
- Store recent observation hashes too — a loop can form around returning the same result without making forward progress

**2. Hard limits as escalation triggers, not failure:**
- Set `max_steps`, `max_tokens`, and `timeout` as _human escalation points_, not as "stop and fail"
- When a limit hits, return partial results with a clear `stop_reason` — do not silently truncate
- The mental model: "iteration limit is time to call the team lead, not try one more time"

**3. Node-level retry with exponential backoff on transient failures:**
- Wrap tool calls in `try/except` — catch rate limits (429), timeouts, and 5xx errors
- Retry with exponential backoff (e.g., 1s → 2s → 4s) up to a max attempts cap
- On exhaustion, route to a dedicated error_handler node instead of crashing the graph

**4. Structural failures get re-prompts, not retries:**
- If output validation fails (wrong schema, hallucinated fields), feed the exact error back to the LLM — "self-correction is a retry with a better error message"
- Transient failures (API down, rate limit) get retry; structural failures (wrong tool, bad args) get re-prompt

**5. Progress tracking — stop on no-signal:**
- After each step, hash the new state/observation
- If N consecutive steps produce no new signal (same hash), break the loop
- Combine with a "result delta" check: did this step produce information that wasn't in the previous step?

**6. Checkpoint state for recovery:**
- Persist step history, tool results, and intermediate state at defined checkpoints
- On crash, timeout, or manual restart, resume from the last checkpoint — don't re-run completed work

## Evidence

- **Research paper:** arXiv 2607.01641 — "When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents" (Huazhong University, July 2026). IAL-Scan static analyzer found **68 IAL failures across 47 real-world repositories** at 91.9% precision from 6,549 repos. Confirms loops are structural, not edge cases. — [https://arxiv.org/html/2607.01641v1](https://arxiv.org/html/2607.01641v1)

- **GitHub MCP docs:** `yigitkonur/docs-mcp-advanced-best-practices` — concrete hash-based state tracking pattern with code: store `(tool_name, args)` hashes in a sliding window, detect 2–3 consecutive repeats, interrupt with a circuit breaker. — [https://github.com/yigitkonur/docs-mcp-advanced-best-practices/blob/main/error-handling/08-circuit-breakers-for-loop-detection.md](https://github.com/yigitkonur/docs-mcp-advanced-best-practices/blob/main/error-handling/08-circuit-breakers-for-loop-detection.md)

- **GitHub repo + pattern site:** `hijrahassalam/ai-agent-loop` (npm package, zero-dependency) — guards ReAct loops with loop detection, token budgets, step limits, and duplicate call prevention. Backed by `agentpatterns.tech` — curated catalog (4,880 stars on GitHub) with traceable references for each pattern. Real example cited: "An AI agent spent $847 because there was no token budget and no step limit." — [https://github.com/hijrahassalam/ai-agent-loop](https://github.com/hijrahassalam/ai-agent-loop), [https://www.agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop)

- **Engineering blog:** `bestaiweb.ai` — "Retry, Fallback & Self-Correction in AI Agents (2026)" — categorizes failure into four domains with distinct solutions. Key insight: "Self-correction is just a retry with a better error message — let the validator tell the model exactly what was wrong." — [https://www.bestaiweb.ai/how-to-implement-retry-fallback-and-self-correction-loops-in-ai-agents-in-2026](https://www.bestaiweb.ai/how-to-implement-retry-fallback-and-self-correction-loops-in-ai-agents-in-2026)

- **GitHub:** `langchain-ai/langgraph` — official `RetryPolicy` with `max_attempts`, `RetryOn` whitelist, exponential backoff, and per-node `error_handler` for structured fault tolerance. ToolNode supports `on_error` handlers with custom retry logic. — [https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py](https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py), [https://www.langchain.com/blog/fault-tolerance-in-langgraph](https://www.langchain.com/blog/fault-tolerance-in-langgraph)

- **GitHub:** `petterjuan/agentic-reliability-framework` (v3.3.9) — multi-agent system with three specialized agents: Detective (anomaly detection via FAIS vector memory), Diagnostician (root cause analysis), and Predictive (failure forecasting). Claims 2-minute MTTR vs 45-minute manual recovery. — [https://github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)

## Gotchas

- **Conflating retry with recovery:** Retrying the same approach N times is not recovery — it's loop formation. After 2–3 retries, the problem is structural and needs a different strategy, not a fresh attempt.
- **Iteration limits without escalation:** A hard `max_steps` that just fails silently is almost as bad as no limit. Return partial results with a `stop_reason` so humans can inspect what was accomplished before the break.
- **Checkpointing the wrong unit:** Checkpoint the graph state (step history, tool results, intermediate artifacts), not just the prompt. On resume, the agent needs full context to know where it left off.
- **Missing the no-progress loop:** Agents can loop without repeating the exact same tool call — they might call different tools but return the same non-useful result. Hash-based detection must include observation hashes, not just action hashes.
- **Treating all failures the same:** A rate-limit error and a schema mismatch require different responses. Retry only transient errors; re-prompt only structural ones. Mixing them up wastes budget on unsolvable problems.
