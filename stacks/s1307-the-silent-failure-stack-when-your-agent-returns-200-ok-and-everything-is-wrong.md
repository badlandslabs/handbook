# S-1307 · The Silent Failure Stack — When Your Agent Returns 200 OK and Everything Is Wrong

Your agent loop completed without throwing a single exception. Every tool call returned a response. The API logged HTTP 200 across the board. And yet the agent sent packages to the wrong addresses, misread financial data, and hallucinated tool calls that never executed — all silently. This is the silent failure problem: the failure mode that costs the most and looks like success from every observable signal.

## Forces

- **Agents fail with answers, not errors.** A conventional service crashes with a stack trace; an agent produces a plausible but wrong response. The location of failure is opaque — buried in reasoning, not surfaced by the system.
- **HTTP 200 is not success.** Tool calls that return a response are treated as successful by most monitoring stacks, even when the response contains malformed JSON, wrong schema data, or fabricated content. There's no exception to catch.
- **Correct final output masks broken trajectories.** An agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints. Output-only evaluation misses 20–40% of regressions. The destination was fine; the route was a disaster.
- **LLM-as-judge creates echo chambers.** Using the same model family to evaluate its own agentic offspring shares blind spots. The judge and the agent are optimized for similar patterns of "reasonable-sounding" output.
- **Failure type determines recovery path.** A rate limit (transient) needs a retry with backoff. A hallucinated tool name (semantic) needs re-prompting with corrective context. A token budget breach (resource) needs summarization. Mixing them up makes things worse.

## The move

The move is **layered failure taxonomy + trajectory-scoped recovery**. Treat each failure class differently, and instrument the agent loop at the step level — not just the endpoint.

**1. Classify failures into four types, each with a distinct response:**

| Type | Examples | Response |
|------|----------|---------|
| **Transient** | Rate limits (429), timeouts, 503, DNS failures | Retry with exponential backoff + jitter — the same request will succeed if you wait |
| **Semantic** | Malformed JSON, wrong tool name, schema violations | Re-prompt with corrective context appended — the agent can fix the approach, not just retry blindly |
| **Resource** | Token budget exceeded, context overflow, spending cap | Reduce payload — summarize history, drop older tool results, switch to cheaper model |
| **Fatal** | Auth failures, revoked API keys, removed endpoints, policy violations | Abort immediately, log, alert — do not retry or re-prompt |

**2. Wrap the agent loop in a circuit breaker.** Set hard limits: max steps (typically 5–15 for most tasks), token budget, wall-clock time. When the breaker trips, return a structured error with the step count and reason. Do not let the agent loop silently for 35 minutes.

```
breaker = CircuitBreaker(turn_limit=10, token_limit=15000)
result = loop.run(task)
# Branch on result — do NOT catch CircuitBreakerError inside loop.run()
```

**3. Evaluate trajectories, not just endpoints.** Score the full path: which tools were called, in what order, with what arguments, and whether each step satisfied policy constraints. A replay harness re-runs captured traces with modified inputs to surface whether regressions are structural or lucky.

**4. Treat "200 OK but wrong" as the primary threat.** Instrument tool responses with schema validation before passing them to the agent. Flag malformed JSON, missing fields, and unexpected types at the tool layer — not after the agent has already incorporated wrong data into its reasoning.

**5. Combine human review for calibration with automated scoring.** LLM-as-judge scales but drifts. Domain expert review on a sample of trajectories (5–10%) provides the ground truth needed to validate whether automated scores are tracking real quality.

## Evidence

- **Survey (306 practitioners, 86 deployed systems):** First large-scale study of production AI agents (Berkeley/Stanford/IBM, arXiv:2512.04123, June 2026) found 68% of production agents execute 10 or fewer steps before human intervention — suggesting guardrails, timeouts, and failure boundaries are the norm, not the exception. Only 15% of agents run more than 20 steps without human oversight.
- **Engineering post:** The "Constraint Decay" paper (278 HN points) and follow-on analysis found that 88% of AI POCs never reach production scale — root cause is almost never model accuracy. It's the inability to trace why an agent made a decision. Teams cite "silent failure" as the top reliability threat. (Sherlocks.ai analysis of 73 production incidents, June 2026 — https://www.sherlocks.ai/blog/why-ai-agents-fail-in-production)
- **Engineering post:** Galileo's 2025 analysis found specification failures account for ~42% of multi-agent failures, coordination breakdowns 37%, and verification gaps 21%. 50x cost variation observed for similar accuracy across different agent configurations. Enterprise data shows 37% performance gap between lab scores and production outcomes. (Zylos Research, May 2026 — https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **HN thread (Show HN):** Agentic Reliability Framework — multi-agent self-healing system using circuit breakers, checkpointing, and structured fallback chains for tool call failures. 468 HN points. (https://news.ycombinator.com/item?id=46207273)

## Gotchas

- **Retry logic without error classification makes things worse.** Blind retry amplifies rate limit errors and lets semantic failures loop indefinitely. Classify first, then choose the response strategy.
- **Max-step limits prevent disaster but sacrifice completability.** Setting turn_limit=5 stops loops cheaply, but agents that need 7 steps for a correct answer will fail silently. Tune limits against real task distributions, not intuition.
- **LLM-as-judge correlation with human judgment drops over time.** Spearman correlation of 0.80+ is achievable, but model updates, input distribution shifts, and benchmark contamination erode it. Re-calibrate the judge against human samples quarterly.
- **Instrumenting for silent failures requires schema validation at the tool boundary, not at the agent.** By the time the agent has incorporated wrong data into its reasoning chain, it's too late to catch it by inspecting the output. Validate tool responses before they enter context.
