# S-2260 · The Agent Failure Recovery Stack — When Your Agent Keeps Going But Is Wrong

Your agent returned a confident answer in 47 seconds. No error. No crash log. HTTP 200. The answer is wrong — built on a hallucinated tool parameter that poisoned everything downstream. Your dashboard shows green. Your users see garbage. Agents almost never fail the way normal services fail. They keep going, fluently, sometimes for dozens more steps, while the tower of wrong conclusions grows taller. The loop is the unit of correctness — not the step.

## Forces

- **Agents fail "up."** A single corrupted tool response poisons the next reasoning step, which poisons the next. By step 12, the agent is confidently wrong on structurally correct output. The trace looks clean. The stack trace is missing.
- **Activity ≠ progress.** Loop detection that watches API calls, file edits, or log volume will fire on both stuck loops AND slow-but-converging legitimate work. You need a progress metric that only increments on real outcomes — failing tests resolved, sources gathered, checklist items completed.
- **Automated recovery often makes things worse.** Analysis of 220 production loops found that half of automated recovery responses either did nothing or degraded the situation. Every recovery rung is a hypothesis that needs measurement.
- **Silent failures return HTTP 200.** The four dominant silent failure classes — hallucinated tool calls, tools that succeed with wrong data, quality decay after model changes, and retries that resolve onto a weaker path — all look like success from the infrastructure's perspective. You have to read the content.
- **Recovery ladders go both directions.** A nudge might unstick a repeater. A replan might unstick a wanderer. But nudge makes a circular loop worse, and reset destroys state that a nudge would have recovered.

## The Move

Build a layered failure recovery system: **detect → classify → climb → verify**. Detection identifies that something is wrong. Classification determines the stuck shape. The recovery ladder applies the minimum intervention that is likely to work. Verification confirms the intervention helped — and reverses if it didn't.

### Layer 1: The Three Stuck Shapes

| Shape | What it looks like | Why it happens |
|---|---|---|
| **Repeater** | Same tool, same parameters, same failure, again | Model doubles down on the confident-but-wrong approach |
| **Wanderer** | Different actions, same goal, no progress | Context is insufficient; agent explores but doesn't ground |
| **Circular** | Actions repeat in a sequence | No short-term memory of what was already tried |

Classify before recovering — the fix that breaks a repeater (switch strategy) may make a wanderer worse (it needed context, not strategy).

### Layer 2: The Recovery Ladder (climb minimum to maximum)

1. **Nudge** — Inject a diagnostic message: "You have called `edit_file` on `auth.py` 5 times without passing tests. The last 3 failures named `JWTValidationError`. Consider a different approach." Fires on repeaters. Does not destroy state.
2. **Replan** — Abandon the current plan, generate a new one from scratch with the same goal. Costly in tokens but may escape a wanderer dead-end. Treat as hypothesis — measure whether the new plan behaves differently.
3. **Escalate** — Route to a higher-capability model or a human supervisor. Expensive. Reserve for cases where nudge and replan have both failed.
4. **Reset** — Clear short-term context, reload from the last known-good checkpoint. Destructive — loses intermediate state. Last resort for circular loops where state has become noise.
5. **Human handoff** — Stop the agent, surface the failure, and await human instruction. Correctness over autonomy for high-stakes or ambiguous cases.

### Layer 3: Circuit Breakers (non-negotiable guardrails)

Unlike kill switches (manual, reactive), circuit breakers are automated thresholds that terminate execution before damage compounds:

| Breaker type | Threshold example | Action |
|---|---|---|
| **Cost velocity** | >$X in last 10 minutes | Pause, alert, require acknowledgment |
| **Iteration count** | >N consecutive tool failures | Trigger recovery ladder |
| **Consecutive failures** | >M same-tool failures in a row | Open circuit, escalate |
| **Scope violation** | Agent attempts action outside its defined scope | Hard abort + alert |
| **Context saturation** | >95% context window used | Flush oldest non-essential turns, continue |

> "A developer woke up to a $437 API bill after their nightly document-summarizing agent entered a retry loop at 11 PM and ran until 7 AM. The fix took 20 minutes. The loop ran for 8 hours. No alert fired. Nothing stopped it." — Waxell.ai, 2026

Budget controls (per-tool spend caps) stop damage after the fact. Pre-authorization — reserve → commit per action — detects anomalous patterns before burn accumulates.

### Layer 4: Graceful Degradation

When full capability can't be maintained, degrade in tiers rather than hard-failing:

1. **Retry with backoff** — Same model, exponential backoff, jitter. For transient API errors.
2. **Fallback model** — Route to smaller/cheaper model at reduced quality. Acceptable for non-critical paths.
3. **Reduced scope** — Complete the subset of the task that the degraded system can handle reliably. Surface what's skipped.
4. **Replan** — Generate a new plan under the degraded constraints.
5. **Fail clearly** — Return "unable to complete" with a structured explanation. For safety-critical or high-stakes actions where degraded quality is worse than no answer.

Not appropriate for: medical diagnosis, financial trading, legal document review. Define explicitly which capabilities can degrade and which must either work or fail clean.

### Layer 5: Checkpointing (for long-running agents)

Long-running agents need durable state recovery beyond the session:

- Serialize: agent memory, conversation history, current task queue, intermediate results, external API responses
- Store at natural task boundaries (after each subtask completes, not mid-step)
- Use structured format (Protocol Buffers for efficiency, JSON for portability)
- Resume from checkpoint on crash — avoids restarting a 58-minute task from scratch

## Evidence

- **Research synthesis:** 42% of multi-agent failures are specification failures (wrong goal definition), 37% coordination failures (agents misaligned), 21% verification failures (no confirmation step) — Galileo MAST taxonomy, 2025, grounded theory on 200+ production traces — https://arize.com/blog/common-ai-agent-failures
- **Loop dataset:** Analysis of 220 production loops found ~50% of automated recovery responses either had no effect or made things worse — Boucle, 2026 — https://dev.to/boucle2026/how-to-tell-if-your-ai-agent-is-stuck-with-real-data-from-220-loops-4d4h
- **Silent failure case study:** Anthropic Sonnet 4 routing misconfiguration ran undetected for weeks, affecting 0.8%–16% of requests at peak, because latency and error rates didn't move — Anthropic postmortem, August 2025 — https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
- **Cost incident:** Per-tool AI budget controls built after a developer lost $200 to an agent loop running overnight — HN Show, lava.so, 2025 — https://news.ycombinator.com/item?id=46991656
- **Architecture patterns:** Supervisor trees (parent agent monitors child agents, restarts failed ones), idempotency layers (make tool calls safe to retry), circuit breaker libraries with per-tool breakers and gradual HALTF_OPEN recovery — reaatech/circuit-breaker-agents, 2026 — https://github.com/reaatech/circuit-breaker-agents
- **Behavioral taxonomy:** "Persistent" models (retry same action indefinitely on CAPTCHA) vs "pragmatic" models (recognize unsolvable and stop) — Magnus Müller, CEO Browser Use, April 2026 — https://www.twosetai.com/insights/when-llm-agents-get-stuck-in-loops/
- **Production failure field analysis:** Context window overload (dump-truck indexing without structure), tool parameter hallucination (fabricated IDs, wrong formats), self-contradiction (confidence without consistency), budget overruns, and context poisoning — Harsh Rastogi, Modelia.ai/Asynq.ai, March 2026 — https://harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns

## Gotchas

- **Tool parameter validation is not optional.** Agents call the right tool with the wrong parameters — fabricated IDs, invalid enum values, wrong date formats. Validate ALL tool inputs against the actual schema before executing, not after.
- **Retry-without-change is a loop.** A retry that re-runs the identical action with identical parameters is not recovery — it is repetition. Each retry rung must change something: parameters, strategy, model, or context.
- **Checkpoint mid-step, not mid-thought.** Saving a checkpoint in the middle of a multi-step reasoning chain produces a corrupt state. Save at task boundaries only.
- **Graceful degradation requires explicit allowlisting.** If you haven't defined which capabilities can degrade and which can't, the agent will degrade unpredictably — including in ways that create risk rather than reduce it.
- **Activity metrics are liars in loops.** API call count, log volume, and token usage all increase during stuck loops. They cannot distinguish stuck from productive. Define a task-specific progress metric that only rises on real outcomes.
