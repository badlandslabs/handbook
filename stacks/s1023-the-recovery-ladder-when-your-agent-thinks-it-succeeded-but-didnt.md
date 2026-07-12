# S-1023 · The Recovery Ladder: When Your Agent Thinks It Succeeded But Didn't

Your agent returns a clean HTTP 200. No exceptions in the logs. Three minutes later a user reports the ticket was sent to the wrong team, the refund was hallucinated, and the summary contradicts itself. The agent did not fail in any way your error handling caught — it failed in the only way that matters: confidently and completely. This is the semantic failure gap, and it is the hardest class of agent error to handle because the agent's own success signal lies.

## Forces

- **Traditional try/catch misses the real failures.** Hallucinations, semantic tool errors, and confident nonsense return HTTP 200. The failure is in the output, not in the execution path. Your error handling never fires.
- **Agents compound their own mistakes.** A bad intermediate result from step 3 propagates through steps 4–8. By step 8, the root cause is buried under six layers of confident wrong reasoning.
- **Not all loops are the same.** A "stuck" agent might be a **repeater** (same action, same error) or a **wanderer** (different actions, no progress). The cheap fix that breaks one is wasted on the other.
- **Recovery costs escalate.** Ten retry iterations × complex reasoning × a 128k-token context window = $50–$500 in wasted spend before anyone notices.
- **Human handoff is a last resort, not a first move.** Escalating everything defeats the purpose of autonomy, but escalating nothing leaves silent failures undetected.

## The Move

Build a **tiered recovery ladder** — a small, ordered set of interventions that escalate from cheap-and-likely to expensive-and-guaranteed. Each rung handles a different failure class. Fire the lowest rung first; only climb when the agent does not self-correct.

### Classify errors at the harness level before recovery starts

Not all failures belong in the same bucket:

| Error class | Signal | Recovery |
|---|---|---|
| `transient` | Rate limit, network hiccup, timeout | Exponential backoff + retry (base: 2s, cap: 60s, jitter ±25%) |
| `semantic` | LLM output fails JSON/schema validation | Retry with explicit format correction in system prompt |
| `capability` | Missing tool, schema mismatch | Escalate to parent agent or tool registry |
| `budget` | Cost or token ceiling hit | `budget-paused` state → operator decision |
| `fatal` | Unrecoverable state (DLQ-worthy) | Mark failed, return partial results + error receipt |

### Implement progress detection, not just activity detection

Activity proxies (API calls, file edits, token count) rise during stuck loops too. Distinguish stuck from slow-converging by tracking a **progress metric**: a scalar that rises when the agent moves closer to the goal (test pass count, search result quality score, delta from previous state). Flat progress across N heartbeats = stuck. Rising even slowly = working.

### The recovery ladder (fire lowest rung first)

1. **Nudge** — Pass a targeted hint back: "You have searched for 'refund policy' three times with no results. Try searching for 'return policy' or ask the user to clarify." No state reset, no cost.
2. **Replan** — Regenerate the next-step plan from the current state. If the plan diverges from execution (wanderer), a fresh plan often unsticks. If it matches execution (repeater), proceed to next rung.
3. **Reset context** — Truncate the conversation history to the last N coherent turns. Removes the garbage-in that causes garbage-to-worse-out. Preserve tool results, drop the reasoning chain.
4. **Reset state** — Roll back to the last checkpoint (LangGraph `checkpointer` or equivalent). Full state restore for mid-workflow recovery.
5. **Human handoff** — Escalate with a structured error receipt: what the agent tried, what failed, what partial work exists, what the user asked for. Never escalate empty-handed.

### Use a DLQ for unrecoverable agent tasks

Map SQS/GCP dead-letter queue semantics to the agent domain. A task that fails all recovery rungs goes to the DLQ with:

- Full execution trace (all tool calls, all LLM outputs)
- Error classification and recovery attempts made
- Partial results if any exist
- `human_action_required: true` flag

Do not re-enqueue failed tasks automatically. Unlike transient HTTP errors, an agent task that failed due to semantic drift will fail identically on retry without external intervention.

### Checkpoint before every external call

Save the agent's complete state — conversation history, tool results, intermediate outputs — to durable storage before every tool invocation. This makes workflows resumable from the last known-good state rather than from scratch. LangGraph's built-in `checkpointer` supports this; if rolling your own, persist to a DB row keyed by `task_id + step_count`.

## Evidence

- **PADISO blog (2026):** A Sydney logistics startup's booking subagent retried a "slot unavailable" API error **200 times in 8 minutes** — only stopped by the API rate limiter. Case study in the failure mode where standard iteration limits catch the symptom but not the root cause (tool error misinterpreted as retry-worthy). — [https://www.padiso.co/blog/subagent-failure-modes-loops-drift-recovery-patterns/](https://www.padiso.co/blog/subagent-failure-modes-loops-drift-recovery-patterns/)

- **DEV Community / Alan West (2026):** A ReAct-style customer support triage agent called `search_knowledge_base` **73 times in a single session**, burning **47,000 tokens** — no loop detection, no "already tried this" state. Root cause: the conversation history showed the agent ten failed searches; the model interpreted this as "search harder" rather than "the tool is returning no useful results." — [https://dev.to/alanwest/why-your-ai-agent-loops-forever-and-how-to-break-the-cycle-12ia](https://dev.to/alanwest/why-your-ai-agent-loops-forever-and-how-to-break-the-cycle-12ia)

- **AgentPatterns.ai — Stuck-Loop Recovery (2025):** Documents the three stuck loop shapes — repeater, wanderer, and spiral — and the recovery ladder with concrete nudge/replan/reset/handoff tactics. Emphasizes that activity proxies (tool calls, edits) fail as progress metrics because they rise during stuck loops too; the correct signal is a domain-specific progress metric. — [https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)

## Gotchas

- **Do not retry on semantic failures.** A hallucinated JSON response will hallucinate identically on retry unless the prompt changes. Classify `semantic` errors separately and route to `replan` or `reset context`, not `retry`.
- **Hard iteration limits catch symptoms, not patterns.** A limit of 10 stops runaway cost but tells you nothing about whether the agent was a repeater (fixable with better tool feedback) or a wanderer (fixable with a new plan). Log the failure class, not just the limit hit.
- **The DLQ is not a graveyard.** Teams that route failed agent tasks to a DLQ and never look at it have built a silent failure sink. The DLQ needs a review SLA (e.g., all items cleared within one business day) and aggregated analysis to identify systemic failure patterns before they become production incidents.
- **Checkpoint cost vs. recovery cost.** Saving state before every tool call adds latency and storage overhead. The right granularity is before every *external* call (API, DB, file system) — not before every LLM call. Internal reasoning steps are cheap to redo; external side effects are not.
