# S-2247 · The Agent Failure Recovery Stack — When Your Agent Keeps Retrying the Same Broken Thing

When an agent loops silently for 35 minutes burning tokens, or cascades a single tool failure into a full pipeline collapse, or completes an irreversible action before anyone can intervene.

## Forces

- Agent failures are not software bugs — they produce confident, plausible, wrong output with no exception thrown
- A loop that only ends because a step limit fired was never designed to end; it just ran out of budget
- Reversible actions (reads, queries) and irreversible ones (deletes, writes, deploys) need fundamentally different guardrails, but agents treat all tool responses the same
- Detecting a stuck agent is easy; choosing the right recovery action is hard — the cheapest fix breaks repeaters but not wanderers, and vice versa
- Cost accumulation during failure is invisible until the bill arrives; a single retry loop can run $47,000 before a human notices

## The Move

Build a **failure recovery pipeline** with three layers: classify the action before it runs, detect failure mid-loop, and recover through a bounded escalation ladder.

**Pre-execution: Reversibility Classification**

Every tool call gets classified before execution, not reactively after failure:

| Tier | Examples | Policy |
|------|----------|--------|
| **Read-only** | Query DB, fetch URL, search vector store | Proceed freely |
| **Idempotent write** | Update record, send draft email | Proceed; log for audit |
| **Mutating** | Create resource, modify file, post to external API | Require human approval or reversibility confirmation |
| **Irreversible** | DROP TABLE, delete S3 bucket, rm -rf | Hard block + human approval gate |

The key insight: classify *actions*, not *tools*. The same `database.query` tool is read-only when selecting, irreversible when executing raw DDL.

**Mid-execution: Stuck-Loop Detection**

Detection must distinguish stuck from slow-but-converging. Use a **progress metric** (tests resolved, unique sources gathered, checklist items completed) — not an activity metric (API calls made, files touched). A progress metric can only increase when real work is done.

| State | Progress | Activity | Recovery? |
|-------|----------|----------|-----------|
| Stuck | Flat across N heartbeats | Continues | Yes |
| Converging slowly | Rising | Continues | No |

Two loop shapes: **repeater** (same action with same args) and **wanderer** (different actions cycling back to start). Treat differently.

**Recovery Ladder: Bounded Escalation**

When stuck detection fires, climb the ladder — don't jump to human handoff:

1. **Nudge** — inject a prompt signal ("your last 3 actions were all 'search' and didn't advance the goal. Try a different approach.")
2. **Replan** — call the agent's planner with the current state and ask it to produce a revised plan
3. **Escalate** — route to a human with full state dump (trajectory history, tool results, what was tried)
4. **Reset** — rollback to last checkpoint, clear context, restart from a known-good state
5. **Handoff** — transfer to a different agent class or fall back to a deterministic script

The ladder prevents two failure modes: over-escalating (every stuck event fires a human) and under-escalating (the agent keeps looping until budget dies).

**Cost and Cascade Guards**

- **Per-call cost cap**: fail fast on any single LLM call exceeding N cents
- **Per-run budget**: hard stop on total spend, not just step count
- **Cascade breaker**: if tool call N fails, do not call tools N+1, N+2 automatically — require explicit replan
- **Step limit as backstop only**, not the primary termination signal — a run that ends because the limit fired is a run whose ending was never specified

## Evidence

- **GitHub community doc:** Vectara's `awesome-agent-failures` repo (195 stars, Apache-2.0, created 2025-08-20) catalogs six structural failure modes — tool hallucination, response hallucination, goal misinterpretation, prompt injection, cascade contamination, and silent context poisoning — each with battle-tested mitigations. Documents that cascade failures account for 31% of production incidents in their survey sample. — [https://github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)

- **Production incident:** Two LangChain agents in a research pipeline entered an 11-day infinite conversation loop (one analyzing, one verifying) before a human noticed. Total bill: $47,000. No alert fired, no dashboard flagged it. Demonstrates that step limits alone do not catch loops — progress metrics do. — [https://www.paperclipped.de/en/blog/ai-agent-reversibility-checks](https://www.paperclipped.de/en/blog/ai-agent-reversibility-checks)

- **HN production audit:** An "Ask HN" thread on testing agents before production (harperlabs, ~4 months ago, 300+ points) surfaced five distinct failure modes teams encounter in staging: hallucination under unexpected inputs, edge case collapse (null values, Unicode names like O'Brien), prompt injection, silent context-window misbehavior, and cascade failures where tool failure propagates invisibly. The consensus: traditional software testing maps poorly to agent behavior. — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Step limits treat all loops as equal.** A repeater (same action) needs a different recovery than a wanderer (cycling through different actions). Ladder climb must be action-shape-aware, not step-count-aware.
- **Silent context exhaustion is the stealthiest failure.** When the context window fills, the model doesn't error — it just produces wrong output. Monitor token utilization per step, not just step count.
- **Reversibility classification must be pre-execution, not post-failure.** By the time a `DROP TABLE` fails, it's already destroyed data. The gate must be before the tool call, not after.
- **Retry without budget caps is a cost runaway.** Exponential backoff on an LLM endpoint that is down will accumulate significant spend before the circuit opens. Always cap total retry budget.
- **Cascade failure is the default behavior.** A tool returning empty results or an error code causes most agents to continue to the next tool as if nothing happened. Explicit cascade-breaking logic is required — it doesn't happen by default.
