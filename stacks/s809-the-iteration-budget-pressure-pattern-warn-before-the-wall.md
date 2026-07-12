# S-809 · The Iteration Budget Pressure Pattern: Warn Before the Wall

An agent that hits its iteration ceiling and gets cut off mid-thought delivers nothing. An agent that gets warned at 70% and 90% of its budget wraps up, saves its progress, and returns a partial result worth keeping. The difference is whether your agentic pipeline produces value or silence when it runs long.

## Forces

- **The wall vs. the ramp** — a hard `max_iterations` cut-off terminates the agent without warning; it produces no final response and loses all context. The agent has no opportunity to self-correct, consolidate, or graceful-exit.
- **Agents have no global view of their own spend** — an agent that has cost $80 and accomplished nothing has no awareness of that. That global view must be injected from outside the reasoning loop.
- **Partial results dominate in production** — most agentic tasks are bounded by time, cost, or user attention. A 70% complete answer delivered cleanly beats a 100% complete answer that never arrived because the agent loop never terminated.
- **Abrupt termination is the silent failure** — unlike tool errors or API rate limits (which surface in logs), an iteration wall produces a clean, quiet exit with no error code. You only notice it when the expected output doesn't appear.

## The move

The pattern: inject escalating advisory messages into the agent's context before hard limits are reached. The messages don't stop execution — they change the agent's behavior by giving it time to transition from exploration to consolidation.

**Two-tier threshold system** (from Hermes Agent issue #414, inspired by Utah/Inngest):

- **Caution at 70%** — inject: `"[BUDGET: Iteration {N}/{max}. You have {remaining} iterations left. Start consolidating your work and prepare to provide a final response.]"` — sent as ephemeral context, not persisted to session history.
- **Warning at 90%** — inject: `"[BUDGET: Iteration {N}/{max}. You MUST provide your final response NOW. Do not make additional tool calls unless absolutely critical.]"` — forces the pivot from action to synthesis.

**Delivery mechanism**: inject into the API call's message array only (`api_messages` copy), never into persisted session history. This avoids polluting the conversation record and keeps the message invisible to downstream logging or memory systems.

**Why two tiers**: the 70% caution gives the agent time to shift strategy gradually — stop exploratory calls, focus on synthesis, save intermediate state. The 90% warning is the last call — no more tools, provide output now.

**The `_handle_max_iterations()` fallback** remains as the hard stop: one final tool-less API call asking the model to summarize everything it learned. Without budget pressure, this final call starts with zero consolidation context and produces a degraded summary. With pressure, the model has already been doing this work for the last 30% of its budget.

## Evidence

- **GitHub Issue:** Iteration Budget Pressure — Warn the LLM Before Max Iterations Hit — Hermes Agent issue #414, opened March 5, 2026, with a proposed two-tier implementation (caution at 70%, warning at 90%) and PR #54277 tracking the fix. Explicitly cites Utah (Inngest's agent harness) as the inspiration. — [github.com/NousResearch/hermes-agent/issues/414](https://github.com/NousResearch/hermes-agent/issues/414)
- **GitHub Repo:** Utah — Universally Triggered Agent Harness — an Inngest-powered durable agent implementing the think/act/observe loop with budget pressure as a core design principle. Every LLM call is an Inngest step with retry and cancellation support. — [github.com/inngest/utah](https://github.com/inngest/utah)
- **Case Study:** November 2025 multi-agent LangChain incident: two agents locked in recursive loop for 11 days, $47,000 in API charges, zero alerts fired. Root causes: no per-agent iteration cap, no runtime timeout, no anomaly detection. — [kognita.co/blog/ai-agent-runaway-cost-no-kill-switch](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **Architecture Analysis:** DEV Community post-mortem of the same incident, detailing the architectural failure: no orchestrator watching the full conversation, no shared memory between agents, no global state. — [dev.to/utibe_okodi](https://dev.to/utibe_okodi_339fb47a13ef5/the-ai-agent-that-cost-47000-while-everyone-thought-it-was-working-1lg6)
- **Pattern Analysis:** TeachYou Academy — "Agent Guardrails: Preventing Runaway Loops and Cost Overruns," July 2026. Names five failure modes driving runaway costs: tool loops, context explosion, no max_tokens, model confusion loops, plan deviation. Frames guardrails as "explicit, testable limits enforced in code rather than hoped for in a prompt." — [teachyou.ai/blog/agent-guardrails-runaway-loops](https://www.teachyou.ai/blog/agent-guardrails-runaway-loops)

## Gotchas

- **Ephemeral vs. persistent injection** — if caution/warning messages are written to session history, they accumulate and inflate context. Always inject into the API call's ephemeral message array, not `messages` or storage.
- **Budget pressure is advisory, not enforced** — the agent can ignore the caution and keep calling tools. The hard stop at 100% is the enforcement layer. Budget pressure improves output quality; it doesn't guarantee termination.
- **Model-specific calibration** — 70/90 thresholds are starting points. Models with longer reasoning traces (o-series, extended thinking) may need earlier caution thresholds because more of their budget is consumed by non-action steps.
- **Noisy at scale** — checking thresholds every API call adds latency. Profile before claiming it's negligible in high-throughput pipelines.
- **Dollar ceiling still needed** — iteration budget pressure doesn't prevent a $5 tool loop (the same tool called cheaply 500 times). Combine with per-session dollar ceilings ([F-88](../forward-deployed/f88-session-cost-ceiling.md)) for orthogonal coverage.
