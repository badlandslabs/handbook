# S-1230 · The Dead Agent Walking Stack — When Your Agent Fails but Returns 200 OK

Your agent just finished a task and returned a clean response. The API returned 200. Nothing threw an exception. But the answer is wrong — subtly, dangerously wrong. A financial agent misinterpreted a ticker symbol. A logistics agent sent a package to the wrong address. A content agent published hallucinated citations. This is the dead agent walking problem: AI agents fail silently, returning HTTP 200s for fundamentally broken outputs. Unlike traditional software that crashes loudly, agentic systems keep running while producing plausible garbage. This stack is about detecting that, bounding it, and recovering from it.

## Forces

- **Agents fail sideways, not forward.** A traditional app crashes. An agent returns a bad answer and marks the task complete. Your monitoring sees nothing — because nothing errored.
- **Self-correction can loop forever.** The natural response to "it failed, try again" is a retry loop. Without hard bounds, agents will spend token budget retrying a fundamentally broken approach until the cost eats your margin.
- **Retry != recover.** Retrying the same tool with the same inputs produces the same failure. Real recovery requires changing the inputs, the tool choice, the model, or the approach — not just the same call again.
- **The trust boundary is blurry.** Agents that can self-correct are agents that can self-harm. The more recovery power you give them, the larger the blast radius when recovery goes wrong.
- **Escalation friction kills adoption.** If the only recovery option is "file a ticket and wait," teams just suppress errors and ship broken results rather than admit failure.

## The move

**Build a layered failure cage — detect, bound, correct, escalate.**

1. **Hard guardrails first.** Set `MAX_STEPS = 12` (or 8-15 depending on task complexity), a per-run token budget (default $1), and a wall timeout. These are not guidelines — they are circuit breakers. When any trip, stop the agent, log the full trace, and route to escalation. A hard stop is always better than a silent runaway.

2. **Descriptive tool errors, not HTTP codes.** Wrap tool responses so a failed search returns "Search failed: no results for 'X', tried Y and Z" rather than a 500 with an empty body. The agent needs to *reason over* the failure, not just retry it. Feed failure context into the next reasoning step.

3. **Per-tool retry with exponential backoff — max 2-3 attempts.** If a tool call fails, retry it once or twice with backoff. After that, the failure is structural — the tool, the input, or the environment is wrong. Do not keep retrying the same broken thing.

4. **Whole-agent fallback to a larger model on hard failures.** When the agent exhausts retries and hasn't completed, escalate to a more capable model for one final attempt. This is distinct from per-tool retries — it's a "the approach itself might be wrong" signal.

5. **Escalation hook on terminal failure.** When the agent hits a hard limit (step cap, budget, or final fallback failure), it should not return a broken result. It should create a human ticket, email a queue, or surface a "needs review" flag. The agent says "I couldn't complete this" rather than fabricating a completion.

6. **Log everything per run — input, steps, tools called, outputs, cost, latency.** Aggregate to find: which agents loop most? Which tools error most? Which prompts are expensive? This feeds back into eval and prompt refinement. Per-run traces are also your only debugging surface when the silent failure surfaces in production.

7. **Idempotency on all agent actions.** If retrying causes a duplicate email send or double booking, you have a data-integrity problem. Design tool actions with idempotency keys or check-before-act semantics so retries don't cause side-effect duplication.

## Evidence

- **Blog post:** "LLM Agent Error Recovery in 2026 — Patterns That Don't Loop Forever" — documents the MAX_STEPS pattern, per-tool retry with backoff, whole-agent model fallback, cost caps, and escalation hooks as the concrete production-ready checklist. Recommends MAX_STEPS=12, per-run cost cap of $1, and descriptive error wrapping as the minimum viable failure cage. — [https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **GitHub repo:** Vectara's "awesome-agent-failures" — community-curated list of agent failure modes including tool hallucination (tool returns wrong data, agent acts on it), response hallucination (agent invents output inconsistent with tool results), and infinite loops. Documents the failure taxonomy that makes silent errors so dangerous. — [https://github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Blog post:** "Practical AI Agent Failure Recovery Methods for Production Systems" (AgentReviews, May 2026) — describes silent misclassification as the primary production failure mode: the agent returns 200 OK while routing a financial transaction incorrectly or publishing a wrong answer. Recommends deterministic fallbacks, observability on every run, and human-in-the-loop checkpoints for high-stakes actions. — [https://agentreviews.dev/blog/ai-agent-failure-recovery-methods](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)
- **Show HN / GitHub:** TensorPool Agent — autonomous recovery for distributed training jobs. Shows real-world deployment where agents babysit long-running GPU training jobs, auto-recovering from failures. HN commenters raised the key trust question: how much control should a bot have? Demanded smarter progress checks to detect zombie jobs (agent thinks it's working, but the job is stalled silently). — [https://news.ycombinator.com/item?id=46812909](https://news.ycombinator.com/item?id=46812909)
- **GitHub repo:** Agentic Reliability Framework (petterjuan) — separates decision intelligence (OSS, advisory only) from governed execution (Enterprise). Explicitly models the failure mode where giving agents autonomous recovery power creates a blast radius problem. Solution: let the agent diagnose and recommend, let a governed layer execute. — [https://github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Engineering blog:** Anthropic's "Building Effective AI Agents" — recommends starting with direct LLM API calls rather than heavy frameworks for agentic systems. HN discussion (543 points, 88 comments, June 2025) surfaced consensus that simpler patterns (ReAct-style loops, few lines of code) outperform heavy orchestration frameworks for most agent use cases. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Hard step caps only work if they're actually enforced.** Setting MAX_STEPS=12 and then letting the loop run one more time "just this once" defeats the purpose. Make it a hard exception, not a warning.
- **Retrying without changing inputs is not recovery.** If a tool fails because it returned bad data (RAG hallucination, stale index), retrying it returns the same bad data. Recovery requires changing something — different query, different tool, different model.
- **Agents can loop in subtle ways.** Not just "same tool called 50 times" — an agent can loop by cycling through a 3-step pattern that never converges. Pattern detection (are we seeing the same tool calls with the same inputs?) catches this where step counts don't.
- **Cost controls are easy to forget until the bill arrives.** Set per-run and per-step token budgets before production, not after. Budget libraries (Thskyshield, AgentGuard) offer per-org policy enforcement — useful when you have multiple teams shipping agents.
- **Idempotency is often an afterthought.** Tool actions that modify state (send email, book appointment, write to DB) must survive retry. If you're adding retry logic, add idempotency keys at the same time.
