# S-1112 · The Elastic Step Stack — When Your Agent Fails But Can't Tell You Where It Stopped

You have a ten-step agentic workflow. Step 7 calls an external API, the call times out, and the agent is left holding state in memory with no record of what happened. Did step 7 execute? Did the downstream system receive it? The agent has no idea. This is not a model problem. It is an infrastructure problem — and it is the reason 86% of agent failures are recoverable, but most teams never recover them.

## Forces

- **The compounding reliability tax** — Chain ten steps each succeeding 85% of the time and the whole run finishes ~20% of the time. Better models do not fix network failures, only infrastructure does.
- **LLM self-correction is mostly verification in disguise** — Huang et al. (2023) proved LLMs cannot self-correct reasoning without external feedback. Every "reflection" loop that appears to work is really a verification loop using an external signal: a compiler, a test suite, a search result. Strip the external signal and self-correction consistently degrades output quality.
- **Agents don't crash, they plausibly drift** — Unlike traditional software, an agent that fails produces wrong output that compiles, passes tests, and ships as technical debt you discover three weeks later.
- **The scratchpad is a lossy compressor** — When LangChain's AgentExecutor summarizes scratchpad state to stay within context limits, step 12 may see "you called search_docs — here is a summary." The model re-derives and re-calls because, as far as it knows, it has not yet.

## The Move

Build a recovery layer that sits between every tool boundary and the agent's next step. The layer does four things:

1. **Classify the failure type before choosing a response.** Transient errors (429, 503, DNS) get exponential backoff retry. Semantic errors (malformed JSON, wrong schema) get re-prompt with corrective context. Resource errors (token overflow, budget cap) get payload reduction. Fatal errors (auth revocation, policy violation) get immediate abort with logging. Each class demands a different recovery — one try/except around the whole agent is worse than none.

2. **Checkpoint after every logical step, not every LLM call.** LangGraph's `MemorySaver` and Temporal's event-history replay are purpose-built for this. The checkpoint records: which tool was called, with what parameters, what it returned, and what the agent decided next. On crash or timeout, the workflow resumes from the last checkpoint, not from scratch. Claude Code's codebase is reportedly only 1.6% AI decision logic — the other 98.4% is operational infrastructure for context management, tool routing, and recovery.

3. **Treat write and connector tools with idempotency keys.** A retried email-send without an idempotency key duplicates the send. A retried database write without a deduplication check creates duplicates or conflicts. Read tools are safe to repeat. Write tools need an idempotency contract. Connector tools (webhook → downstream system) need both a retry contract and a confirmation check — the downstream system may have received the action but failed to return confirmation.

4. **Add a maximum step budget and an escalation path.** Set `max_iterations` with an early-stopping strategy (LangChain: `early_stopping_method="generate"`). Add `max_execution_time` as a secondary safety net. When the budget is exhausted, do not silently return — surface the partial result, log what completed, and escalate to human review. Optio's agent orchestration system feeds CI failures back to the agent as new context and re-runs automatically — but it has a defined stop condition.

## Evidence

- **Engineering blog (programa.space):** Detailed taxonomy of autonomous agent failure modes — action loops, auth failures, hallucinations, and recovery engineering patterns from Anthropic and Alibaba desktop-copilot deployments — [URL: https://programa.space/autonomous-agent-failure-modes-and-recovery-engineering-patt](https://programa.space/autonomous-agent-failure-modes-and-recovery-engineering-patt)
- **Research blog (Vadim's blog, March 2026):** Documents the 0.85^10 reliability math, the Claude Code infrastructure ratio, and why durable execution (checkpointing + replay) is the real answer to long-horizon failure — [URL: https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)
- **HN Show HN (Optio):** Open-source K8s agent orchestration that implements the feedback-loop recovery pattern — CI failures → agent context → automatic fix — [URL: https://news.ycombinator.com/item?id=47520220](https://news.ycombinator.com/item?id=47520220)
- **Community guide (bestaiweb.ai, updated July 2026):** Per-call retry contracts, retry/idempotency coupling, and the four-class error taxonomy (transient, semantic, resource, fatal) — [URL: https://www.bestaiweb.ai/topics/agent-error-handling-and-recovery/](https://www.bestaiweb.ai/topics/agent-error-handling-and-recovery/)
- **GitHub repo (steveandroulakis/temporal-langgraph-checkpoint-recovery):** Production-ready integration of LangGraph checkpointing with Temporal's event-history replay for crash recovery — [URL: https://github.com/steveandroulakis/temporal-langgraph-checkpoint-recovery](https://github.com/steveandroulakis/temporal-langgraph-checkpoint-recovery)

## Gotchas

- **Wrapping a retry around the whole agent is not resilience — it is roulette.** The retry needs to be scoped to the specific tool call that failed, with its own backoff and attempt count. Global exception handlers swallow the information you need to route the right recovery.
- **Idempotency is not optional for write operations.** If you retry a tool call that modifies state and do not include an idempotency key, you will duplicate side effects. This is the failure mode that produces double-emails, double-charges, and duplicate database records.
- **Self-correction requires an external signal, not introspection.** Asking the model "is this correct?" after every step consistently hurts accuracy on tasks requiring reasoning (Huang et al., 2023). Self-correction works when the model receives an objective test result, a compiler error, or a search result to react to — not when it re-reads its own output.
- **Context summarization is lossy.** When frameworks compress scratchpad state to fit context windows, step N loses fidelity about step N-3. The agent may not know it already completed a sub-task and re-execute it, creating loops. Profile your traces to identify where summarization is hiding completed work.
- **Gartner projects 40%+ of agentic AI projects cancelled by 2027** — not due to model quality, but because the systems around the model are not built for failure. The differentiator is not the LLM, it is the recovery infrastructure.
