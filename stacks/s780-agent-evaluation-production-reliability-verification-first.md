# S-780 · Agent Evaluation in Production: Verification-First Architecture

You have an agent that passes your demos. Now you need it to run for 8 hours without silent failure, give you an audit trail, and tell you when it doesn't know what it doesn't know. Evaluation and observability aren't add-ons — they're the production readiness layer.

## Forces

- An agent that is 95% accurate per step has ~60% success across 10 chained steps — the math doesn't forgive a single bad link
- Agents fail silently: they produce plausible-looking wrong outputs, consume tokens, and move on until a human notices or the bill arrives
- Traditional software testing maps poorly — agents have non-deterministic outputs, stateful environments, and emergent failure modes that only appear at long horizons
- The gap between pilot and production is real: 88%+ of enterprise agentic AI projects stall at or after first deployment (multi-source HN/corridor report consensus, 2025)

## The Move

**Build evaluation into the execution loop, not after it.**

### 1. Per-step assertions with deterministic gates

Don't trust the model's self-assessment. Use explicit post-conditions on each tool call — assertions that run against structured snapshots of the result, not against the model's own confidence. For browser agents, this means DOM-level checks (role, visibility, content) gated before the next step proceeds.

> "Reliability in agents comes from verification (assertions on structured snapshots), not just scaling model size." — HN discussion on verification layers for browser agents
> Source: [HN: A verification layer for browser agents: Amazon case study](https://news.ycombinator.com/item?id=46790127)

### 2. Classify errors before retrying

Four error categories require different recovery strategies:

| Error type | Examples | Recovery |
|---|---|---|
| **Transient** | Rate limits (429), timeouts, 503 | Retry with exponential backoff |
| **Semantic** | Malformed JSON, wrong tool name, schema violation | Re-prompt with corrective context appended |
| **Resource** | Token budget exceeded, context overflow | Reduce payload: summarize history, drop tool results, switch to cheaper model |
| **Fatal** | Invalid credentials, permission denied | Escalate to human, halt execution |

A blanket try/except around the whole agent is not recovery — it's hiding failure.

### 3. Instrument three signals: traces, costs, and intents

The minimum viable observability stack for agents:
- **Execution traces**: every tool call, input, output, and decision logged with timestamps — not just "what happened" but "what the agent intended at step T and why it diverged"
- **Cost tracking**: per-agent, per-model, per-task token accounting with budget guards
- **Risk detection on outputs**: flag dangerous actions (DELETE, exec, DROP TABLE) before they execute; require human-in-the-loop approval for high-stakes operations

### 4. Use production-mirrored evaluation environments

Benchmarks like BFCL V4 (Berkeley Function Calling Leaderboard) score agentic multi-step behavior, not just single-call accuracy. For web agents, PA Bench evaluates long-horizon multi-application workflows — the failure modes that only surface with extended horizon and cross-app state.

Benchmarks that matter: **BFCL V4** (40% weight on agentic behavior), **PA Bench** (real-world personal assistant workflows), **Tau-Bench** (agent-tool interaction under constraints).

## Evidence

- **HN Ask HN (2025):** Practitioner consensus that observability must live in an independent execution layer between the agent and business systems — "the agent proposes an intent, but the execution layer acts as the system of record." — [HN: Ask HN: How are you monitoring AI agents in production?](https://news.ycombinator.com/item?id=47301395)
- **Vibrant Labs PA Bench (Feb 2026):** Frontier models on real multi-app workflows: Claude Opus 4.6 achieved 68.8% task success rate, OpenAI CUA 12.5%, revealing that leaderboard scores on isolated tasks dramatically overstate real-world agent reliability. — [PA Bench: Evaluating Web Agents on Real World Personal Assistant Workflows](https://vibrantlabs.com/blog/pa-bench)
- **GitHub / lastmile-ai (2025):** `mcp-eval` — a lightweight eval framework for MCP servers that auto-generates tests from LLM, enabling continuous evaluation of tool-calling reliability regardless of server language. — [GitHub: lastmile-ai/mcp-eval](https://github.com/lastmile-ai/mcp-eval)
- **Neel Mishra blog (2025):** Four-category error taxonomy with per-type recovery strategies — systematic approach to agent failure rather than catch-all exception handling. — [Agent Error Handling: Retries and Fallbacks](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

## Gotchas

- **Retries without idempotency keys create duplicate side effects.** A retry on `send_email` or `charge_customer` is only safe if the operation is idempotent or the retry carries a unique request ID. Without this, retries compound into data corruption.
- **The observability layer must be independent of the agent framework.** If it lives inside the same process, a framework crash takes the audit trail with it. Practitioners report the execution layer must sit between the agent and business systems to act as the true system of record.
- **Human-in-the-loop is not a sign of weakness — it's a feature gate.** The most reliable production agents use human approval as a deterministic checkpoint for high-risk actions, not as a fallback for when the agent fails.
- **Most eval frameworks only test happy paths.** Production evaluation must include adversarial test cases: malformed tool responses, slow tools, context overflow mid-run, and permission-denied errors. Build the eval set from actual production failure logs.
