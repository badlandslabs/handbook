# S-995 · The Agent Failure Recovery Stack — When Your Agent Loops, Hangs, or Hammers Itself Against a Dead End

Your agent ran for 35 minutes last night. It generated 14,000 tokens. It accomplished nothing — a single failed tool call spiraled into a loop, each iteration more confident than the last that it was making progress. Your budget is gone. Your pipeline is broken. And you didn't know until morning.

This isn't a crash. Traditional software crashes and logs a stack trace. Agents fail *creatively*: they loop silently, spawn redundant subprocesses contending for resources, accumulate context until the model halts, or take irreversible actions before a human can intervene. You need a system that catches these failure modes before they cost you.

## Forces

- **Agents fail in ways that bypass your try/catch.** LLM outputs that return HTTP 200 but are semantically wrong, or tool calls that technically succeed but give the wrong result — these don't throw exceptions. Your error-handling vocabulary is too narrow.
- **Retries can make things worse.** A retry storm — where your agent hammers a rate-limited API while a second agent fails over to the same backup, which also rate-limits — can burn through your entire API budget doing nothing. Retry without a circuit breaker is not resilience; it's denial.
- **Context accumulation makes failures expensive.** The longer an agent runs, the more state it accumulates. A failure at step 12 of a 15-step pipeline that destroys all prior work is far costlier than a failure at step 2. Checkpoints are cheap; reprocessing is expensive.
- **Not all errors should retry.** A 401 (revoked API key) or a policy violation will never succeed on retry. Wasting tokens retrying the unretryable is a bug masquerading as reliability.
- **Irreversible actions need a safety gate.** An agent that deletes files, sends emails, or writes to a database cannot be recovered by a retry. These require a fundamentally different pattern: escalation before action, not retry after failure.

## The Move

Five layered patterns that together cover the agent failure surface:

- **Error taxonomy before retry logic.** Classify every error before deciding what to do with it:
  - *Transient* (429, 503, timeout, DNS) → retry with backoff
  - *Semantic* (malformed JSON, wrong schema, bad tool output) → re-prompt with corrective context, don't just retry the same call
  - *Resource* (token limit, context overflow, spending cap) → reduce payload, switch to a cheaper/faster model
  - *Fatal* (401/403, revoked keys, policy violations) → abort immediately, alert operator, do not retry
  This taxonomy prevents the most common mistake: retrying errors that will never succeed.

- **Exponential backoff with jitter.** For transient errors, the formula: `delay = min(base × 2^attempt + random(0, jitter), max_delay)`. The jitter is not optional — it prevents synchronized retry storms when multiple agents recover simultaneously. Set per-provider backoff parameters; a rate-limited OpenAI call and a rate-limited GitHub API call should have independent timers.

- **Circuit breakers per external dependency.** Track consecutive failures per tool or API. Three failures in a row → stop calling that provider for a cooldown window → probe once → if it succeeds, resume. The cooldown prevents hammering a struggling service and lets it recover. Staggered failover (add random delay before routing to backup) prevents the cascade where every agent fails over to the same backup simultaneously. A circuit breaker in OPEN state should queue tasks rather than drop them.

- **Checkpoint-and-resume at every pipeline stage.** Serialize agent state (tool results, conversation history, intermediate outputs) to durable storage at the end of each step. On failure, recover from the last checkpoint rather than restarting. This turns a 15-step pipeline failure from losing all 15 steps to losing only 1. Cost: storage and serialization logic. Benefit: eliminates catastrophic reprocessing.

- **Max-iteration guard with escalating response.** Set a hard iteration limit (10–20 is common for most agents; tune from your P95 observed steps). When the limit is hit:
  1. Log the full trajectory (every tool call, input, and output)
  2. Attempt one "diagnostic re-prompt" — feed the error into the context and ask the model to explain what went wrong
  3. If that also fails or loops, escalate: queue for human review with full context, or trigger a fallback to a simpler deterministic path

- **Escalation queue for irreversible actions.** Actions that delete, send, write, or spend money get a pre-action gate: confidence score below threshold → route to human review queue with full session context and SLA. Binary pass/fail signals from reviewers feed back into the evaluation dataset. This closes the loop between production failures and future improvement.

## Evidence

- **Primary research:** arXiv 2605.06737 "A Self-Healing Framework for Reliable LLM-Based Autonomous Agents" (Jeong & Shin, May 2026) proposes a three-component architecture: failure detection via execution pattern analysis, reliability assessment with quantitative scoring, and automated recovery through dynamic replanning. Validated against幻觉, execution errors, and inconsistent reasoning — three categories that bypass traditional exception handling. — [arXiv:2605.06737](https://arxiv.org/abs/2605.06737)

- **Primary production incident:** Get a Team engineering blog documents a real incident: "47 Slack alerts at 3am. Email gateway agent crashed during peak hours." Root cause: one unhandled API timeout with no retry logic, no graceful degradation, no self-recovery capability. Post-mortem identified five failure patterns that killed ~90% of production agents: API rate limits, unexpected input variations, network instability, context overflow, and silent semantic failures. — [Get a Team Blog: Why 90% of AI Agents Fail in Production](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it)

- **HN production discussion:** The "Hive" agent framework Show HN thread (107 points) surfaced a key insight from a practitioner with 4 years of production ERP automation: "The hardest mental shift was treating Exceptions as Observations. In a standard Python script, a FileNotFoundError is a crash. In Hive, we catch that stack trace, serialize it, and feed it back into the Context Window as a new prompt: 'I tried to read the file and failed with this error. Why? And what should I try instead?'" This "exceptions as observations" pattern — feeding errors back into the LLM context rather than crashing — is the architectural pivot that separates brittle agents from resilient ones. — [HN: Show HN — Agent framework that generates its own topology and evolves at runtime](https://news.ycombinator.com/item?id=46979781)

- **Supervisor/multi-agent pattern:** The "Orchestration Playbook" GitHub repo (p3nchan) documents circuit breaker implementation for multi-agent systems, specifically calling out the retry storm failure mode and the staggered failover prevention strategy. — [GitHub: orchestration-playbook/patterns/circuit-breaker.md](https://github.com/p3nchan/orchestration-playbook/blob/main/patterns/circuit-breaker.md)

- **Infinite loop case study:** LangChain agent practitioners report that ambiguous tool descriptions or missing stop conditions cause agents to call tools until hitting iteration limits, burning budgets with no output. Solution: `max_iterations=10` with `early_stopping_method='generate'`. One practitioner measured a 92% reduction in token spend after adding explicit stop conditions. — [Markaicode: Fix LangChain Agent Infinite Loop](https://markaicode.com/errors/ai-agent-loop-fix/)

- **Graceful degradation:** Cowork.ink's engineering blog documents the five-category agent failure taxonomy (transient, infinite loop, semantic, resource exhaustion, and rogue agent) and recommends degradation chains: if the primary search tool fails, try the backup. If all tools fail, return a cached result with a confidence indicator. If no cache, return a partial answer with a flag. Never let a single component failure cascade into complete system failure. — [Cowork.ink: AI Agent Error Handling](https://cowork.ink/blog/ai-agent-error-handling)

## Gotchas

- **Jitter is not optional.** Without random jitter, multiple agents recovering from the same outage will retry in lockstep, recreating the exact same load spike that caused the original failure. Add `random(0, jitter)` to every backoff formula.
- **Circuit breakers must be per-provider, not global.** A global circuit breaker that trips when OpenAI is down also blocks your calls to Anthropic — even though the failure is isolated. Each external dependency needs its own independent breaker.
- **Output validation is not error handling.** Checking whether an LLM's JSON output is valid JSON is error handling. Checking whether that JSON contains the right schema and semantically correct data is output validation. Both are needed. Many teams only implement the first layer.
- **Checkpoints have a storage cost but a recovery benefit that multiplies with pipeline length.** A 20-step pipeline that checkpoints every 2 steps will lose at most 2 steps of work on failure. A 20-step pipeline with no checkpoints loses all 20. The cost of serialization logic is a rounding error on the cost of the reprocessing you'd otherwise do.
- **Human escalation without context is useless.** Routing to a human reviewer without the full agent trajectory, tool call history, and failure reason produces a reviewer who either rubber-stamps or wastes time re-investigating. Always include: what was attempted, what failed, why it was attempted that way, and what alternatives were considered.
