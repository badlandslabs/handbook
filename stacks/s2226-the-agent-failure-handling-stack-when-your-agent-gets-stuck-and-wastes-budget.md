# S-2226 · The Agent Failure Handling Stack — When Your Agent Gets Stuck and Keeps Spending

Your agent runs for 47 iterations, burning $14 in tokens, produces garbage, and never tells you why. The loop never terminated — the user had to kill it. You've heard "add a max_iterations cap" but that's the wrong fix. It's too blunt: it stops agents that are converging slowly and still wastes budget on agents that are stuck.

## Forces

- **Fixed iteration caps are wrong in both directions.** Stop too early and you clip loops still improving. Stop too late and you've already shipped a worse final output and blown the budget.
- **Not all errors are equal.** A timeout deserves a retry. A malformed input will never parse. A hallucinated tool parameter needs a different recovery path entirely. Treating every error the same is how a small fault cascades.
- **Activity ≠ progress.** A loop that keeps calling APIs looks "active" — but it might be oscillating, not improving. Monitoring call counts misses whether the agent is actually converging.
- **Agents amplify failure.** One bad tool call can steer the agent into a dead-end trajectory from which every subsequent step is wasted. There's no natural backstop.
- **LLM unpredictability breaks traditional error handling.** Deterministic code can catch exceptions and branch cleanly. An LLM that "almost got it right" might silently produce a subtly wrong answer that passes downstream checks.

## The Move

Build a layered failure handling system around the agent loop — detection, classification, bounded recovery, and escalation — not just a max-iteration wall.

**1. Classify errors before reacting.** Separate transient failures (timeouts, rate limits) from permanent failures (bad input, auth revocation) from LLM failures (hallucinated parameters, parse errors). Route each to its appropriate response. Retry the timeout, reject the malformed input, re-prompt or escalate the hallucination.

**2. Use a circuit breaker on tool calls.** After N consecutive failures on the same tool, open the circuit — refuse further calls to that tool for a cooldown window. This stops the agent from hammering a degraded external API. SynapseKit ships this as a built-in primitive; LangChain's similar. Without it, a single failing endpoint can generate 47 compounding failure calls in production.

**3. Track loop convergence, not just iteration count.** Instead of `max_iterations=N`, measure whether the loop is actually improving. LoopGain (a 2026 open-source tool) tracks the loop gain ratio (current error ÷ previous error): if the ratio stays ≥1 across N steps, the loop has stalled and should terminate — regardless of iteration count. This lets slow-converging legitimate work continue while stopping stuck loops early.

**4. Climb a bounded recovery ladder.** Once stuck: (1) nudge — feed the agent a hint about the failure and let it self-correct; (2) replan — give the agent the original goal and ask it to replan from scratch; (3) reset — return the agent to its last known good state (state must be persisted); (4) escalate — human-in-the-loop. Each rung costs more (tokens, latency, human time), so cheap fixes are attempted first.

**5. Make state checkpointed and resumable.** The agent should write its progress to durable storage at each step. On failure, it resumes from the last good state — not from scratch. This makes step 4's "reset" actually cheap. This is the core insight of durable execution systems (e.g., Restate's durable coding agent patterns): the agent loop becomes fault-tolerant at the process level.

**6. Add a confidence/provenance gate on tool calls.** Before executing a tool call, validate that the parameters the agent generated actually exist in the available schema. At Modelia.ai, the candidate evaluation agent hallucinated tool parameters and wasted 3x its allocated budget before this was caught. Parameter validation is cheap; the alternative is cascading downstream errors.

## Evidence

- **GitHub / 12-factor-agents:** Dex Horthy (HumanLayer) interviewed 100+ founders building production agents and found that the dominant pattern among teams who crossed the 70-80% quality wall was treating the agent loop — not the individual step — as the unit of correctness. Their guide (25k+ stars, April 2025) frames failure handling as a first-class engineering discipline: circuit breakers, idempotency, graceful degradation, and human escalation are listed as explicit factors. — [github.com/humanlayer/12-factor-agents](https://github.com/humanlayer/12-factor-agents)

- **Blog post / Programa.space:** "Autonomous Agent Failure Modes and Recovery" (Feb 2026) documents five production failure modes — hallucinations acting, auth failures, action loops, state drift, cascading external outages — and maps each to a recovery pattern: sandbox + dry-run, capability-based permissions, circuit breakers, retry + idempotency, human escalation. Cites Anthropic's Cowork and Alibaba's Qwen as real-world systems now in non-technical users' hands, raising the stakes. — [programa.space/autonomous-agent-failure-modes-and-recovery-engineering-patt](https://programa.space/autonomous-agent-failure-modes-and-recovery-engineering-patt)

- **Blog post / Harsh Rastogi (Modelia.ai, Asynq.ai):** "Agentic AI in Production: Error Recovery, Observability, and Scaling" (March 2026) describes a candidate evaluation agent at Asynq.ai that hallucinated tool parameters, got stuck in loops, and cost 3x budget in production. The fix: parameter schema validation at the tool-call gate. Also describes an image generation agent at Modelia.ai that approved obviously flawed outputs because it optimized for workflow completion. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **GitHub / LoopGain:** A 2026 open-source tool that replaces `max_iterations=N` with control-theory-based loop termination. Tracks error convergence across iterations and terminates when the loop gain ratio ≥1 across N steps. Author: Dave (fitz288), published on HN mid-2025. — [github.com/loopgain-ai](https://github.com/loopgain-ai)

## Gotchas

- **`max_iterations` is a budget guard, not a failure handler.** It stops the loop but doesn't tell you *why* it stopped or recover from the failure. You still have garbage output and zero diagnostic signal.
- **Idempotency is harder than it looks.** If your agent calls a payment API on retry, you need to know whether the first call succeeded before retrying. Without idempotency keys, retries can double-charge users. This is not an agent problem — it's a distributed systems problem that agents now inherit.
- **Classifying errors requires a taxonomy your team owns.** The categories (transient, permanent, LLM) are a starting point, but your specific agent will have failure modes unique to your tools. Build the taxonomy from production incidents, not from theory.
- **Recovery still loses non-checkpointed progress.** If the agent crashes at step 9 and you only checkpointed at step 5, steps 6-9 are gone. Checkpoint granularity is a trade-off between storage cost and recovery cost.
- **Human escalation UX matters.** If your "human-in-the-loop" is just an email notification, nobody checks it until Monday. Escalation needs a low-latency review queue (sub-30-second decisions per item) to be effective in time-sensitive agent tasks.
