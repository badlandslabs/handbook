# S-1119 · The Safe Loop Stack — When Your Agent Can't Tell It Is Lost

Your agent enters a retry loop, burns $47,000 over 11 days, and you find out when the invoice arrives. The agent had no mechanism to recognize that it was going nowhere — it just kept trying. This is the failure handling problem in agentic AI: not crashes, but *silent, expensive loops* with no awareness that they're failing.

## Forces

- **Retry semantics differ from traditional software.** Transient failures (429s, timeouts) deserve retries. Semantic errors (malformed JSON, wrong tool) do not — re-prompting with the same prompt rarely helps. Most teams treat all errors the same way.
- **Agents fail probabilistically, not deterministically.** A prompt that works once can fail the next time due to model drift, token noise, or environmental state changes. You can't just patch a flaky code path — the failure mode is non-reproducible.
- **The cost of looping is asymmetric.** A retry loop consuming 50x tokens on restart is a real incident. Without spend limits, timeouts, or loop detection, agents can run indefinitely at massive cost.
- **Context loss on crash erases progress.** An agent working for hours making hundreds of tool calls can lose all of it when the worker dies. State is not durable by default.
- **Downstream cascading failures.** In multi-agent pipelines, one agent's failure can propagate silently to others that trust its output, amplifying errors across the system.

## The move

Build a layered failure handling architecture that distinguishes error types, limits blast radius, and makes the agent *aware* when it is stuck.

**1. Classify errors before choosing a recovery strategy.** Four categories, four responses:
- **Transient** (rate limits, timeouts, 503s): retry with exponential backoff + jitter
- **Semantic** (malformed JSON, wrong tool call, schema mismatch): re-prompt with corrective context, don't just retry
- **Resource** (token budget exceeded, context overflow): reduce payload — summarize history, switch to cheaper model
- **Fatal** (auth failures, revoked keys): escalate to human, stop immediately — no retries

**2. Implement loop detection with hard limits.** Every agent loop needs a tripwire:
- Max iteration count (e.g., 20 steps), after which the agent explicitly stops and surfaces state to a human
- State fingerprinting: track whether agent output is converging or repeating identical states across steps
- Spend ceiling per task: hard cap on tokens/dollars that triggers immediate stop and escalation

**3. Use circuit breakers for flaky tools.** When a tool or downstream API fails above a threshold (e.g., 5 failures in 2 minutes), stop calling it and fall back to an alternative or gracefully degrade — don't pile up requests on a failing dependency.

**4. Persist state across crashes with checkpointing.** Long-running agents need durable execution: every meaningful step is checkpointed to durable storage before the next step begins. If the worker dies, execution resumes from the last checkpoint — not from scratch.
- Temporal ($5B valuation, 9.1T lifetime executions, 380% YoY revenue growth as of Feb 2026) is the dominant production pattern for this. Every activity is recorded in an event history; a crashed workflow replays deterministically from the last known state.
- For lighter-weight needs: write progress state to a file or DB before each tool call, store the full conversation history, use `ContinueAsNew` to reset event history periodically and prevent unbounded growth.

**5. Escalate high-stakes failures to humans, not retry loops.** Financial transactions, irreversible actions, and decisions below a confidence threshold belong to a human reviewer. Build explicit escalation paths with a clear operator interface to review agent state, approve, reject, or correct — not a fallback retry.

**6. Validate outputs before downstream consumption.** Hallucinated tool arguments, fabricated JSON fields, and wrong citations don't throw errors — they silently corrupt downstream steps. Add output validation schemas (Pydantic models) at every tool boundary so malformed outputs are caught immediately rather than propagated.

## Evidence

- **Engineering blog:** A documented 2025 incident where a multi-agent LangChain system entered a retry loop for 11 days and ran up $47,000 in API charges — discovered only when the billing statement arrived. No spend limit per agent, no timeout, no alert. The architecture that enabled the capability had no mechanism to stop it. — [kognita.co](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **HN "Show HN":** "Securing the Ralph Loop" — a real-world security loop that adds mandatory scan-before-commit, fix iteratively, and explicit escalation after 3 retries. Architecture: `PRD → Claude Code → Security Scan → PASS? → Commit → Next Story / FAIL → Fix → Retry (3x) → Escalate`. — [github.com/agairola/securing-ralph-loop](https://github.com/agairola/securing-ralph-loop)
- **GitHub repo:** `ai-retry` (106 stars, MIT) — typed retry conditions for the AI SDK that track which models have been tried and how many attempts have been made, preventing infinite loops by tracking retry history across error-based and result-based triggers. — [github.com/zirkelc/ai-retry](https://github.com/zirkelc/ai-retry)
- **Industry metric:** Temporal reported 9.1 trillion lifetime action executions on its cloud, 20M+ monthly installs, 380% YoY revenue growth, and $300M Series D at $5B valuation in February 2026. The market validated durable execution as the backbone for production AI agents. — [Tech Funding News](https://techfundingnews.com/a16z-temporal-300m-series-d-5b-valuation), [AI2Work](https://ai2.work/blog/temporal-raises-300m-at-5b-to-power-agentic-ai-in-2026)
- **Blog post:** "Exception Handling and Recovery in Agentic AI" — formal lifecycle: anomaly detected → classify as expected vs unexpected → apply known handler or escalate → if recovery possible, retry with modified context; if not, degrade gracefully or surface to human. — [atalupadhyay.wordpress.com](https://atalupadhyay.wordpress.com/2026/03/16/exception-handling-and-recovery-in-agentic-ai)
- **MLOps guide:** Agent error taxonomy with recovery strategies — transient errors need backoff, semantic errors need re-prompting with corrective context, resource errors need payload reduction, fatal errors need immediate human escalation. — [neelmishra.github.io](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

## Gotchas

- **Don't retry everything the same way.** A rate limit and a malformed JSON response are not the same error class. Treat them differently or you'll burn tokens on errors that won't resolve with repetition.
- **Loop detection must be explicit, not emergent.** The agent will not notice it is stuck — it is generating plausible-sounding continuations. You must enforce hard limits (iteration count, spend ceiling, state fingerprinting) as architectural constraints, not as behaviors the model is asked to self-assess.
- **Context summarization on resource errors breaks determinism.** When you summarize conversation history to stay within token limits, you are discarding state. Ensure the summarization preserves the *decisions made so far*, not just the content.
- **Circuit breakers need monitoring to reopen.** A circuit that trips and stays open forever means a degraded capability with no recovery signal. Track failure rates over time and implement a half-open state that allows a probe request through to test whether the downstream service has recovered.
