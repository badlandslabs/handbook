# S-2405 · The Silent Failure Stack

When your agent returns a confident wrong answer, loops for 35 minutes, or goes dark mid-task — and your system has no idea it happened.

## Forces

- **Agents fail probabilistically, not with exceptions.** A bad LLM response looks identical to a good one. An API 429 is a 200 with a payload you forgot to check. There is no stack trace for a hallucinated tool argument.
- **Recovery depth trades off against cost.** A blind retry is cheap but ineffective for semantic failures. A full LLM-powered self-correction loop fixes more but burns tokens on every failure.
- **Longer tasks demand state persistence, which demands cost.** A 10-step research task that dies at step 9 must not restart from zero — but checkpointing every node adds overhead and storage.
- **Escalation gates irreversible actions, but humans are slow.** You need them for safety, but a 3-hour SLA on human review defeats the purpose of an autonomous agent.
- **Retry storms cascade.** If a downstream API is genuinely down, 100 agents retryting simultaneously keeps it down.

## The Move

Layer four distinct failure-handling mechanisms, from cheapest to most expensive. Each layer handles a different failure mode.

**Layer 1 — Hard Guards (always on, zero LLM cost)**
- Step cap: hard-limit agent reasoning loops (e.g., 50 steps). When hit, return best-effort result or escalate — never loop forever.
- Per-call timeout: enforce wall-clock limits on every tool call and LLM invocation (e.g., 90s for LLM, 30s for file operations). Kill and retry rather than hang.
- Cost circuit breaker: if cumulative spend on a single task exceeds a threshold (e.g., $2.00), halt and alert. Prevent runaway token accumulation.

**Layer 2 — Structured Error Classification (deterministic, cheap)**
Before attempting recovery, classify the failure type to route to the right handler. The Agentic Command Center project defines a clean taxonomy:
- `missing_tool` / `missing_dependency` → install, then retry
- `rate_limit` → exponential backoff, then retry
- `api_error` → retry with jitter, up to N attempts
- `logic_error` → escalate to Layer 3 self-correction
- `hallucination` / `contradiction` → escalate to Layer 3 self-correction
- `max_retries_exceeded` → escalate to human or degraded fallback

**Layer 3 — LLM-Powered Self-Correction (token cost, semantic understanding)**
When deterministic handlers cannot fix the error, invoke the agent itself to reason about the failure: read the error message, examine the last N tool outputs, hypothesize the cause, try an alternative approach. The Agentic Command Center enforces this reflex: the agent must run the classify → route → fix → retry loop before ever reporting failure to a human. This is the self-healing loop — not magic, but a structured retry with LLM-level reasoning as the recovery instrument.

**Layer 4 — Human Escalation and Graceful Degradation (bottleneck, but necessary)**
For unrecoverable failures or high-stakes actions: surface the error with full context (error type, step count, what was attempted, what was produced so far) to a human. While waiting, serve a degraded but functional response — cached result, simplified output, or partial answer — rather than an error page.

**Checkpointing as the persistence backbone**
LangGraph (GA since October 2025) persists agent state at every node transition via `SqliteSaver` or `PostgresSaver`. If the process crashes at minute 9 of a 10-step task, execution resumes at the beginning of the node where failure occurred — not from step 1. Smaller nodes mean more frequent checkpoints and less wasted work on recovery. This is the difference between a 2-minute recovery and a full restart.

## Evidence

- **GitHub repo + HN Show:** The `msstrategies/agentic-command-center` project (MIT, 2026) publishes a verbatim `autonomous-self-healing.md` rule enforcing a 5-step CLASSIFY → ROUTE → FIX → RETRY → ESCALATE loop on every tool failure. The README explicitly states: "Never stop on solvable errors. Never ask when you can decide. Recover from failures instead of reporting them." — [github.com/msstrategies/agentic-command-center](https://github.com/msstrategies/agentic-command-center/blob/main/.claude/rules/autonomous-self-healing.md)
- **Engineering blog + production case study:** The GetATeam blog (Nov 2025) documents a production incident where an unhandled API timeout cascaded into complete system failure — 47 Slack alerts, 23-minute recovery. Their fix: exponential backoff, step-level timeouts, graceful degradation. Result: uptime from 94.2% → 99.7%, MTTR from 23 minutes → 2 minutes. — [blog.geta.team](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/)
- **Open-source framework (checkpointing):** LangGraph's state-machine architecture treats each node as a checkpoint boundary. The official docs and production guides (e.g., ActiveWizards, SparkCo, 2025–2026) recommend `PostgresSaver` for production — pause/resume across crashes without rebuilding state. LangGraph 1.0 went GA in October 2025 after production use at Uber, LinkedIn, and Klarna. — [github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)
- **Community documentation:** The Loop Engineering Workbench (community wiki, 2026) catalogs real failure scenarios — LLM API rate limits during bulk operations, context stuffing causing slow inference, external tool hangs — and prescribes timeouts, checkpoint/resume, and circuit breakers as the production-standard fixes, citing Claude Code, Aider (30K+ stars), OpenHands, and SWE-Agent (15K+ stars) as real-world precedents. — [loopengineering.wiki](https://loopengineering.wiki/tutorials/production-loops/loop-timeout-solutions)

## Gotchas

- **Model refusal is not an error code.** Claude Opus and similar models return HTTP 200 even when refusing a request. Check the response payload, not just the status code — or you'll never know the agent bailed.
- **Retries without backoff create retry storms.** 100 agents retrying a rate-limited API simultaneously will keep it rate-limited. Use exponential backoff with jitter, or a circuit breaker that trips when error rate exceeds a threshold (e.g., 5% over 1 minute).
- **Checkpointing only helps if nodes are small.** If a single node does 30 tool calls, a crash at step 28 of that node redoes all 28. Break large tasks into small, checkpointable nodes.
- **Step caps stop loops but don't fix semantic failures.** An agent hitting its step cap with a wrong answer still returns a wrong answer. Step caps are a guardrail, not a recovery mechanism — pair them with self-correction.
