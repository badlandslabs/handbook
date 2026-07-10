# S-889 · The Silent Failure Spiral Stack — When Your Agent Runs in Dev and Vanishes in Production

Your agent works perfectly in development. One instance, one request at a time, clean logs, happy path. You ship it. Three weeks later you're fielding complaints about ghosted enrichment pipelines, API bills 4x budget, and agents looping on a missing field nobody noticed. No crash. No exception. No alert. Just silence until someone notices the damage. The Silent Failure Spiral Stack is the pattern for building recovery-first agents that fail loudly, recover automatically, and escalate cleanly.

## Forces

- **Agents fail differently than software.** Traditional services crash with a stack trace — you see it. AI agents may loop silently for 35 minutes, spawn redundant subprocesses, accumulate context until the model halts, or take irreversible actions before a human can intervene. The failure modes are qualitatively different, and try/catch doesn't cover them. (Zylos Research, 2026 — [source](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery))
- **Rate limits and timeouts look like success.** A 429 from an upstream API, a tool that silently returns partial data, a 30-second timeout that gets swallowed — none of these crash your agent. They produce silence. And silence in production is the most dangerous failure mode. (Supergood Solutions case study, 2026 — [source](https://supergood.solutions/blog/when-your-agent-fails-silently))
- **The observability gap is structural.** LangSmith, LangFuse, Arize, and Helicone answer "what happened" but not "should this have happened." A looping agent generates perfectly formatted traces that look like normal execution. Your monitoring tools see nothing wrong. (Ceyhun Aksan, DEV Community, 2026 — [source](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai))
- **Cost spirals compound silently.** An agent in a retry loop on a rate-limited API can burn through a month's budget in hours. The longer the agent runs without a cost circuit breaker, the worse the damage. (Agentbrisk, 2026 — [source](https://agentbrisk.com/blog/ai-agent-error-recovery-2026/))

## The Move

Build recovery into the agent's architecture from the start. Five layers, applied from innermost to outermost:

1. **Hard step caps.** Set a recursion limit and enforce it. If the agent doesn't finish in N steps (Rajpoot recommends 12 for most agents), stop, document state, and escalate. In LangGraph: `recursion_limit=12`. This is the single most important guardrail — it turns infinite loops into bounded failures. (Rajpoot, 2026 — [source](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026))

2. **Structured tool error semantics.** Tool responses must carry structured error metadata, not just empty payloads. A tool that fails should return `{"error": "rate_limited", "retry_after": 2}` — not a silent timeout. The agent then routes to retry logic based on error type, not absence of data. (Rajpoot, 2026 — same source above)

3. **Exponential backoff retries at the tool layer.** Three retries max. After three consecutive transient failures (429, 503, timeout), stop retrying — you're in an outage, not a flap. Escalate to the fallback layer. Jitter on delay prevents thundering herd. (Clarion.ai, 2026 — [source](https://clarion.ai/insights-resilient-agentic-ai-pipelines-retry-fallback-human-in-the-loop))

4. **Fallback chains that degrade gracefully.** When retries are exhausted, the pipeline tries the next option in sequence: frontier model → smaller local model → cached result → human handoff. Never crash — always have a next step. (Clarion.ai, same source above; Agentbrisk, same source above)

5. **Cost circuit breaker.** Track cumulative cost per session or per task. If the agent exceeds a threshold (e.g., $2 of API calls without a meaningful state change), halt and alert. This is distinct from step caps — an agent can run 12 short steps and still cost $50 on a verbose model. (Rajpoot, same source above)

## Evidence

- **Engineering case study (Supergood Solutions, 2026):** A lead-enrichment agent ghosted in production — no crash logs, no exceptions, just silence. Root cause: Clearbit's 10 req/sec rate limit was exceeded by 3 concurrent instances generating 30 req/sec during peak hours. Clearbit silently dropped requests (429), the agent received no response, timed out after 30 seconds, and moved on. Fix: exponential backoff retry logic with circuit breakers. — [URL](https://supergood.solutions/blog/when-your-agent-fails-silently)
- **Community failure taxonomy (vectara/awesome-agent-failures, 2026):** A curated repo (187 stars) documenting real failure modes: tool hallucination (agent uses a tool with hallucinated parameters), response hallucination (agent combines correct tool outputs into a wrong final answer), goal misinterpretation (agent optimizes for the wrong objective), and plan generation failures (agent sends calendar invite before confirming availability). Each entry includes battle-tested mitigation. — [URL](https://github.com/vectara/awesome-agent-failures)
- **Engineering guide (Agentbrisk, March 2026):** Production agents fail in predictable shapes: rate limits (429), server errors (503), timeouts on slow tools, malformed model responses, cascading failures when one dependency goes down. The guide provides a four-pattern production resilience stack: retry with exponential backoff, circuit breakers, fallback model routing, graceful degradation. — [URL](https://agentbrisk.com/blog/ai-agent-error-recovery-2026/)

## Gotchas

- **Silent failures are harder to detect than crashes.** If your agent fails silently, your monitoring will look healthy. You need behavioral assertions — "this pipeline should complete in under 60 seconds" — not just availability checks. (Ceyhun Aksan, same source above)
- **Retrying without idempotency doubles the damage.** Before adding retries anywhere, ask: if this call runs twice, does anything bad happen? If yes, you don't have a retry problem — you have a side-effect problem. Make the operation idempotent first (natural keys, deduplication tokens, conditional writes), then add retry logic. (GoCodeo engineering guide, 2025 — [source](https://www.gocodeo.com/post/error-recovery-and-fallback-strategies-in-ai-agent-development))
- **Three retries is the right budget for LLM API calls.** Beyond three, you're likely in an outage, not a transient flap. Continuing to retry at that point is a cost spiral, not recovery. Escalate to human-in-the-loop instead. (Clarion.ai, same source above)
- **Step caps prevent loops but don't fix wrong answers.** An agent can complete 12 steps while confidently producing a wrong result. Step caps are a safety net for loops, not a quality guarantee. Combine with trace inspection and behavioral assertions.
