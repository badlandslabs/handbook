# S-1225 · The Grounded Recovery Stack — When Your Agent Fails But Cannot Tell Success From Failure

When an agent's tool call times out, a rate limit hits, or the agent declares victory prematurely — the system must detect the failure, decide whether to retry, and know when to stop. Unstructured agents either retry forever or give up silently. Grounded recovery makes failure legible to the agent and to operators.

## Forces

- **Uncertainty vs. action** — Agents lack internal sensors for "this failed." They optimistically continue or give up entirely.
- **Retry loops vs. silent failures** — Without hard stops, agents waste tokens retrying dead ends. Without retries, transient failures cascade into permanent ones.
- **Recovery vs. over-engineering** — Building circuit breakers and rollback logic for every tool is expensive; not building them means one bad run can trash your data or burn your budget.
- **Intrinsic self-correction is unreliable** — Research through 2025 consistently shows that prompting "check your work" without external grounding degrades accuracy rather than improving it.

## The Move

Three interlocking layers: **structured error taxonomy, bounded retry with escalation, and post-failure state recovery.**

### Error taxonomy before retry logic

Classify every failure into one of four categories before choosing a recovery strategy. Different categories need different fixes.

| Category | Example | Recovery |
|---|---|---|
| **Transient** | 429 rate limit, timeout, 503 | Retry with exponential backoff |
| **Semantic** | Malformed JSON, wrong tool name, schema violation | Re-prompt with parse error appended |
| **Resource** | Token budget exceeded, context overflow | Truncate/summarize context, then retry |
| **Terminal** | Policy violation, ambiguous input | Stop and escalate to human |

### Bounded retry with circuit breakers

Set hard limits at three levels:

- **Per-tool retry cap** (e.g., 3 attempts per tool before switching to fallback)
- **Same-error rule** — if the same error fires twice in a row, stop retrying that path
- **Global circuit breaker** — after N consecutive failures on an upstream service, fail fast for a cooldown window rather than burning money on 1,000 failing calls

```
Error → classify → transient? → retry with backoff
                    ↓ no
              semantic? → re-prompt + retry (1x)
                    ↓ no
              resource? → truncate context + retry
                    ↓ no
              → terminal → stop + log + escalate
```

### Post-failure state recovery

For multi-step workflows, failure mid-run must not leave dangling state. The rollback principle: either the entire operation completes or it looks like nothing happened.

- Log the failure type, tool name, error code, payload size, retry count, recovery action, and final outcome
- Clean up partial writes (e.g., half-created files moved to a draft/error folder)
- Surface the error state explicitly in the agent's next turn rather than retrying blindly
- For batch operations: process individually, retry only failures, track per-item results — don't fail the whole batch for one bad item

### LLM-as-judge for outcome verification

When the agent claims success, use a separate verifier to confirm. Production teams split into two tiers: GPT-4o or Claude 3.7 Sonnet for high-stakes gating; small distilled judges (3B–8B models) for high-throughput inline checks. Small models deliver ~97% cost reduction at 0.88–0.95 accuracy for routine verification.

## Evidence

- **Enterprise failure analysis:** 86% of agent failures are recoverable, but Gartner predicts 40%+ of agentic AI projects will be cancelled by 2027 — primarily because the systems around them aren't built to handle failure. — [AgentMode AI](https://agentmodeai.com/agentic-ai-failure-case-studies), April 2026
- **Production error taxonomy:** Classify errors before retrying — transient errors (rate limits, timeouts) need backoff; semantic errors (schema violations) need re-prompting; resource errors need context truncation; terminal errors need human escalation. — [Neel Mishra, Agent Error Handling](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Open-source implementation:** The `reflect` MCP server (Rust) implements the Reflexion paper as a production tool — agents store failures in SQLite with error type, trigger context, and lesson, making patterns searchable across sessions. — [rohansx/reflect on GitHub](https://github.com/rohansx/reflect)
- **HN discussion:** The minimal agent loop (LLM + tools + while loop) works surprisingly well; 95% of the "magic" is in the LLM and its tool-call fine-tuning, not the orchestration. Failure handling is where complexity concentrates. — [Hacker News, 43998472](https://news.ycombinator.com/item?id=43998472)
- **Real-world case study:** A Cursor IDE user documented 6 months of endless agent loops — root causes were infinite analysis cycles, task-list amnesia (repeating completed items), and context collapse (sudden reversion to old conversations). Fixes: max iterations per file, explicit task state persistence, periodic context summarization. — [dreyson.com](https://dredyson.com/how-i-fixed-cursors-endless-agent-loops-a-6-month-case-study-from-real-world-development/)
- **LangGraph fault tolerance:** LangGraph models agents as graph nodes with configurable retry policies per node. When retry policy exhausts, execution halts explicitly — nothing fails silently. Recovery nodes and conditional edges handle graceful continuation. — [LangChain Blog](https://www.langchain.com/blog/fault-tolerance-in-langgraph)
- **LLM-as-judge production stats:** 57%+ of surveyed production agent teams use judge LLMs at runtime. Intrinsic self-correction ("check your work" prompt) degrades accuracy without external grounding. — [Zylos Research, April 2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

## Gotchas

- **Don't retry everything.** Transient errors benefit from retry; terminal errors (policy violations, ambiguous inputs) just waste tokens and may make things worse on retry.
- **"Check your work" is not reliable.** Intrinsic self-correction without external grounding consistently degrades outcomes. Use an LLM-as-judge or structured output validation instead.
- **Loops look like progress.** An agent burning tokens in a tight retry loop looks identical to one making real headway. Log the error history, not just the current state.
- **Partial success is common.** 30% of autonomous agent runs hit exceptions mid-execution. Batch operations that fail all-or-nothing waste the successful items. Process individually and track per-item outcomes.
- **Context truncation creates new errors.** Summarizing context to fit a window can remove the exact detail the agent needed. Preserve critical fields during truncation, or store them in a scratch-pad tool the agent can query.
