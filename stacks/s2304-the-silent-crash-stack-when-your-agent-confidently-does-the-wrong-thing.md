# S-2304 · The Silent Crash Stack — When Your Agent Confidently Does the Wrong Thing

Your agent returned HTTP 200. It declared success. The task was done — except the downstream record was wrong, the email was sent to the wrong address, and the refund was approved at 3x the requested amount. No error was thrown. No alarm fired. This is the silent crash: the failure mode that kills production agentic systems and that traditional error handling can't see.

## Forces

- **Agents fail with success codes.** Unlike deterministic software, AI agents produce confident wrong outputs that return HTTP 200 — no exception, no stack trace, no signal. A tool call that returns malformed JSON is technically a 200.
- **Early errors compound exponentially.** In a multi-step agent (plan → retrieve → synthesize → execute), a small error at step 2 collapses every subsequent step. There's no transaction rollback — only cascading wrongness.
- **The retry instinct is wrong for some failures.** A blanket `except: retry` burns tokens on 401s, 400s, and hallucination spirals where retrying changes nothing except your invoice.
- **max_iterations is a blunt instrument.** Stop too early and you clip a loop still improving. Stop too late and you've already shipped the wrong answer — one that was worse than what the loop had already found.

## The Move

Build a layered failure-handling architecture that classifies failures by type and routes each to the right response. Four layers, applied in order:

**Layer 1 — Retry with exponential backoff and jitter.** Wrap every external call. Only retry transient failures (429 rate limits, 503 server errors, brief timeouts). Never retry 400/401 without fixing the underlying cause first. Jitter prevents thundering-herd on shared provider resources.

**Layer 2 — Reasoning circuit breakers.** Traditional HTTP circuit breakers can't detect when an agent is burning tokens chasing its own tail — that returns 200 too. Measure **confidence trajectory** across recent turns: if confidence has degraded N consecutive steps, trip the breaker before token budget is exhausted. The agent-reliability-patterns library implements this by tracking `REASONING_CLOSED → REASONING_HALF_OPEN → REASONING_OPEN` states. A separate, smaller LLM ("verifier agent") can score each tool output for semantic correctness — if the verifier says the output doesn't answer the query, trigger correction as if it were a hard error.

**Layer 3 — Fallback chain.** When primary provider calls fail after retries, fall through to backup providers or models. Define fallback chains explicitly: primary → openrouter → google. Track cost multipliers and fallback event rates — if one provider consistently triggers fallbacks, investigate rather than silently paying premium rates.

**Layer 4 — Loop termination with convergence measurement.** Replace `max_iterations=N` with actual convergence detection. LoopGain (open-source, Apache 2.0) measures empirical loop gain (Aβ): the ratio of current error to previous error. Aβ < 1 means the error is shrinking — the loop is still improving. Aβ > 1 means the loop is diverging — terminate immediately and roll back to the best result already found. This prevents the common case where an agent oscillates between two wrong answers, finally lands on one, and gets shipped as if it were correct.

## Evidence

- **Production case study (Asynq.ai / Modelia.ai):** Candidate evaluation agent hallucinated tool parameters, entered infinite loops, produced contradictory outputs, and cost 3x budget in production. Image generation agent had no budget guard — ran indefinitely. Root cause: no failure classification, no recovery paths, no cost guardrails. — [Harsh Rastogi, AI Product Engineer, March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **HN Show HN (LoopGain):** Open-source library applying control theory to agent loop termination. Benchmarked across 2,000 real API runs, five loop patterns, three model providers. Found that max_iterations fails in both directions: clips improving loops and ships diverged answers. Replaced with loop gain (Aβ) measurement. — [Hacker News, Show HN, 2026](https://news.ycombinator.com/item?id=48919562)
- **GitHub (agent-reliability-patterns):** MIT-licensed library implementing reasoning circuit breakers for AI agents. Detects confidence degradation, token exhaustion, and hallucination spirals — failure modes that return HTTP 200. Ships with benchmark suite for measuring pattern effectiveness. — [hamley241/agent-reliability-patterns, GitHub, March 2026](https://github.com/hamley241/agent-reliability-patterns)
- **LangGraph / Reflexion:** LangGraph's `create_react_agent` is now the baseline; the differentiator in production is the reflection layer. Generate → critique → revise loop where a separate LLM critic scores each output. Reflexion accumulates verbal self-reinforcement across episodes. In practice: pays off in code generation and report writing; overhead in tool-use loops where the environment already provides feedback (lint errors, test failures). — [LangGraph docs, travism26/agentlog research, 2026](https://github.com/travism26/agentlog/blob/main/research/langgraph_patterns_2026.md)

## Gotchas

- **Don't retry everything.** A blanket `except Exception: retry` is worse than no retry — it re-submits 400 errors, auth failures, and hallucination spirals, burning budget without recovery. Classify failures first.
- **Fallback chains have cost implications.** Falling back to a premium provider is cheaper than a complete outage, but only if you track fallback rates. A provider that consistently triggers fallback should be investigated or deprioritized, not silently subsidized.
- **Checkpoint state before risky steps.** If a tool call will modify external state (send email, approve refund, update record), checkpoint the agent's full state before executing. On failure, recover from checkpoint rather than replaying from scratch.
- **Verifier agents add latency.** Semantic verification of every tool output via a separate LLM call roughly doubles the per-step cost. Gate it on critical steps only, not every tool call.
- **Aβ termination can ship a previous result.** When LoopGain terminates on divergence, it returns the best result found so far — which may be from iteration 3 of 20. Test that your downstream can handle "best effort" results, not just "final iteration" results.
