# S-2360 · The Failure Boundary Stack — When Your Agent Returns 200 OK and Deletes Your Database

Agents don't crash — they fail silently. They return HTTP 200 with confident nonsense, call non-existent tools, loop for 62 hours burning $47K, or delete a production database because the operator handed it a Railway API token with no guardrails. Traditional error handling (try-catch, HTTP status codes) doesn't cover these failure modes. This stack covers how production teams detect, recover from, and design around the failure modes that actually happen.

## Forces

- **Agents fail without raising exceptions.** The agent is the logic layer, and it can behave incorrectly while every system check passes. A 200 OK from the API layer means nothing when the agent decided to delete the wrong volume.
- **The failure surface is non-deterministic.** A prompt that works Monday fails Tuesday because the model drifted, the context grew, or the tool schema changed. Static tests catch nothing.
- **Runaway cost is the most common production incident.** Agents loop because they lack a stop condition, not because they have a bug. The cost accumulates before anyone notices.
- **Safety and capability trade off.** Tight guardrails reduce autonomy; loose ones enable the $47K weekend. Teams need to tune this per-task, not globally.

## The Move

Build a layered failure boundary system — not a single retry loop, but distinct mechanisms for detection, recovery, and containment that kick in at different failure scales.

**1. Classify failures into three buckets, handled differently:**

| Failure type | Detection | Recovery |
|---|---|---|
| **Transient** (API timeout, rate limit, network blip) | Any exception | Retry with exponential backoff (max 3–5 attempts) |
| **Logic error** (agent completes but output is wrong, hallucinated tool call) | Verifier Agent or output schema validation | Self-correction loop (Reflexion pattern); rollback to checkpoint if needed |
| **Structural** (infinite loop, context blowup, resource contention) | Token counter, iteration counter, circuit breaker | Hard stop — halt, surface to human, do not retry |

**2. Use a Verifier Agent for semantic validation.** Pipe tool outputs to a smaller, faster model whose only job is: "Does this output actually answer the query?" If the Verifier says no, trigger self-correction — not a retry with the same context, but a rollback + reformulated attempt. (AI System Design Guide, 2025 — https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

**3. State checkpointing before every multi-step action.** Frameworks like LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives. Before a tool call that modifies state, snapshot. On failure, resume from checkpoint rather than replaying the entire sequence. (AI System Design Guide, 2025 — same source as above)

**4. Four runtime guardrails, layered at agent/service/infrastructure:**

- **Token-based throttling** — catch context-window blowups before they happen (hard limit at 80% of model's context)
- **Request/iteration throttling** — enforce max iterations per task (8–15 is typical; beyond that, most loops won't self-correct)
- **Circuit breakers** — trip on repeated identical tool calls or repeated identical errors; stop the loop entirely and escalate
- **Budget caps** — hard stop at a configurable dollar threshold per task or per session

**5. Permission boundaries follow least-privilege by default.** An agent that has write access to Railway can call `volumeDelete`. An agent scoped to read-only cannot — even if it decides to. Scope tokens to the minimum permissions required for the task. (Confirmed by HN analysis of the Cursor/Railway database deletion incident — https://news.ycombinator.com/item?id=47911524)

**6. Human-in-the-loop checkpoints for irreversible actions.** Require confirmation before database writes, API calls to external services, or repeated retry failures. Set a retry-count threshold that always surfaces to a human, regardless of whether the loop has technically "recovered." (Tanuj Garg, April 2026 — https://tanujgarg.com/blog/ai-agent-reliability-patterns)

**7. Log normalization for regression detection.** Collect error logs over a rolling 7-day window per normalized error signature (strip UUIDs, timestamps, request hashes). After deployment, compare observed error rates against baseline using Poisson probability. Flag any signature where `p < 0.05`. (Tian Pan, September 2025 — https://tianpan.co/blog/2025-09-22-self-healing-agents-in-production)

## Evidence

- **Case study — $47K runaway loop:** A mid-sized SaaS team ran a support-triage agent over a long weekend. No iteration limit, no budget cap, no alerting on token burn. The agent looped for 62 hours, generating $47,218 in API costs (130× a normal week). Root cause: no stop condition and no cost observability. Fix: iteration throttling, budget caps, and cost-per-task monitoring. (Rapid Claw, April 2026 — https://rapidclaw.dev/blog/ai-agent-rate-limiting-guardrails)
- **HN post — production database deletion:** A developer used Cursor's Plan mode (Claude Opus) with access to their Railway API token. The agent called the `volumeDelete` mutation and deleted the production database. Railway recovered the data, but the incident exposed: no deletion protection, 3-month-old backups on the same volume, and a token with full API access. HN commenters noted: "The agent didn't delete your database — you deleted your database. The agent was just the tool." (Hacker News, July 2026 — https://news.ycombinator.com/item?id=47911524)
- **Gartner research — market-scale failure:** Over 40% of agentic AI projects will be canceled by end of 2027 due to escalating costs, unclear business value, or inadequate risk controls. Contributing factor: "agent washing" — vendors rebranding chatbots as agents. Of thousands of vendors claiming agentic solutions, Gartner estimates only ~130 offer genuine agentic capabilities. (Gartner, June 2025 — https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027)
- **GitHub open source — AgentFuse:** A developer built and open-sourced AgentFuse, a local circuit breaker specifically to prevent runaway agent bills. Trips on repeated identical tool calls or exceeding configured thresholds for tokens/requests. Posted on HN with the explicit framing: "prevent $500 OpenAI bills." (Hacker News — https://news.ycombinator.com/item?id=46404312, https://github.com/AbdulBasitA/agent-fuse)
- **Engineering post — LangChain debugging:** LangChain agent debugging guide catalogs the specific failure modes: `OutputParserException`, `ValueError: Could not parse LLM output`, thought loops that burn through the iteration limit, agents that stop responding without raising any exception. Root causes: ambiguous tool descriptions, missing stop conditions, lack of iteration caps. (Mechanic AI, July 2026 — https://mechanicai.dev/blog/langchain-agent-debugging.php)

## Gotchas

- **Retry loops don't fix logic errors.** Adding retries helps transient failures but amplifies cost on hallucination-driven loops. You need semantic validation (Verifier Agent), not more retries.
- **Iteration limits without fallback are a cliff.** An agent that hits its iteration limit and halts is safe but useless. Always pair limits with a checkpoint-resume path or a clean handoff to human review.
- **Circuit breakers must reset.** A circuit breaker that trips and stays open forever means the agent is permanently dead. Implement a reset window (30–60s) and a max-trip-count before forcing human intervention.
- **Monitoring tools don't catch agent-level failures.** A 62-hour runaway loop generates no exceptions — the HTTP status is 200 throughout. You need agent-specific observability: token burn rate, iteration count, cost-per-task, and output quality signals, not just infrastructure metrics.
- **The agent is not the security boundary.** It is a tool. The security boundary is the API token scope, the permission model, and the blast radius controls you put around the tool. Treat the agent as a capable but fallible operator with no risk awareness.
