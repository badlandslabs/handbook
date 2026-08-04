# S-2138 · The Agent Recovery Stack — When Your Agent Crashes at Step 47 of 50 and Starts Over

Your agent is 47 steps into a 50-step ETL pipeline. It has extracted, validated, and transformed all the data. Then an OOM kill hits the container mid-load and the agent restarts from step 1. Every result is lost. The agent loops again, hits the same memory pressure, and dies again. This is not an edge case — it is the default behavior of every agentic system that doesn't treat failure recovery as a first-class architectural concern.

## Forces

- **Agent failures cascade.** A 98% reliable agent × 5 sequential steps = 90% end-to-end reliability. Without explicit recovery mechanisms, compounding failures across steps turn minor blips into total loss.
- **Naive loops have no memory.** The standard agent loop — `while not done: model → tool → repeat` — stores no state outside the current turn. A crash at step 47 means step 47 never happened, regardless of how much work preceded it.
- **Not all failures deserve the same response.** Retrying a 429 rate limit is correct. Retrying an auth failure is waste. Retrying a context overflow by re-running the same prompt is guaranteed to loop. The agent must classify errors before choosing a recovery path.
- **Multi-agent systems amplify failure surfaces.** Zylos Research measured 41–86.7% failure rates in production multi-agent systems without deliberate fault tolerance design. Each agent-to-agent handoff is a potential failure point with no natural recovery.
- **State is expensive to rebuild.** Re-deriving context, re-querying memory, re-running sub-agents — the cost of recovery-from-scratch compounds with task complexity.

## The Move

Build recovery into the agent loop itself, as infrastructure — not as a feature layered on top. Three layers work together:

**Layer 1 — Classify errors before retrying.** Route each failure into exactly one of four buckets, each with a distinct recovery path:

| Error type | Examples | Response |
|---|---|---|
| **Transient** | 429 rate limit, 503, DNS timeout, connection reset | Retry with exponential backoff + jitter |
| **Semantic** | Malformed tool output, schema violation, wrong tool selected | Re-prompt with corrective context and hints |
| **Resource** | Token budget hit, context overflow, spending cap | Reduce payload — summarize, drop partial results, switch to smaller model |
| **Fatal** | Auth failure, revoked key, policy violation | Abort immediately, log, alert, do not retry |

Never retry blindly. A retry loop hammering a 401 endpoint wastes tokens and time while the underlying problem stays broken.

**Layer 2 — Checkpoint after every completed step.** Persist agent state (conversation history, intermediate outputs, tool results, execution pointer) to durable storage after every successful step — not just on completion. On crash, resume from the last checkpoint, not from step 1. LangGraph's `PostgresSaver` and `RedisSaver`, Restate's durable execution primitives, and AxmeAI's checkpoint-and-resume library all implement this pattern. The key design constraint: checkpoint writes must not block the agent loop — async writes or write-ahead logging prevent the checkpoint itself from becoming a bottleneck.

**Layer 3 — Progressive escalation with hard bounds.** The self-healing hierarchy from agentpatterns.ai:

```
Self-Correct (retry with context adjustment)
  → Fallback (switch to alternative strategy or smaller model)
    → Degrade Gracefully (return partial results with clear gaps flagged)
      → Escalate (cap fix attempts via circuit breaker, hand off to human)
```

The circuit breaker is the hard stop. After N consecutive failures on the same task, stop attempting fix and surface the partial result with a clear error report. This prevents runaway loops that burn budget on tasks the agent cannot complete.

## Evidence

- **GitHub repo / reference impl:** `hailports/self-healing-agent` — a zero-dependency reference loop implementing retries with backoff, circuit breakers, watchdog timers, checkpoint/resume, and a budget governor in ~200 lines. Provides one `generate(system, messages)` method for provider-agnostic model swapping. — [https://github.com/hailports/self-healing-agent](https://github.com/hailports/self-healing-agent)
- **Engineering blog / production walkthrough:** Restate's durable coding agent post — builds on Modal (ephemeral sandboxes) + Restate (durable execution) to achieve "continues from latest completed step" on crash, automatic failure recovery, and scale-to-zero without custom retry code. — [https://www.restate.dev/blog/durable-coding-agent-with-restate-and-modal](https://www.restate.dev/blog/durable-coding-agent-with-restate-and-modal)
- **Pattern taxonomy:** Neel Mishra's agent error taxonomy — four error categories (transient, semantic, resource, fatal) with recovery strategy mapping and Python implementation. — [https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **LangGraph production lessons:** Gheware DevOps blog — documents that conditional edges + retry nodes with exponential backoff distinguish demos from production, and that `MemorySaver` teams lose all state on pod restart in containerized environments. — [https://devops.gheware.com/blog/posts/langgraph-production-ai-agents-2026.html](https://devops.gheware.com/blog/posts/langgraph-production-ai-agents-2026.html)
- **Multi-agent failure rates:** Zylos Research measured 41–86.7% failure rates in multi-agent production systems without fault tolerance design; recommends tool-specific circuit breakers and provider-level fallback chains (Anthropic → OpenAI → Cohere → local model). — [https://zylos.ai/research/2026-02-20-graceful-degradation-ai-agent-systems](https://zylos.ai/research/2026-02-20-graceful-degradation-ai-agent-systems)

## Gotchas

- **MemorySaver is not production.** LangGraph's default `MemorySaver` resets on process exit. Every pod restart, every OOM kill, every container rescheduling in Kubernetes wipes the agent's state. If you checkpoint only to memory, you have no checkpoint.
- **Retry loops without jitter create thundering herds.** If every agent instance retries at the same interval after a shared rate limit, synchronized retries compound the original problem. Add random jitter to spread retry windows across 0.5×–1.5× of the base delay.
- **Context overflow on retry is a common suicide loop.** An agent that hits a token limit on step 47 often retries the same prompt and hits the same limit. The correct response to a resource error is not to retry the same prompt — it is to reduce the payload (summarize history, drop low-priority intermediate results, switch to a model with a larger context window).
- **Checkpoint write failures are silent killers.** If the checkpoint write itself throws an exception and is caught, the agent continues without persisting state — and the next crash behaves identically to having no checkpoint at all. Wrap checkpoint writes with their own retry logic or write-ahead logging.
- **The circuit breaker must track per-task, not globally.** A circuit breaker that trips globally after N failures prevents the agent from attempting any task. Track failure counts per task type or per tool, so a failing search tool doesn't disable a working code-execution tool.
