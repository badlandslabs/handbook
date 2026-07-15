# S-1134 · The Escalation Ladder Stack — When Your Agent Gets Stuck But Nobody Knows What to Do

An agent loops for 35 minutes, makes thousands of identical tool calls, and runs up a $437 API bill — while returning no error and exiting with status 0. Your first instinct is to add a kill switch. Your second problem is that the kill switch requires a human to notice. The escalation ladder gives stuck agents a graduated recovery playbook: nudge first, re-plan second, rewind third, escalate last.

## Forces

- **Agents fail silently.** Unlike a microservice that crashes and logs a stack trace, a stuck agent often returns HTTP 200 with subtly wrong output. No exception fires. No threshold trips. Nothing stops it.
- **Cheap fixes don't generalize.** The recovery that breaks a repeating loop — same action, same failure — will do nothing for a wandering agent that's drifting further from the goal. But routing everything to a human supervisor burns attention on problems a single prompt nudge would have solved.
- **Activity proxies lie.** Counting API calls, file edits, or log lines as "progress" rises during stuck loops too. An agent that calls the same tool 40 times in a row generates plenty of activity while making zero progress. You need a metric that only increases when real work is done: tests resolved, unique sources gathered, checklist items completed.
- **Recovery must be bounded.** A recovery action that takes longer than the original task defeats the purpose. Escalation ladders that include infinite retry or unbounded recursion just create new failure modes.

## The Move

Build a three-layer defense: **detect → classify → escalate**. Detection identifies when the agent is stuck (not slow). Classification determines which of three stuck shapes you're dealing with. Escalation runs a bounded ladder until the agent escapes or a human takes over.

### Layer 1 — Stuck Detection (Not Slow)

- Define a **progress metric** that only increases on real work done. Examples: failing tests remaining (should decrease), unique documents retrieved (should increase), subtasks on a checklist completed. Activity proxies like tool call counts are unreliable — stuck agents generate plenty of activity.
- Fire on flat progress across N consecutive heartbeats. Tune N against workload: a tight refactor on one file needs N=3–5; a research task spanning 20 sources needs N=8–12. Too tight and you interrupt legitimate slow work. Too loose and the agent has already burned budget.
- Instrument at step granularity. Every LLM call, tool invocation, and state transition should be logged with a timestamp and step type. This makes post-mortems tractable and distinguishes "slow but converging" from "stuck."

### Layer 2 — Classify the Stuck Shape

Once detection fires, classify before escalating. Three shapes, three different fixes:

| Shape | What it's doing | Detection signal | First fix |
|---|---|---|---|
| **Repeater** | Same action, same failure, repeating | Identical tool call N times | Inject a context nudge: "last N attempts returned the same result; try a different approach" |
| **Attractor** | Caught in a local basin — converging to wrong goal | Progress flat but behavior varied | Re-plan: re-inject the original task spec and ask the agent to verify the current goal against it |
| **Wanderer** | Drifting — each step farther from the task | Progress flat + task-similarity score dropping | Roll back to last checkpoint, then re-plan |

Activity variation alone cannot distinguish attractor from wanderer. You need a signal tied to goal alignment: semantic similarity between the agent's current state and the task specification, or a lightweight verifier node that scores partial completion.

### Layer 3 — The Bounded Escalation Ladder

Run escalation in order. Each rung has a fixed budget; if it exhausts the budget without progress, move up. Never skip rungs — each rung is cheaper than the next.

1. **Nudge** (budget: 1–2 LLM calls) — Inject a recovery prompt: summarize what's been tried, note that progress has stalled, and ask for a different approach. Often resolves repeaters without any structural change.
2. **Re-plan** (budget: 1 full re-plan call) — Re-inject the original task spec and goal into context. Strip any intermediate context that might be anchoring the agent to a wrong direction. Ask the agent to verify its current state against the goal before continuing.
3. **Rollback** (budget: 1 checkpoint restore) — Restore the last known-good checkpoint. In LangGraph this is a 3-line operation: `config["configurable"]["checkpoint_id"] = previous_checkpoint_id`. Use Postgres for production checkpoint storage, Redis for low-latency dev environments.
4. **Human handoff** (budget: manual) — Surface the full trace with a structured summary: what was tried, what went wrong, what the progress metric shows. Include a "resume from" checkpoint ID so the human can resume rather than restart. Do not log-only this step — it must block further autonomous execution until resolved.

### Budget Guards (Run Alongside Escalation)

Never let the escalation ladder itself run unbounded. Guard it with:

- **Max iterations cap** — frameworks like LangGraph, AutoGen, and CrewAI all support `max_iterations`. Set it to 2–3x your expected step count for the task. A conservative estimate is better than no ceiling.
- **Token budget per trace** — Reject or truncate requests exceeding a per-run ceiling. LiteLLM supports `max_budget_per_session` at the agent params level.
- **Spend anomaly alerts** — Flag when per-hour spend deviates more than 2σ from baseline. A loop that slips past iteration limits will show up as a spend spike before it becomes catastrophic.

## Evidence

- **Engineering blog (Zylos Research, 2026):** Multi-agent failure distribution — 42% specification failures, 37% coordination breakdowns, 21% verification gaps. Notes agents fail without raising exceptions: "An agent may silently loop for 35 minutes, spawn redundant subprocesses that contend for shared resources, accumulate context until the model halts, or take an irreversible action before a human can intervene." — [Zylos Research](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Post-mortem / DEV Community (Waxell, 2026):** Real incident — nightly document-summarizing agent entered a retry loop at 11 PM. Woke up to a $437 API bill at 7 AM. The fix took 20 minutes. The loop ran for 8 hours. No alert fired. Introduces the circuit breaker vs. kill switch distinction: "The problem isn't the absence of a kill switch. It's the absence of a circuit breaker." — [DEV Community](https://dev.to/waxell/ai-agent-circuit-breakers-the-reliability-pattern-production-teams-are-missing-5bpg)
- **Pattern catalog (AgentPatterns.ai):** Recovery ladder — classifies three stuck shapes (repeater, attractor, wanderer) and maps each to a first-response recovery strategy. Key insight: "The cheap fix that breaks a repeater fails on a wanderer, and the heaviest move — human handoff — is a poor first choice when a nudge would have sufficed." — [AgentPatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/)
- **Engineering post (Harshrastogi, Modelia.ai / Asynq.ai, 2026):** Tool parameter hallucination, loop costs, and workflow-completion-vs-quality failures observed in production. Notes: "A candidate evaluation agent hallucinated tool parameters, got stuck in loops, contradicted its own reasoning, and cost 3x budget." — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Framework docs (LangGraph / DeepWiki):** `RetryPolicy` type with configurable backoff, jitter, and per-node attachment. Checkpoint-based rollback: restore execution to any prior checkpoint without dropping user context. Postgres recommended for production checkpointer storage. — [DeepWiki / LangGraph](https://deepwiki.com/langchain-ai/langgraph/3.8-error-handling-and-retry-policies)

## Gotchas

- **Setting max_iterations too low kills legitimate long tasks.** A research agent that needs 30 steps for a complex query will get truncated mid-work. Calibrate against observed step counts, not intuition.
- **Checkpointing adds latency on every step.** For latency-sensitive agents, checkpoint every N steps rather than every step. The tradeoff: you lose resolution on rollback. For high-stakes actions (database writes, external API calls), checkpoint immediately before.
- **Recovery prompts can backfire.** A nudge that re-injects too much context can re-anchor the agent on the same wrong path. Keep recovery prompts tight and goal-focused, not history-summary.
- **Circuit breakers protect against downstream failures, not agent logic failures.** A circuit breaker that trips when an external API returns 500s is valuable, but it won't stop an agent from looping on a tool that returns 200 with garbage data. You need both: downstream circuit breakers and behavioral loop detection.
- **Human handoff that only logs is not a handoff.** If a human must review and act, the agent must block until the human responds. A logged handoff with no blocking semantics is a post-hoc incident report, not a safety net.
