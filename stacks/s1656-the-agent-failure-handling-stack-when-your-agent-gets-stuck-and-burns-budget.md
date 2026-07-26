# S-1656 · The Agent Failure-Handling Stack — When Your Agent Gets Stuck and Burns Budget

When an agent silently loops on the same tool, a transient error cascades into a $47,000 cloud bill, or a single bad API response drives destructive actions in production.

## Forces

- **Agents fail in shapes single-LLM calls don't.** Loops, runaway tool calls, infinite "let me try one more thing" — failure modes that don't exist for one-shot completions.
- **Observability is not enforcement.** Teams often have tracing and logs but no hard limits. The $47,000 LangChain loop had monitoring; it had no budget enforcement.
- **Errors传递给agent的信息决定能否自愈.** A bare HTTP status code gives an agent nothing to self-correct on. Full error context lets it pivot strategy.
- **The failure taxonomy is still being written.** Microsoft documented 17 failure mode categories after a year of red-teaming; teams are discovering new ones weekly in production.
- **Gartner predicts >40% of agentic AI projects cancelled by 2027** — not because models are insufficient, but because the systems around them aren't built to handle failure.

## The Move

Design the failure layer before the happy path. The following patterns are used in combination by teams running agents in production:

- **Hard step caps.** Stop after a fixed number of agent turns regardless of progress. Most practitioners use 10–15 steps. Beyond that, the probability of useful work drops sharply and token cost compounds. LangGraph, LangChain, and OpenAI's Agents SDK all expose this as `max_iterations` or equivalent. When hit, document state and escalate or return.
- **Loop detection beyond string matching.** Agents can loop without producing identical outputs — they vary slightly each turn. Tools like LoopBuster (2026, MIT, ~93 stars) use four detection strategies: exact repeat, fuzzy repeat, cycle detection, and output stagnation. A sliding window of recent `(tool_name, hash(tool_args))` pairs catches productive repetition (same tool, different args) separately from pathological repetition (identical calls).
- **Rich tool error responses.** The fewsats case study showed that surfacing complete HTTP error bodies — not just `raise_for_status()` exceptions — enabled agents to self-correct on API failures. A bare 429 gives the agent nothing actionable. `429: Rate limit exceeded. Retry after 230ms. Current usage: 847/1000 requests/minute` lets the agent back off intelligently. The rule: error responses should be self-contained and suggest a recovery path.
- **Exponential backoff with jitter for transient failures.** Timeout, rate limit, and network errors warrant retry: `1s → 2s → 4s → 8s → 16s` with ±20% jitter to avoid thundering herd. Cap total attempts at 3–5. OpenHelm reports this pattern alone improving reliability from ~87% to 99.2%.
- **Circuit breakers at the tool level.** After N consecutive failures calling an external service (e.g., Stripe, GitHub), stop calling it entirely for a cooldown window. This prevents cascading failures and stops agents from burning budget on a service that's down.
- **Budget enforcement, not budget alerts.** The November 2025 LangChain loop incident: four agents ran for 11 days, every call returned 200, nobody noticed until the $47,000 invoice. The team had monthly budget alerts that fired two days too late. Per-agent hard caps that terminate before the next API call are what actually prevents overruns. Budget alerts are tracking; budget enforcement is control.
- **State checkpointing for long-running sessions.** Agents that crash or restart mid-task need to resume from where they left off, not from the beginning. Persist intermediate state (current step, accumulated context, tool call history) to an external store (DB, file). The agent resumes by loading state before re-entering the loop.
- **Human-in-the-loop escalation tiers.** Not every failure needs human review — but high-risk actions always do. Four-tier risk model: (1) read-only → no gate, (2) write local → informational log, (3) write remote → approval checkpoint, (4) destructive → mandatory human sign-off before execution. The key is async-first design so agents can pause and wait without blocking infrastructure.
- **Fallback chains for model and approach failures.** When the primary model returns consistently bad outputs, fall back to a smaller/faster/cheaper model for the remaining steps. Some teams fall back from Claude Opus to Haiku mid-session after hitting a quality threshold, rather than aborting entirely.

## Evidence

- **Incident report:** $47,000 LangChain agent loop — four agents running for 11 days (264 hours) in November 2025, ping-ponging between an Analyzer and Verifier agent. Root cause: no per-agent budget caps, no termination enforcement. The public post-mortem explicitly notes "the team had observability. They did not have enforcement." — [DEV Community / Waxell](https://dev.to/waxell/the-47000-agent-loop-why-token-budget-alerts-arent-budget-enforcement-389i)
- **Case study:** Cursor agent deleted production database via Railway GraphQL API. Root cause: production API tokens given to an agent with write access, no environment separation, no destructive-action guardrails. The agent's "confession" was surfaced in the HN thread with the exact curl command used. — [Hacker News / ycombinator](https://news.ycombinator.com/item?id=47911524)
- **Production failure data:** OpenHelm benchmarks show retry + exponential backoff + circuit breaker pattern stack improving reliability from ~87% to 99.2% (14× fewer failures) in production agent deployments. — [OpenHelm Blog](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **Library:** LoopBuster — framework-agnostic anti-dead-loop toolkit with semantically-aware loop detection (exact, fuzzy, cycle, stagnation), state stasis guard, and budget ceiling. Zero hard dependencies, works with LangChain, LangGraph, AutoGen, CrewAI, LlamaIndex. Created May 2026. — [GitHub / liuchunwei732-cmyk](https://github.com/liuchunwei732-cmyk/loopbuster)
- **Enterprise taxonomy:** Microsoft AI Red Team published v2.0 of the Agentic AI Failure Taxonomy (June 2026) — 17 failure mode categories across 7 new categories discovered after a year of red-teaming deployed systems. Grounded in empirical evidence from real engagements, not predictions. — [Microsoft Security Blog](https://www.microsoft.com/en-us/security/blog/2026/06/04/updating-taxonomy-failure-modes-agentic-ai-systems-year-red-teaming-taught-us/)

## Gotchas

- **Hard step caps stop execution but don't fix the underlying cause.** An agent that hits `MAX_STEPS` and exits cleanly still produced no result. Step caps are a circuit breaker, not a solution — you still need to investigate why the agent couldn't converge.
- **Loop detection on string similarity alone produces false negatives.** Agents can generate semantically identical tool calls with different string representations. Fuzzy/semantic loop detection is necessary; exact match is insufficient.
- **Providing full error context is a SDK design decision, not a model decision.** If your HTTP SDK swallows error bodies with `raise_for_status()`, the model will never see them. Audit your SDKs before auditing your prompts.
- **Budget alerts are not budget enforcement.** If your "budget protection" fires after the spend happens, it is not protection — it is reporting. Hard caps must block before the next API call, not after the invoice arrives.
- **Silent failures are worse than loud ones.** An agent that fails silently (returns `null` or an empty response) is harder to debug than one that throws an exception. Design error responses to be observable.
- **Not all failures warrant the same recovery strategy.** Rate limits → retry. Auth errors → don't retry (fix credentials first). Destructive actions → escalate to human. Applying uniform retry logic across all error types causes unnecessary cost and can worsen cascading failures.
