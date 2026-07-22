# S-1468 · The Silent Burn Stack — When Your Agent Fails Without Failing

Your agent is running. It responds to every tool call. It logs its steps. There is no crash, no error, no exception. It simply continues — loop after loop — burning $50,000 over a long weekend while you sleep. Agent failure does not look like a crash. It looks like correct behavior that never stops.

## Forces

- **Agents fail by doing the right thing forever.** Unlike traditional software that crashes or returns errors, a stuck agent keeps producing valid outputs that compound into disaster. The loop is syntactically correct and semantically broken — which is harder to detect than a traceback.
- **Cost multiplies silently through multi-agent pipelines.** A single chatbot call costs ~$0.04. A multi-agent workflow with tool calls, memory, and orchestration multiplies that by 30–70x. A 5-hour Claude Code recursion loop burned $16,000–$50,000. An 11-day four-agent LangChain pipeline ran up $47,000. Nobody noticed until the invoice arrived.
- **Activity is not progress.** Tool call counts, log volume, and API request counts all increase during stuck loops. These signals look like productive work. Only a progress metric — whether the task is actually converging — distinguishes a stuck agent from a slow-but-correct one.
- **Failure detection and failure recovery are separate disciplines.** Firing recovery on slow legitimate work is as dangerous as not firing it on a stuck loop. A nudge fixes a repeater; it does nothing for a wanderer; a hard reset is the right answer for neither.

## The move

**A two-layer failure containment system: hard circuit breakers plus a bounded recovery ladder.**

### Layer 1 — Hard Circuit Breakers (non-negotiable)

- **Step cap:** Set `MAX_STEPS = 12` as a hard stop, not a soft warning. Document and escalate when hit — do not silently continue.
- **Token budget per trace:** Each task execution gets a defined token ceiling. Exhaust it → return partial result, stop billing.
- **Cost alert thresholds:** Fire at 50%, 80%, 100% of projected budget. A pager is better than a $47,000 invoice.
- **Runtime-linked cost limits:** Bind execution state to token/cost limits at the runtime level so a runaway loop cannot exceed the ceiling regardless of what the agent decides to do next.

### Layer 2 — Bounded Recovery Ladder (climb one rung at a time)

After detection fires, recovery should not immediately escalate to a human. Climb:

1. **Nudge** — inject a prompt that re-orients the agent ("you appear to be repeating steps. Check your history and confirm the last completed step.")
2. **Replan** — give the agent its own execution history and ask it to diagnose whether it is converging or stuck.
3. **Escalate** — switch to a supervisor agent or higher-capability model for one reasoning pass.
4. **Reset** — truncate context and reinitialize from the last verified checkpoint. The agent restarts with a clean state.
5. **Human handoff** — surface the execution trace with a summary of what failed. Stop the loop. Do not attempt further automated recovery.

### Classify Errors Before Retrying

Distinguish retryable from fatal errors *before* entering the retry loop:

- **Retryable:** 429 rate limit, 503 service unavailable, timeout, network error, malformed JSON from a tool.
- **Fatal:** 401 unauthorized, 403 forbidden, invalid API key, schema validation failure on LLM output. Retrying a fatal error burns budget on a doomed request.

### Fallback Chains (not just model cascades)

Fallback is not only "use a cheaper model." Define fallback chains across multiple dimensions:

- **Model:** GPT-4o → GPT-4o-mini → Claude Haiku → local model.
- **Strategy:** Full reasoning → simplified prompt → retrieval-only (no generation).
- **Scope:** Full task → partial result with known gaps → graceful failure with explanation.

### State Checkpointing

Every N steps, write a durable checkpoint: tool call history, LLM state, partial outputs. If the agent crashes, exceeds its step cap, or is manually reset, restart from the last checkpoint rather than the beginning. This also enables meaningful human review of what went wrong.

## Evidence

- **HN Commenter on the Anthropic "Building Effective Agents" post (543 points):** Teams consistently underestimated how much safety engineering matters compared to prompt engineering. The most reliable production agents had hard caps on steps, explicit done conditions, and cost circuit breakers — none of which are in the default agent framework templates. — [Hacker News](https://news.ycombinator.com/item?id=44301809)
- **Reddit r/AI_Agents (6 months ago):** Practitioner reported the core problem: "most agent frameworks give you great tools for acting, but very few tools for restraint." Experimenting with budget-aware runtimes that link execution state to token/cost limits. — [Reddit r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1qnavt9/the_infinite_loop_fear_is_real_how_are_you/)
- **FreeCodeCamp engineering tutorial (June 2026):** Documented two real incidents: a Claude Code recursion loop burning $16,000–$50,000 in 5 hours (July 2025), and an 11-day four-agent LangChain pipeline costing $47,000. Root cause in both cases: no exit condition defined, not a crash or error. — [FreeCodeCamp](https://www.freecodecamp.org/news/how-to-build-a-production-safe-agent-loop-from-exit-conditions-to-audit-trails)
- **agentpatterns-ai (GitHub, reviewed June 2026):** Stuck-loop recovery pattern documented with the key principle: recovery should NOT fire on slow legitimate work. Activity proxies (API call counts) cannot distinguish stuck from slow — only a progress metric that rises during convergence can. — [agentpatterns-ai](https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md)
- **vectara/awesome-agent-failures (GitHub, Aug 2025):** Community-curated failure mode catalog covering tool hallucination, response hallucination, loop patterns, and cascading failures. Documents that ~42% of multi-agent failures are specification failures, ~37% coordination breakdowns, ~21% verification gaps. — [GitHub](https://github.com/vectara/awesome-agent-failures)

## Gotchas

- **Soft limits don't protect you.** Setting `MAX_STEPS = 100` with a log warning is not a circuit breaker — it is a wider cage. Hard caps must actually stop execution, not alert about it.
- **Retrying fatal errors wastes budget and can cause harm.** A 401 should never enter a retry loop. Build the error classification before the retry logic, not after.
- **Progress metrics beat activity metrics.** API call counts and log lines increase during loops. If you measure "is the agent busy" instead of "is the agent converging," you will fire recovery on the wrong events.
- **Human handoff is the last rung, not the first.** Practitioners default to "send it to a human" as a first response to failure, but the wrong fix wastes human time on recoverable loops. Escalation ladders should start with the cheapest fix and only reach humans when automated recovery is exhausted.
- **Checkpointing only helps if you actually use the checkpoint.** Many teams implement state persistence but never build the "resume from checkpoint" logic — the state survives a crash but nobody can actually use it to recover.
