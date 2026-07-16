# S-1169 · The Multi-Level Degradation Ladder — When Your Agent Can Only Succeed or Fail

When your production agent hits a rate limit, a malformed tool response, or an oversized context window — and its only two options are retrying blindly until something works or crashing entirely. Binary failure modes are expensive: a crashed agent wastes all prior work and requires a full restart. Your agent needs a staircase, not a cliff.

## Forces

- **Token layers compound invisibly.** A 4-step tool pipeline (scrape → extract → transform → save) generates 3–4x token overhead from LLM reasoning between steps. When a middle step fails, retrying with full context re-burns that overhead every attempt.
- **Retry amplification is real.** Blind retries on a 429 rate-limit error don't just slow down — they deepen the rate limit, creating a thundering-herd problem where your recovery attempt makes things worse.
- **Context preservation vs. cost tension is unresolved.** The $47K multi-agent loop incident happened partly because 4 agents each accumulated full conversation history with no summarization between them. But truncating context loses recovery information.
- **Aggressive autonomy kills safety; conservative safety kills utility.** A hard `max_iter = 5` prevents loops but kills long legitimate tasks. The right threshold is domain-dependent and changes over time as the agent matures.

## The move

Design a **6-level degradation ladder** for every agent workflow. At each level, the agent keeps working — just with less convenience, less context, and fewer tools.

1. **Full context, all tools, primary model.** Normal operation. No tradeoffs.
2. **Retry with exponential backoff** (transient errors: 429 rate limits, 500/503 server errors, timeouts). Double wait time per retry, cap at 3–5 attempts. This is where LiteLLM-style automatic provider failover lives.
3. **Switch to backup model** (LiteLLM `fallbacks = [{"gpt-4o": ["gpt-4-turbo", "gpt-3.5-turbo"]}]`). Handles permanent model-side failures — rate limits that don't clear, context-length errors, policy violations.
4. **Reduce context** — summarize the conversation, drop the oldest messages, keep the last N turns and tool results. This is the hardest trade: you lose detail but stay within budget.
5. **Fall back to a simpler tool set** — disable complex tools (database queries, multi-step web scrapers), keep only file read/write and a single search API. The agent completes a degraded but safe version of the task.
6. **Human escalation with full context preserved** — surface what the agent tried, where it failed, and what degraded steps it went through. The human receives a complete briefing, not a crash dump.

Each level has an explicit trigger (what condition activates it), an explicit action (what changes), and an explicit recovery condition (when to climb back up).

Layer in **schema validation at every tool-call boundary** (Zod/Pydantic). LLMs generate malformed JSON, missing fields, wrong types. Converting untrusted LLM output to typed, safe data *before* execution prevents bad tool calls from propagating — it's the cheapest possible failure interrupt.

Layer in **iteration budget guards**: set `max_iter` to 5–8 per agent in CrewAI/LangChain (not the default 25). Beyond that, you are in runaway territory. Complement with semantic loop detection — comparing recent state snapshots for convergence — for tasks that legitimately need more steps.

## Evidence

- **Multi-level degradation sequence documented (Preporato, May 2026):** Concrete 6-level ladder with specific escalation triggers. Key insight: "The agent keeps moving — just with less convenience at each level." — [Preporato — Error Handling in AI Agents: Circuit Breakers, Retry & Recovery](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)
- **$47K incident — no degradation ladder:** 4-agent LangChain A2A system ran undetected for weeks with no iteration cap, no budget guard, no context summarization. Week 1: $127 → Week 4: $18,400 → Total: $47,000 before shutdown. No degradation path existed — the only options were "keep running" or "kill it." — [Towards AI — We Spent $47,000 Running AI Agents in Production (Oct 2025)](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)
- **LiteLLM automatic provider failover:** `fallbacks = [{"gpt-4o": ["gpt-4-turbo", "gpt-3.5-turbo"]}]` — handles 429, 500, 503, timeout, context-length errors with configurable retry counts. Widely deployed in production agent frameworks. — [LiteLLM Docs — Fallbacks](https://docs.litellm.ai/docs/proxy/reliability)
- **Schema validation at boundary (Google ADK + production data):** LLMs generate malformed JSON at ~2–8% of tool calls without schema validation. Runtime Pydantic/Zod validation converts untrusted output to typed data before execution. — [Understanding Data — Tool Call Validation (2026)](https://understandingdata.com/posts/tool-call-validation) + [Medium — Malformed Function Call Errors in Multi-Agentic Systems (Google ADK, 2026)](https://medium.com/@mukrimenurgumus/malformed-function-call-errors-in-multi-agentic-systems-d7462a33b91b)
- **max_iter production guidance:** AgileSoftLabs post-mortem on CrewAI production deployments recommends 5–8 iterations per agent as the safe threshold — the default of 25 is a loop amplifier, not a capability setting. — [AgileSoftLabs — CrewAI in Production 2026: Real Lessons (June 2026)](https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons)
- **AgentBudget (open source):** Python SDK enforcing per-session dollar limits on AI agents. Wraps LLM calls, tracks cumulative spend, triggers `HardLimitExceeded` when budget is hit. Supports LangChain/LangGraph via `LangChainBudgetCallback`. 166 commits, Apache-2.0. — [AgentBudget GitHub (2026)](https://github.com/AgentBudget/agentbudget)

## Gotchas

- **The ladder is not free — it adds latency.** Each degradation level introduces a decision and a re-prompt. Design the ladder to short-circuit on known-fatal errors (auth failures, policy violations) — those should abort immediately, not walk the ladder.
- **Context summarization destroys recovery state.** When you drop old messages to reduce context, you lose the trace of *why* the agent made prior decisions. If the failure was semantic (wrong approach, not transient), the agent restarts without the lesson.
- **Model fallbacks introduce quality variance.** Falling back from GPT-4o to GPT-3.5-turbo changes the agent's reasoning quality mid-workflow. Some tasks (code generation, multi-step reasoning) degrade non-linearly — you may prefer escalation to human over a degraded model answer.
- **Hard iteration caps kill legitimate long tasks.** A hard cap of 5–8 is right for early-stage agents. As the agent matures and you accumulate per-object reasoning traces (S-1165), you can relax it for domains where longer runs are provably safe.
- **Dead-end states bypass the ladder entirely.** A terminal non-final state (S-1165) — where the agent enters a safety state with no outbound transition — never triggers a degradation. The ladder only helps if the agent can *attempt* the next level. Silent dead-ends require separate detection: state-reachability checks or explicit end-state enumeration.
