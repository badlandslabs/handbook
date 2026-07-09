# S-877 · The Grounded Recovery Stack — When Your Agent Returns 200 OK and Everything Is Wrong

[Your agent just ran for 11 days straight. It spent $47,000. It never crashed. It never errored. It just kept looping — search, read, think, search, read, think — politely producing nothing while burning through credits. This isn't a crash. It's the default behavior of an unconstrained agent. The fix is not better prompts. The fix is a recovery architecture.]

## Forces

- **Agents fail silently, not loudly.** A conventional service crashes and logs a stack trace. An agent returns 200 OK with a confidently wrong answer, or keeps looping with no signal that anything is wrong. Traditional APM doesn't see it because the request is still "succeeding."
- **Retries without contracts amplify damage.** Unbounded retries on a degraded dependency turn a partial outage into platform-wide pressure. At 500 jobs/minute with 3 retry attempts each, that's 15,000 avoidable calls in 10 minutes — and that's before the circuit opens.
- **You can't fix what you can't see.** Most observability tools record *what* happened, not *why* the agent deviated. The key question during post-mortems — "at step T, intent was Z but execution was W" — is unanswerable without step-level traces.
- **Context is both the asset and the failure mode.** Agents accumulate state across steps, which enables coherent multi-turn reasoning. It also causes them to drift, loop, or halt when context overflows the model's effective window.

## The Move

Build recovery into the agent's execution loop — not as an afterthought retry wrapper, but as a structured system of contracts, circuit breakers, explicit state signals, and escalation gates.

### 1. Make tool results self-describing

Ambiguous tool results are the leading cause of loops. When a search returns an empty array, the agent can't tell if "no results yet" means "keep trying" or "search is definitive." Fix the tool, not the prompt.

```json
{
  "status": "complete",
  "result": [],
  "message": "Search completed. No results found for query. This is definitive — do not retry."
}
```

The explicit `"do not retry"` in natural language inside the result message is what makes this work — the LLM reads it as instruction, not observation. This single change eliminates roughly 40% of loops in production systems.

### 2. Write per-tool retry contracts, not global exception handlers

Every LLM or tool call needs its own contract specifying: which exceptions trigger retry, maximum attempts, backoff strategy, and what to do when exhausted. Retries and idempotency are a package deal — a retried step without an idempotency key duplicates the side effect it was trying to fix.

```python
retry_policy = RetryPolicy(
    max_attempts=3,
    backoff=Backoff.exponential(base=2, jitter=True),
    retryable_exceptions=[RateLimitError, TimeoutError, ServiceUnavailable],
    fatal_exceptions=[AuthError, PermissionError],
    idempotency_key=f"{tool_name}:{input_hash}"
)
```

Per-tool contracts beat a global try/except because different tools fail differently. A database timeout should retry differently than a malformed JSON return.

### 3. Add circuit breakers at the tool level

Retries alone amplify outages. Circuit breakers isolate failures before they cascade. A breaker trips after N consecutive failures on a single tool, then either fails-closed (reject calls, return error) or fails-open (allow through with a warning flag) depending on the risk posture.

Best practice: per-tool circuit isolation so a broken search doesn't take down the agent's code execution. Also consider confidence-aware tripping — if a tool returns results below a confidence threshold 3 times in a row, trip early even if individual calls succeed.

### 4. Detect loops deterministically, not probabilistically

Track a hash of recent (action, observation) pairs. If the same pair repeats N times within a sliding window, the agent is looping — not "thinking deeply." Trigger a hard stop and surface the checkpoint.

Structural loops differ from retry loops: the agent makes progress on each attempt (improving gradually) versus making no progress (identical output). Treat them differently. Loop detection should distinguish:

- **Same-action loop:** identical tool call with identical arguments → halt immediately
- **Progress-hampered loop:** similar calls with slight variations → increase backoff, alert, offer checkpoint restore

### 5. Checkpoint state and make recovery resumable

Store agent state at decision points: current plan, tool history, accumulated context, and the specific question being answered. If the agent crashes, loops, or halts, the next run restores from checkpoint instead of restarting from scratch.

Checkpoints are especially valuable for long-running tasks where losing 30 minutes of progress is costly. The checkpoint should capture enough to reconstruct the agent's reasoning chain, not just the tool outputs.

### 6. Build an escalation gate

Not every failure should retry. Define explicit escalation triggers:

- Irreversible action attempted (delete, write, publish) when agent is in degraded state
- Cost or step budget exhausted
- Loop detected after max retries
- Human-in-the-loop required for high-confidence decisions above a risk threshold

The escalation gate is a governance decision, not just a code path. It should produce a human-readable receipt explaining what the agent was trying to do, why it stopped, and what information a reviewer needs to decide next steps.

### 7. Observe the full trajectory, not just outcomes

Traditional APM records request count, latency, and error rate. Agent observability records: tool calls with arguments, reasoning steps, state transitions, memory operations, and cost per step. The failure signal is "wrong tool called with wrong arguments" — not an HTTP 500.

Capture: step number, LLM input/output tokens, tool called, tool arguments, tool result, cumulative cost, reasoning summary. This makes the "at step T, intent was Z but execution was W" question answerable in post-mortems.

## Evidence

- **Blog post (Coasty AI, May 2026):** Documented the $47,000 11-day infinite loop — a production agent stuck in search/read/think cycle with no crash, no alert, no stop condition. Core failure: no loop detection, no step budget, no cost ceiling. — [https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories](https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories)

- **Blog post (AIwave, 2026):** Empirical finding that explicit self-describing tool result status (`"status": "complete"` with natural language explanation) eliminates ~40% of production loops. Four root causes of agent loops identified: ambiguous tool results, planning drift, tool call errors, and context overflow. — [https://aiwave.hashnode.dev/why-your-ai-agent-keeps-looping-and-how-to-fix-it-a-deep-dive-into-react-pattern-failures](https://aiwave.hashnode.dev/why-your-ai-agent-keeps-looping-and-how-to-fix-it-a-deep-dive-into-react-pattern-failures)

- **HN Ask discussion (2026):** 18+ commenters on monitoring production agents. Key insight: existing tools log *what* happened, not *why* the agent deviated from intent. AgentShield and Lava identified as solutions providing step-level traces, risk detection on outputs, cost tracking per agent, and human-in-the-loop for high-risk actions. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

- **GitHub repo (REA Technologies, 2026):** Open-source circuit breaker library for agent-to-tool communication with per-tool breakers, confidence-aware tripping, cost-aware tripping, and gradual HALF_OPEN recovery. State persists across restarts via Redis/DynamoDB/Firestore. — [https://github.com/reaatech/circuit-breaker-agents](https://github.com/reaatech/circuit-breaker-agents)

- **GitHub repo (agairola, 2026):** "Securing the Ralph Wiggum Loop" — security scan integrated into autonomous coding agent loop. Pattern: implement → scan → fix iteratively (3x) → escalate if stuck → human review. Distinguishes between recoverable failures (fix in loop) and terminal failures (escalate). — [https://github.com/agairola/securing-ralph-loop](https://github.com/agairola/securing-ralph-loop)

- **Research note (Zylos, May 2026):** Taxonomy of agent failures: agents fail by silently looping, spawning redundant subprocesses, accumulating context until model halts, or taking irreversible actions before intervention. Proposes supervisor tree pattern (borrowed from distributed systems) for agent-level fault isolation. — [https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)

## Gotchas

- **Blanket retry wrapping around the whole agent is worse than no retry.** A global try/except around the agent run retries everything including non-retryable failures (auth errors, malformed prompts), amplifying the outage and masking the real problem.
- **Agents don't return error codes — they return confident nonsense.** You need output validation separate from error handling. A tool call that "succeeds" but returns garbage needs different treatment than one that throws an exception.
- **Checkpoint frequency is a trade-off.** Checkpointing every step creates overhead and storage cost. Checkpointing only at the end means you lose all progress on failure. The sweet spot: checkpoint at decision points (after tool call completes, before next action).
- **Fail-open vs. fail-closed is a risk posture decision, not a technical one.** Fail-open (let requests through with a warning when the safety service is down) is higher risk but higher availability. Fail-closed (reject when uncertain) is safer but less available. Choose explicitly per tool based on the consequences of a wrong call.
