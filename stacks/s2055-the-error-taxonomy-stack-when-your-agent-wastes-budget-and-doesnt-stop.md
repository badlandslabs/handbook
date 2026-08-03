# S-2055 · The Error Taxonomy Stack — When Your Agent Wastes Budget and Doesn't Stop

Your agent spent 47 minutes in a loop last night, burning $12.80 in API calls on a task that should have cost $0.08. Nobody noticed until the morning log review. You're shipping agents to production and discovering that the gap between a working demo and a resilient system is exactly the gap between ignoring failure and classifying it.

## Forces

- **Errors in agents are semantic, not just syntactic.** Traditional software fails with exceptions you can catch. Agents fail with HTTP 200 and confident nonsense — the same prompt that produced valid JSON an hour ago now returns a hallucinated schema. You can't catch your way out of this with a try/except.
- **Failure cascades by default.** A rate-limited API call doesn't just fail — it re-triggers planning, re-populates context, and re-issues the same call. One transient error becomes a spiral. Per Zylos Research, 67% of AI system failures stem from improper error handling rather than algorithmic issues.
- **Retry storms are invisible until they're expensive.** Indiscriminate retries on a 429 (rate limit) don't just delay — they amplify. Every client that hammers a throttled endpoint extends the cooldown window for all clients. An agent with 5 retries hitting a rate-limited endpoint can delay recovery by minutes.
- **Loop detection requires deterministic signals, not LLM judgment.** Asking the agent "are you stuck?" doesn't work — the agent will confidently report progress on the 30th iteration. You need structural checks that don't depend on the model's self-assessment.

## The Move

**Classify errors before you retry, then route to the right recovery strategy.**

### 1. Build a four-category error taxonomy

| Category | Examples | Recovery |
|---|---|---|
| **Transient** | 429, 503, DNS timeout, network blip | Exponential backoff + jitter, then retry |
| **Semantic** | Malformed JSON, invalid tool arguments, schema violations | Re-prompt with corrective context, max 2 passes |
| **Resource** | Token budget exceeded, context overflow, cost cap hit | Reduce payload (summarize, chunk, drop low-priority results) |
| **Fatal** | 401 auth failure, revoked key, policy violation | Abort immediately, log, alert operator |

Classify before you retry. A retry loop that hammers a 401 wastes tokens and extends the outage. A transient error that you treat as fatal causes unnecessary escalation.

### 2. Implement exponential backoff with jitter

```python
RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay": 1.0,
    "max_delay": 60.0,
    "multiplier": 2.0,
    "jitter": True  # critical: prevents thundering herd
}
```

Jitter is not optional. Without it, every client retries at the same interval, synchronized, extending the outage for everyone. Full jitter (randomizing the entire backoff window) outperforms equal jitter.

### 3. Wrap the circuit breaker around external dependencies

Track failure counts per external call (API, vector store, tool endpoint). After N failures in a window, open the circuit — fail immediately for M seconds rather than retrying. This prevents retry storms from cascading into full system degradation. LangGraph's checkpointing pairs well here: when a circuit trips, the agent state is preserved and can resume after recovery.

### 4. Detect loops structurally, not semantically

Track three independent signals: action repetition rate (same tool called N times consecutively), trajectory divergence (embedding similarity of recent steps drops below threshold), and step count vs. task complexity estimate. Any one signal firing is a warning; two is a hard abort. DeepEval implements this as a deterministic metric (no LLM judgment required). The Agent Patterns taxonomy identifies four loop types — hard loop (same action repeated), soft loop (different actions but same goal), retry storm (repeated error cycles), and semantic loop (LLM re-interprets the same input repeatedly).

### 5. Build a fallback chain, not a single model

When the primary LLM fails or is unavailable, route to a fallback model. When fallback is also unavailable, have a deterministic code path that completes the task at reduced fidelity — return cached results, use a simpler heuristic, or surface the partial result with a clear status flag. The tanayshah11/ai-agent-error-patterns repo on GitHub demonstrates partial-success handling: 95/100 items in a batch succeeding means you return the 95 with clear provenance, not a full failure.

### 6. Checkpoint long-running agents

For agents that span minutes or hours, persist state at decision points. If the process crashes or a circuit breaker trips, resume from the last checkpoint rather than restarting. LangGraph's checkpointing is the canonical implementation. Without it, recovery means replaying every step from scratch — expensive and slow.

## Evidence

- **τ-Bench analysis (Atla/EvalToolbox, April 2025):** Detailed failure categorization on production agent traces revealed that aggregate success rates (e.g., "50% of tasks complete") obscure the actual failure modes. Agents fail in predictable categories — tool call errors, context mismanagement, verification failures — that are only visible when you decompose the trace. Atla's EvalToolbox implements this granular failure diagnosis for τ-retail and τ-customer benchmarks. — [MarkTechPost deep-dive](https://www.marktechpost.com/2025/04/30/diagnosing-and-self-correcting-llm-agent-failures-a-technical-deep-dive-into-%CF%84-bench-findings-with-atlas-evaltoolbox/)
- **OpenClaw Self-Healing (Ramsbaby, 2025):** A 4-tier autonomous recovery ladder that escalates from self-healing scripts (Tier 1) through service restarts (Tier 2), configuration repair (Tier 3), to human escalation (Tier 4). Built specifically to reduce 3 AM pages by letting the machine attempt obvious fixes before escalating. Only 14% of surveyed teams had production-ready implementations. — [HN Show post](https://news.ycombinator.com/item?id=47118278) | [GitHub repo](https://github.com/Ramsbaby/openclaw-self-healing)
- **Agent Patterns taxonomy (agentpatterns.tech, 2025):** Documents four distinct loop types with production detection methods. Hard loops (same action repeated) and soft loops (different actions, same goal) require structural detection — semantic checks fail because the agent confidently reports progress. The repo cross-references implementation patterns across LangGraph, CrewAI, and AutoGen. — [Agent Patterns](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **Lemma (YC F25):** Built a production monitoring product specifically because agent prompts degrade ~40% in a few weeks in production due to real-world input drift. The problem isn't just crashes — it's silent performance degradation that goes unnoticed until it affects users. — [Y Combinator company page](https://www.ycombinator.com/companies/uselemma)

## Gotchas

- **Don't retry everything.** Fatal errors (auth failures, policy violations, revoked keys) won't resolve with retry — they'll just consume budget and delay alerting. Classify first.
- **Don't ask the agent if it's stuck.** LLMs consistently over-report confidence in their own progress. Loop detection must be structural and deterministic: step count, action repetition rate, trajectory embedding similarity. The model cannot reliably self-diagnose.
- **Graceful degradation is harder than full failure.** Returning a partial result (95/100 items processed) requires your output schema to carry provenance and status flags. Retrofitting this into a system that assumed 100% success is expensive — design for partial success from the start.
- **Checkpointing adds latency.** Persisting state at every decision point isn't free. Profile the overhead — for short-lived agents (<30 seconds), the cost may exceed the benefit. For long-running agents, it's essential.
- **Jitter must be full jitter, not equal jitter.** Equal jitter (adding a small random delta to a fixed interval) still produces herd patterns. Use full jitter: randomize the entire backoff window within the range `[0, calculated_delay]`.
