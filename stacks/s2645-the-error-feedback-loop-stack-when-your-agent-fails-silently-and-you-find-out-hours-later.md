# S-2645 · The Error-Feedback Loop Stack — When Your Agent Fails Silently and You Find Out Hours Later

Your agent ran for 90 minutes on a 10-step pipeline. It returned a result. Three days later, a customer notices the data is stale. Step 6 hit a rate limit at minute 12. The agent swallowed the HTTP 429, re-ran step 6 with degraded parameters, and continued — producing output that looked valid but was semantically wrong. Nothing threw an exception. Nothing logged an error. The pipeline reported success.

This is the silent failure pattern. It is the most common production failure mode for AI agents, and traditional error handling does not catch it.

## Forces

- **LLM failures don't throw exceptions.** HTTP 200 with malformed JSON, a tool that succeeds technically but returns garbage semantically, a rate-limited call that retries with worse parameters — these all look like success to a naive try/catch wrapper. Agents that only check HTTP status codes will miss the failure modes that matter most.
- **Multi-step pipelines lose all prior work on step failure.** A pipeline running steps 1–7 successfully, then failing on step 8 (e.g., LLM rate limit), has no checkpoint to resume from. The agent must start over. In pipelines that run 30 minutes to 4 hours, this means hours of compute wasted on every transient failure. — [Rittika Jindal, Principal Engineer @ Thomson Reuters, "Building Retries in Agents"](https://pub.towardsai.net/building-retries-in-agents-how-to-build-ai-agents-that-survive-failures-32eedd2623f0)
- **Semantic failures are invisible to infrastructure.** "The agent returned output that was 200 OK but the JSON was unparseable" is not a network error. Neither is "the model hit its context window limit mid-generation." A circuit breaker that only tracks HTTP failures will not catch these.
- **Output quality is not the same as execution success.** An agent can produce syntactically valid, semantically confident nonsense and report it as a successful result. Validation guards must check both whether the tool ran and whether its output actually answers the query. — [Blog.jztan.com, "AI Agent Error Handling: 5 Patterns"](https://blog.jztan.com/ai-agent-error-handling-patterns)

## The move

Error handling for AI agents requires four layered strategies — each targeting a different failure taxonomy.

### 1. Classify errors into four types, then apply targeted recovery

Not all errors are equal. Applying the wrong recovery to the wrong error type makes things worse.

| Error type | Examples | Recovery |
|---|---|---|
| **Transient** | Rate limit (429), timeout, 503, DNS | Retry with backoff — same request will likely succeed |
| **Semantic** | Malformed JSON, wrong schema, tool called incorrectly | Re-prompt with corrective context — the model can self-correct |
| **Resource** | Context overflow, token budget exceeded | Reduce payload (summarize history, drop older results, switch to shorter-context model) |
| **Fatal** | Auth failure, revoked API key, policy violation | Abort immediately, log, alert, escalate to human |

— [Neel Mishra, "Agent Error Handling: Retries and Fallbacks"](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

### 2. Wrap retries with exponential backoff + jitter, but feed the validation error into the retry

A plain retry re-rolls the same prompt at the same temperature — statistically likely to produce the same failure. A self-correcting retry passes the validation error back into the model:

```
Prompt: {original_prompt}
Response: {failed_response}
Validation error: {exact error from schema check}
Instruction: The previous response failed validation. Correct it.
```

This transforms the retry from a random re-roll into an error-correcting edit. — [Goldziher, r/LocalLLaMA, "A cheap trick for reliable structured output"](https://www.reddit.com/r/LocalLLaMA/comments/1ulatl7/a_cheap_trick_for_reliable_structured_output_feed/)

### 3. Add semantic circuit breakers — not just HTTP ones

Circuit breakers must track both infrastructure failures AND semantic failures. The pattern: closed → open → half-open.

- **Closed:** Normal operation. Failures are counted.
- **Open:** After N consecutive failures (configurable threshold), stop attempting and fail fast.
- **Half-open:** After a cooldown period, allow one test request. If it succeeds, close the breaker; if it fails, reopen.

The critical difference from traditional circuit breakers: count semantic failures (malformed output, tool returns wrong schema) the same as HTTP failures. An agent returning HTTP 200 with unusable output is just as broken. — [Blog.jztan.com, "AI Agent Error Handling"](https://blog.jztan.com/ai-agent-error-handling-patterns)

### 4. Checkpoint long pipelines and degrade gracefully

For pipelines running 30+ minutes, save state after every step. On failure, resume from the last checkpoint — not from scratch.

For non-critical failures, implement a graceful degradation chain instead of hard failure:

```
Primary model (GPT-4o) → Rate limited
→ Fallback model (GPT-4o-mini) → Still failing
→ Cached previous result → Return with "stale" flag
→ Dead letter queue → Alert human, return partial result
```

This chain prevents catastrophic failure while preserving visibility. — [Tanay Shah, "AI Agent Error-Handling Patterns"](https://tanayshah.dev/projects/ai-agent-error-patterns/)

### 5. Implement human-in-the-loop escalation for ambiguous failures

When the agent encounters a failure it cannot automatically resolve, it must stop and ask. Do not let the agent guess its way through ambiguous situations. Design explicit escalation criteria:

- Confidence below threshold after N retries
- Action requires irreversible consequences (destructive writes, financial transactions)
- Ambiguous input that could have multiple valid interpretations
- Dead letter queue overflow

The escalation should include full execution state — what steps ran, what outputs were produced, what the error was — so the human can make an informed decision without re-running anything. — [Tanay Shah, "AI Agent Error-Handling Patterns"](https://tanayshah.dev/projects/ai-agent-error-patterns/)

### 6. Monitor what traditional APM misses

Standard application monitoring tracks HTTP codes and latency. AI agents need:

- **Step-level tracing:** Every tool call, every LLM invocation, logged with input/output summaries
- **Token budget tracking:** Alert on unexpected spend or token usage spikes
- **Output quality gates:** Automated checks on whether tool output answers the query (not just whether it returned)
- **Execution graph diffing:** Compare what the agent reported as complete against what actually ran

Teams that don't instrument these dimensions have no way to run meaningful post-mortems. — [HN Ask: "How are you monitoring AI agents in production?", jairooh](https://news.ycombinator.com/item?id=47301395)

## Evidence

- **Engineering survey (Cleanlab, 2025):** < 1 in 3 teams are satisfied with observability and guardrail solutions for production agents. Only 5% of 1,837 surveyed engineering leaders have AI agents live in production. 63% plan to invest in observability and evaluation in the next year. — [Cleanlab, "AI Agents in Production 2025"](https://cleanlab.ai/ai-agents-in-production-2025/)
- **Case study (GetaTeam):** After identifying 5 critical failure patterns — API rate limits, unexpected input variations, hallucinated tool calls, cascading failures, and context overflow — and implementing exponential backoff, circuit breakers, dead letter queues, and comprehensive monitoring, a team improved agent uptime from 94.2% to 99.7%. — [GetaTeam Blog, "Why 90% of AI Agents Fail in Production"](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it)
- **Open-source library (Tanay Shah, 2025):** Production error-handling patterns for AI agents built with Trigger.dev v4, covering circuit breakers, partial success/dead letter queues, human-in-the-loop escalation, and graceful degradation chains. MIT license, standalone CLI tests. — [GitHub: tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)
- **Architecture guide (ombharatiya/ai-system-design-guide):** Verifier Agent pattern — pipe tool output to a smaller, faster model whose only job is to check "does this output actually answer the query?" If not, trigger self-correction as if it were a hard error. Uses LangGraph checkpointing for stateful rollback. — [GitHub: ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Naive retry loops burn credits fast.** A retry without backoff that hits a rate limit will immediately re-request and get rate-limited again, compounding the problem. Always add exponential backoff with jitter. A retry storm on a rate-limited API can burn thousands of dollars in minutes.
- **HTTP 200 is not success.** The most dangerous agent failures return HTTP 200. The output looks valid. The agent continues. The result is quietly wrong. You must validate output semantics, not just status codes.
- **Checkpoints are only useful if you actually resume from them.** Teams add checkpointing infrastructure but forget to wire up the resume logic. On failure, the agent still starts from scratch, and the checkpoint data accumulates unused.
- **Escalation is useless without execution state.** Sending a human "the agent failed" with no context forces them to re-run the investigation. The escalation payload must include full step history, outputs, and error details.
