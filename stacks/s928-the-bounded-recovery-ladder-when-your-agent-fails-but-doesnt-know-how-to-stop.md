# S-928 · The Bounded Recovery Ladder

When an agent hits a wall — a failed tool call, a loop, a wrong turn — it usually keeps going. The expensive failure mode isn't the crash; it's the agent that looks operational while burning tokens behind an HTTP 200. You need a recovery architecture that knows when to stop, when to retry, and when to hand off to a human.

## Forces

- **Loops are more expensive than crashes.** A crashed agent stops billing. A looping agent burns $10–50/hour until someone notices (SynapseAI, "AI Agent Infinite Loop," 2026). Unlike code, where an infinite loop is a logic error you can catch with a static linter, an agent's loop is probabilistic — same input, different output, so reproduction is hard.
- **86% of agent failures are recoverable, but most teams don't build recovery.** The Operator Collective (March 2026) found that 86% of agent failures are technically recoverable — yet Gartner predicts 40%+ of agentic projects will be cancelled by 2027, largely due to failure-handling gaps, not capability gaps.
- **Soft failures hide behind HTTP 200.** Augment Code (June 2026) identifies the core observability problem: agents return "200 OK" while producing semantically wrong output. Infrastructure looks healthy. The failure is in the reasoning path, which conventional APM doesn't see.
- **A single stuck loop destroys multi-agent chains.** A 3-agent chain with 90% per-step reliability only achieves ~73% reliability. Compound 10-agent chains, and reliability collapses. Escalation gates are mathematically required, not optional (Digital Applied, "Human-in-the-Loop Escalation," June 2026).

## The Move

**The bounded recovery ladder: separate detection from recovery, then climb a fixed escalation sequence until the agent escapes or a human takes over.**

The critical architectural insight from AgentPatterns.ai ("Stuck-Loop Recovery," 2026): detection and recovery must be separate. A recovery action that breaks a "repeater" (same action over and over) fails on a "wanderer" (making progress but slowly). Using the wrong recovery tier wastes time and burns budget.

### 1. Hard cap at the foundation

Never deploy without a **max-turns/step limit**. This is the single most important safeguard. Without it, an agent loop runs until rate limits or budget exhaustion. Every major framework supports it:

- **AutoGen:** `max_turns`, `max_consecutive_auto_reply` — use both as defense in depth (Learnixo, "Termination Conditions," May 2026)
- **OpenAI Agents SDK:** `max_turns` hook that injects `"You have N turns remaining. Provide a FINAL answer."` into the prompt (GitHub Issue #844, openai-agents-python)
- **LangGraph:** checkpoint-based state management lets you resume from before a failure

### 2. Loop detection — semantic, not syntactic

**Identical-argument deduplication is insufficient.** A looping agent won't call the same tool with identical arguments — it'll call the same tool with slightly different reasoning or parameters, evading a naive `seen_actions` set. The fix is **semantic similarity** on recent trajectory (AgentPatterns.ai):

- Track recent action outcomes, not just action signatures
- Compute similarity between current action context and the last N steps
- Flag when progress metric has been flat across N heartbeats while activity continues
- Key distinction: **stuck** = progress metric flat; **converging slowly** = progress metric rising

The SynapseAI loop taxonomy (2026) gives three root causes:

| Root cause | Symptom | Fix |
|---|---|---|
| Retry without backoff | Tool fails → immediate retry → infinite loop | Exponential backoff + circuit breaker |
| Undetected task completion | Task done, agent re-does it | Explicit success-condition check after each milestone |
| Dependency deadlock | Subtask A waits for B, B waits for A | Timeout + escalate to supervisor |

### 3. The recovery ladder — four tiers, in order

Once detection fires, climb this sequence (AgentPatterns.ai, Digital Applied):

**Tier 1 — Nudge:** Inject a hint into the next turn without resetting state. Example: `"You've called the same tool 3 times. Consider whether this is producing progress. If not, try a different approach."` This costs one API call and handles ~40% of loops.

**Tier 2 — Replan:** Provide a revised plan, stripping context of recent failed attempts. Use the agent's own reasoning to generate a new approach. This breaks pattern-lock without losing the original goal.

**Tier 3 — Reset to checkpoint:** Roll back to the last verified-good state (LangGraph checkpoints, Microsoft Agent Framework state snapshots). Do not let the agent continue from within a failed trajectory — the failure may have corrupted internal state.

**Tier 4 — Human handoff:** Queue the task for human review with full context (trajectory, error log, last checkpoint). This is the fallback, not the first move. A practitioner at lava.so (HN, 2025) lost $200 from a loop before building per-tool budget controls — escalation at the tool level could have caught it.

### 4. Error classification determines recovery path

Not all failures are equal. Classify before choosing recovery (Anthropic SDK discussion #1341, GitHub):

| Error type | Examples | Recovery |
|---|---|---|
| `transient` | Network hiccup, rate limit, brief API unavailability | Exponential backoff + retry (1s → 2s → 4s → 8s → escalate) |
| `budget` | Cost ceiling hit mid-task | Pause, notify orchestrator, await budget top-up |
| `capability` | Requested tool unavailable, model ceiling reached | Escalate to supervisor or human |
| `state_corruption` | Agent produced malformed output mid-stream | Reset to last checkpoint, replay from there |

### 5. Circuit breakers for cascading failures

When a downstream service (API, database, tool) is failing, retrying immediately creates cascading failure. Wrap external calls with circuit breakers (Operator Collective, 2026):

- **Open:** After N consecutive failures on a service, stop calling it entirely for a cooldown period
- **Half-open:** After cooldown, allow a single test call
- **Closed:** If test call succeeds, resume normal operation

This prevents a single bad API from holding up the entire reasoning loop, which is the most common cascading failure pattern.

### 6. Budget kill-switches

Per-tool budget limits are now a production necessity, not a nice-to-have. The lava.so founder lost $200 from a single agent loop by leaving it running unattended. Practical pattern: set per-tool spending caps, and when a tool has consumed its budget within a single session, block further calls to that tool for that session regardless of the agent's stated intent.

## Evidence

- **HN Ask HN:** Testing AI agents before production — 7 identified failure categories, including "agent gets stuck in retry loops without knowing when to stop" — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **Show HN:** Founder lost $200 from agent loop → built per-tool AI budget controls at lava.so — [https://news.ycombinator.com/item?id=46991656](https://news.ycombinator.com/item?id=46991656)
- **Blog post:** "The most expensive failure mode is the agent that looks operational while burning tokens." SynapseAI loop taxonomy and token cost table ($4.50–9/5min, $45–90/15min) — [https://ddaekeu3-cyber.github.io/synapse-ai/guide/loop-stuck-errors](https://ddaekeu3-cyber.github.io/synapse-ai/guide/loop-stuck-errors)
- **Company engineering:** Modelia.ai/Asynq.ai agent at scale — candidate evaluation agent hallucinated parameters, got stuck in loops, cost 3x budget before failure handling was added — [https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **GitHub Discussion:** Anthropic SDK production error recovery — error classification framework (transient/budget/capability/state_corruption) — [https://github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Blog post:** AgentPatterns.ai stuck-loop recovery — recovery ladder concept (nudge → replan → reset → handoff) — [https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **Company post:** Operator Collective — 86% of failures are recoverable, 40%+ Gartner cancellation prediction, 6 failure modes with recovery patterns — [https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Research blog:** Digital Applied — escalation math, 4 risk tiers, async-first escalation patterns, 88% of projects stall before production — [https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026](https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026)

## Gotchas

- **Do not use verbal confidence as an escalation trigger.** RLHF models show ~75% actual accuracy at 90% claimed confidence. An agent that says "I'm very confident" may be wrong. Use behavioral signals (progress metric flat, same action N times) over declared confidence.
- **Identical-argument deduplication misses most loops.** A sophisticated loop agent makes slightly different calls each time. Track outcome similarity, not just argument equality.
- **Checkpointing without tested restore is worthless.** Teams add LangGraph checkpointing but never verify the restore path works under failure. Test restore from checkpoint before deploying.
- **The cheapest recovery tier (nudge) should be tried first.** Don't escalate to human review for a loop that a single contextual hint could break. The ladder exists precisely to avoid over-escalation.
- **Context window thrash during long loops.** A looping agent accumulates context with each iteration, slowing down and increasing hallucination risk. A hard turn cap stops this from becoming a compounding problem.
