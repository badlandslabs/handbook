# S-1319 · The Dead End Stack — When Your Agent Gets Stuck and Never Recovers

Your agent entered a loop 40 minutes ago. It keeps trying the same failing API call, burning tokens, holding a connection, and producing nothing. Nobody set a max iterations cap. Nobody added a circuit breaker. Nobody taught it to say "I can't do this." The agent is still going, and it will be going when you check tomorrow morning — and the morning after.

## Forces

- **LLM non-determinism makes errors unpredictable** — a prompt that works once fails the next time due to model drift, token variation, or an API schema change. Traditional try/catch blocks don't cover hallucinated tool arguments or semantically wrong outputs.
- **The loop is the default behavior** — a ReAct loop runs forever unless something stops it. Every agent architecture (single-loop, plan-and-execute, hierarchical) converges on "keep going until done," but the termination condition is often absent or brittle.
- **Failure modes are heterogeneous** — rate limits need backoff; server outages need fallbacks; infinite loops need hard caps; semantic errors need self-correction. One handler can't cover all of them.
- **Context window is a ticking clock** — each failed iteration adds to the context. A stuck agent eventually fills its context window and starts truncating memory, making recovery harder rather than easier.
- **Operational cost compounds silently** — at $0.01–$0.10 per 1,000 tokens, a looping agent can cost hundreds of dollars per hour with nothing to show for it.

## The Move

Build a layered defense system where each layer catches a different failure class, and the layers compose into a recovery hierarchy.

**Layer 1 — Classify the error before acting on it.**

```
TransientError (429, 500, 503, timeout) → retry with backoff
PersistentError (auth failure, bad schema, resource gone) → fallback path
SemanticError (malformed JSON, wrong output shape, hallucinated tool) → self-correction
```

Do not lump these together. A 429 requires waiting. A 401 requires stopping and alerting. Malformed JSON from the model requires a different retry prompt.

**Layer 2 — Exponential backoff with jitter for transient failures.**

```python
base_delay = 1
for attempt in range(max_retries):
    try:
        return api_call()
    except RateLimitError:
        sleep(base_delay * (2 ** attempt) + random.uniform(0, 1))
    except ServerError:
        sleep(base_delay * (2 ** attempt) + random.uniform(0, 1))
```

Jitter prevents thundering herd — multiple agents retrying simultaneously at the same intervals and hammering the API at the same moment.

**Layer 3 — Hard stopping conditions (always include at least two).**

| Stop type | Trigger | Purpose |
|---|---|---|
| Hard stop | `iterations >= max_iterations` | Prevents infinite loops |
| Budget stop | `tokens_spent >= max_tokens` | Caps cost exposure |
| Timeout | `elapsed_seconds >= max_seconds` | User-facing SLA |
| Soft stop | Agent outputs final-answer token | Normal task completion |

Layer at least two. Hard stop + budget stop is the minimum viable pair. Timeout alone is insufficient — a slow but making-progress agent gets killed unfairly.

**Layer 4 — State checkpointing with resumable recovery.**

After each meaningful step, serialize the agent's state (current plan, tool results, context) to durable storage. When the agent is interrupted (by stop, crash, or restart), resume from the last checkpoint rather than re-executing from scratch. LangGraph provides this natively via `interrupt_before`/`interrupt_after` breakpoints with `Command(resume)`. MirrorNeuron persists state, retries failed steps, and resumes from where it left off across restarts.

**Layer 5 — Self-correction loop for semantic errors.**

When a tool returns a malformed result or the agent produces an invalid output format, feed the error back into the model with the original error context and ask it to fix. This is distinct from retrying — the model gets the specific failure message and a directive to self-correct, not a blind second attempt.

```python
output = llm(messages)
if not is_valid(output):
    messages.append({"role": "user", "content": f"Previous output invalid: {error}. Fix it."})
    output = llm(messages)  # Second attempt with error context
```

**Layer 6 — Fallback to a different model or a human.**

When all retries are exhausted on a persistent error, escalate. Route to a different model provider (e.g., switch from GPT-4 to Claude for a task the primary model consistently mishandles), or surface the failure to a human. Never let a failed agent silently continue consuming resources.

## Evidence

- **HN Post / Engineering Blog:** Philip Zeyliger (Sketch) on the unreasonable effectiveness of the LLM agent loop — shows the minimal 9-line ReAct loop but explicitly notes the need for stopping conditions in production. Discusses tool-call failures as a primary failure mode. — [sketch.dev/blog/agent-loop](https://sketch.dev/blog/agent-loop) / [HN discussion, 447 points, May 2025](https://news.ycombinator.com/item?id=43998472)
- **GitHub README / HN Post:** Agentic Reliability Framework (ARF) — separates decision intelligence from governed execution, providing deterministic safety guarantees and self-healing for multi-agent systems. Includes structured error classification and recovery paths. — [github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework) / [HN Show HN, 2025](https://news.ycombinator.com/item?id=46207273)
- **GitHub System Design Guide:** Error taxonomy for agentic systems — categorizes failures as hallucinated tools, malformed JSON, rate limits, and infinite loops. Recommends stateful rollbacks via LangGraph checkpointing as the primary mitigation for loop-entrapment. — [ai-system-design-guide/07-error-handling-and-recovery.md](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Open-source Runtime:** MirrorNeuron — open-source agent runtime that persists state, retries failed steps, and resumes from checkpoints across process restarts. "Durable execution" is the explicit design goal. — [mirrorneuron.io](https://www.mirrorneuron.io) / [HN Show HN, 2026](https://news.ycombinator.com/item?id=47884446)
- **Technical Blog:** Zylos Research (May 2026) — identifies brittle planning as the dominant failure mode in deployed agents, ahead of hallucination or missing capability. Documents adaptive replanning and backtracking as the architectural response. — [zylos.ai/research/2026-05-15-ai-agent-planning-backtracking-adaptive-replanning](https://zylos.ai/research/2026-05-15-ai-agent-planning-backtracking-adaptive-replanning/)
- **Engineering Blog:** Learnixo — max iterations, budget stops, and circuit breakers as mandatory production guardrails, with specific code patterns and rationale for each. — [learnixo.io/courses/agentic-ai-patterns/ap-max-iterations](https://learnixo.io/courses/agentic-ai-patterns/ap-max-iterations)

## Gotchas

- **Don't retry unconditionally.** Auth errors (401), bad request errors (400), and resource-not-found errors (404) will never succeed on retry — they indicate a configuration problem or a broken state. Retrying them just burns tokens and delays alerting. Classify errors first, then decide whether to retry.
- **Don't rely on a single stop type.** A timeout-only agent gets killed during a legitimate slow operation. A max-iterations-only agent might be burning budget between iterations even if it hasn't hit the cap. Layer at least two stop mechanisms from different categories.
- **Don't let the model guess the error type.** If a tool call fails, pass the actual error message to the model in the next prompt rather than letting it hallucinate a fix. "The previous output was invalid JSON: `Unexpected token at position 42`" produces much better self-correction than "try again."
- **Checkpoint state, not just progress.** Saving "step 3 completed" is not enough — save the accumulated tool results, partial outputs, and reasoning state. An agent that resumes from step 3 but has lost the context from steps 1–2 will redo work or produce inconsistent results.
- **Circuit breakers protect downstream services, not just your agent.** When an external API is down, continuing to hammer it doesn't help your agent and can worsen the downstream outage. A circuit breaker that fails fast and switches to a fallback path is kinder to everyone.
