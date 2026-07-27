# S-1735 · The "Failure Is Not the Crash" Stack — When Your Agent Pretends to Work

You have a production agent running smoothly. Logs show no errors. But it shipped wrong data, looped 47 times, and burned $50 in tokens on one session — silently. The crash isn't the failure. The failure is when the agent succeeds at the wrong thing.

## Forces

- Agents fail *quietly* — they produce plausible output, return HTTP 200, and keep running even when deeply wrong
- Every tool call in a chain multiplies failure probability: 95% reliability × 95% × 95% × 95% = 81% end-to-end
- Traditional try/catch doesn't cover semantic errors (valid JSON with wrong content) or agentic loops (no exception thrown)
- A bug in your prompt can make an agent loop 50 times and cost real money before you notice — unlike a crash, there's no alert
- Multi-step causality: failure at step 8 is often caused by a bad decision at step 2, making the actual break invisible

## The Move

Layer defense in three zones: **prevent**, **detect**, **recover**. Each zone handles different failure modes.

### Prevent — Stop loops before they start

- **Hard step caps**: Set a recursion limit and stop unconditionally. For LangGraph: `recursion_limit=12`. This is the single most important guardrail. A step cap doesn't care why the agent is looping — it just stops it. Without one, a single bad prompt can generate runaway costs.
- **Cost circuit breakers**: Budget limits that halt execution when token spend crosses a threshold mid-session. Prevents silent cost explosions from prompt bugs. A bug in your system prompt is indistinguishable from a good prompt at runtime — only the budget cap catches it.
- **Negative constraints**: Agents are good at following instructions on *what to do*. Be explicit about *what not to do* — don't retry the same tool more than N times, don't call the same API with the same query, stop when progress plateaus.

### Detect — Make failure visible

- **Error classification before retry**: Classify the error type before branching into recovery. A 401 retry wastes tokens and time. A semantic error (valid JSON, wrong schema) needs different handling than a transient error (429, 503, timeout). Always inspect the HTTP status code or error pattern first.
- **Tool output validation**: Agents often loop because they can't parse tool output. Generic error messages like `"Error: 400"` give the LLM no signal to try a different approach — it retries the exact same request. Return structured, diagnostic error messages from tools that tell the agent *why* it failed and *what to try next*.
- **Structured run logs**: Before shipping, instrument every step with a trace: what did the agent decide to do, which tools did it call, in what order, what did each tool return. Without execution traces, you're debugging blind. This is not optional for production.

### Recover — Graceful degradation paths

- **Exponential backoff with jitter** for transient errors (429, timeout, 503): `delay = min(base × 2^attempt + random(0, jitter), max_delay)`. Jitter prevents synchronized retries from creating thundering herd problems across distributed agents.
- **State checkpointing**: Save execution state at defined boundaries (step completion, tool call, decision point). On failure, resume from the last checkpoint instead of restarting from scratch. Critical for long-running workflows and anything that can't tolerate wasted work. Open-source tooling exists specifically for durable agent checkpoint/restore.
- **Fallback chains**: When a tool fails persistently, don't let the agent retry into a hole. Have a defined fallback — try a different tool, use a cached result, return a partial answer, or escalate to human review. The agent should never be left holding a failed state with no path forward.
- **Graceful degradation output**: When recovery fails completely, the agent should return a structured failure response with what it tried, what went wrong, and suggested next steps — not silence.

## Evidence

- **DEV Community (The Daily Agent):** Real production failure case — customer support triage agent burned 47,000 tokens calling `search_knowledge_base` 73 times in a row. Root cause: ambiguous tool output with no negative constraint telling the agent to stop. Fix: step caps + structured error messages + negative constraints on retry counts. — [https://dev.to/thedailyagent/5-ai-agent-failures-in-production-and-how-to-fix-them-2nm0](https://dev.to/thedailyagent/5-ai-agent-failures-in-production-and-how-to-fix-them-2nm0)
- **Blog (Manvendra Rajpoot, May 2026):** Documents cost circuit breakers as a production necessity. A prompt bug can make an agent loop 50 times and burn $20 in tokens before human notice. Recommends hard step caps (`recursion_limit=12` for LangGraph) and per-session budget limits as the primary guardrails. — [https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **r/LocalLLaMA production discussion:** Practitioners report token bloat of 6–8x from intermediate reasoning steps in multi-step tool chains. Consensus approach: separate LLM reasoning from orchestration logic, use deterministic code for control flow, let LLMs focus on tasks they're genuinely good at (extraction, categorization) rather than loop management. — [https://www.reddit.com/r/LocalLLaMA/comments/1qh8xj6/those_of_you_running_agents_in_productionhow_do/](https://www.reddit.com/r/LocalLLaMA/comments/1qh8xj6/those_of_you_running_agents_in_productionhow_do/)
- **Hacker News (Ask HN, testing agents):** Community reports that Gartner estimates 40%+ of agentic AI projects will fail by 2027. Specific failure mode cited: silent misbehavior when context window fills — no exception, no error code, just wrong output returned as HTTP 200. — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **GitHub (phoenix-assistant/agent-checkpoint):** Open-source library specifically for durable checkpoint/restore of agent cognitive state — enables resuming from provider outages or "intelligence brownouts" (model quality degradation) without restarting from scratch. — [https://github.com/phoenix-assistant/agent-checkpoint](https://github.com/phoenix-assistant/agent-checkpoint)

## Gotchas

- **Step caps alone aren't enough**: A step cap stops the loop but doesn't tell you *why* it looped. Pair it with structured logging so the failure is diagnosable after the fact.
- **Retry without classification amplifies failures**: Hammering a 401 endpoint wastes tokens. Hammering a 429 endpoint can get you rate-limited longer. Classify first, then branch.
- **Silent success is the worst failure mode**: The agent returned a result. There's no exception. But the data is wrong, the action was wrong, or the reasoning was wrong. You only catch this with output validation — schema checks, semantic assertions, or human review gates on high-stakes actions.
- **Context window exhaustion is invisible**: When the context fills, agents don't error — they start ignoring earlier context, including the original instructions. The fix is proactive: monitor context usage and trigger a summarization or checkpoint before the window fills.
