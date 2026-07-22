# S-1510 · The Falling Agent Stack — When Your Agent Fails and No One Notices

Your agent ran 2,000 tasks last week. None raised an exception. Three hundred produced subtly wrong outputs — a formatted response instead of a structured one, a 200 OK from an API the agent invented, a loop that kept making progress until the context window collapsed. The agent didn't fail loudly. It failed quietly, expensively, and by the time you noticed, the damage was baked in. This is the failure detection gap: the time between when an agent goes wrong and when anyone knows.

## Forces

- **Agents fail silently.** The API returned 200. The tool call completed. The model hallucinated a plausible-but-wrong answer and moved on. Traditional error handling catches exceptions — it doesn't catch semantics.
- **Activity ≠ progress.** A stuck loop still makes API calls, edits files, and generates tokens. The activity signals that fire for traditional crashes are useless here. The agent looks alive when it isn't.
- **Failure categories don't map to HTTP codes.** Rate limits (429) are transient and retryable. Authentication rot is semi-transient. A model that confidently answers a question it can't answer is a semantic failure — and there's no error code for that.
- **Recovery without diagnosis wastes attempts.** A retry that re-runs the same flawed reasoning loop just burns tokens and cost. Recovery must address root cause, not surface symptom.
- **Humans escalate too late.** By the time a human reviews output, the task context is cold. Real escalation needs to happen within the agent's own execution loop.

## The Move

Build a layered failure handling system in three concentric rings:

**Ring 1 — Detection:**
- Instrument progress metrics, not just activity. The signal is "checklist items completed" or "unique sources gathered" — something that only rises on real work, not loop iterations.
- Detect stuck loops via flat progress across N heartbeats while activity continues. Set heartbeat intervals and flat thresholds empirically per task type.
- Distinguish loop types: hard loops (exact repetition), soft loops (slight variations), semantic loops (plausible variation with no convergence). Each needs a different intervention.
- Catch infrastructure failures via explicit error codes: rate limits, server errors, auth expiry, schema drift. These are the 1–5% of tool calls that fail visibly but cluster during traffic spikes.

**Ring 2 — Recovery Ladder:**
Escalate through interventions in order of cost:

1. **Nudge** — Inject a hint into context: "you appear to be repeating the same approach; consider an alternative strategy." Cheapest fix, fires first.
2. **Replan** — Truncate context to last meaningful state, provide a revised directive, re-enter the loop. Breaks the trajectory without losing all progress.
3. **Reset** — Drop to a checkpoint before the failure point and restart the step. Use for hard loops and state corruption.
4. **Fallback model** — Switch to a smaller, cheaper model for a retry. Works for transient model capability blips; doesn't fix fundamentally wrong approaches.
5. **Human handoff** — Surface the failure signal, the agent's last state, and a summary of what was attempted. Last resort; don't make it the first option.

**Ring 3 — Circuit Breakers:**
- Trip at threshold: 3–5 consecutive failures on a single tool or dependency.
- Hold open for 30–60 seconds before probing for recovery.
- Share state across replicas via Redis or equivalent distributed store.
- Configure fail modes: `POLICY_CHECK_FAIL_MODE=closed` requeues; `open` allows through with bypass signals for safety checks.
- Cap retry storms: at 500 jobs/min with 3 retries each, naive retrying adds 15,000 avoidable calls in 10 minutes. Circuit breakers prevent this amplification.

**Bonus — Reflexion-style self-critique:**
- After each major step, ask the agent to critique its own output: "did this actually accomplish the goal, or just produce a plausible result?"
- Store critiques in episodic memory. Reference them on retry so the agent doesn't repeat the same wrong approach.
- This is the highest-leverage pattern for semantic failures — the kind no error code catches.

## Evidence

- **GitHub Discussion:** Anthropic SDK community discussion on error recovery patterns — teams using exponential backoff (1s→2s→4s→8s, max 3 retries, 30% jitter, 60s ceiling), idempotency keys for non-idempotent operations, and tiered retry configs distinguishing retryable vs. dangerous operations. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **Research Synthesis:** Zylos Research synthesis (2026-05-06) on agent self-healing — multi-agent failure breakdown: ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps. Key insight: a 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time; failure handling compounds across the pipeline. — [zylos.ai](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)

- **Open-source MCP tool:** agent-guard-mcp (Mohammed Abukhamsin, 2026-04-23) — MCP server implementing circuit breakers, pattern detection, and stuck-agent recovery recommendations as a production tool, not just a conceptual pattern. — [github.com/mdfifty50-boop/agent-guard-mcp](https://github.com/mdfifty50-boop/agent-guard-mcp)

- **Academic:** Reflexion (Shinn et al., arXiv:2303.11366) — self-critique + episodic memory architecture where agents explicitly evaluate their own outputs and store reflections for future steps. Cited 6,000+ times; foundation for production self-correction patterns. — [arxiv.org/abs/2303.11366](https://arxiv.org/abs/2303.11366)

## Gotchas

- **Setting max_steps too high is the #1 cause of runaway loops.** Teams pick round numbers (100 steps) instead of task-appropriate limits. Start with generous limits, then measure actual convergence rates and tighten.
- **Activity-based loop detection produces false negatives.** A wandering loop (slight variation each time) generates different tokens each iteration — it won't trigger repetition detection. Only progress-metric-flat detection catches it.
- **Retry storms are a distributed systems problem, not a model problem.** The LLM is fine; the orchestration layer is hammering a degraded dependency. Fix it with circuit breakers, not better prompts.
- **Human handoff without state serialization is useless.** If the escalation doesn't include the agent's full context (what it's trying to do, what's been tried, what the last output was), the human can't make an informed decision.
- **Semantic failures require domain-specific validators.** The model saying "this looks right" is not a validator. You need task-specific checks: "does this API response match the expected schema?", "are these numbers within plausible ranges?", "did this code compile?".
