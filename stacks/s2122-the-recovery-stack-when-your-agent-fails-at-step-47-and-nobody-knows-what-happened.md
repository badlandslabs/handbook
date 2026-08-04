# S-2122 · The Recovery Stack — When Your Agent Fails at Step 47 and Nobody Knows What Happened

Your agent works perfectly in demos. In production, it fails at step 47 of 50 — corrupts a partial database write, burns 250,000 API calls in a retry loop, and leaves the user with an email that was sent but never recorded. The problem is not that the agent failed. The problem is that the failure was silent, the state was lost, and the recovery path was never designed. Agentic systems need failure handling that goes far beyond try/except.

## Forces

- **Non-determinism makes retry the wrong word** — retrying an LLM call replays the model, costs money, and produces a different answer. "Retry from step 47" is not the same as "resume from step 47."
- **Partial progress is the default failure mode** — an agent completing steps 1–4 of 8 leaves your system in a state that is neither clean nor fully updated. Rerunning from step 1 charges the card again.
- **The mechanisms designed to keep agents running are the most likely to run them off a cliff** — a retry loop without a ceiling is a runaway process. 1,279 Claude Code sessions proved this in a single day.
- **Error categories require different recovery paths** — a 429 rate limit and a confident wrong answer demand opposite responses. Treating them the same leaves semantic failures undetected.

## The Move

Build a layered failure handling system. At each layer, use the right recovery primitive:

**Layer 1 — Transient failures (API timeouts, network blips, rate limits)**
- Exponential backoff with jitter: double the wait time between attempts, add a random 0–100ms offset to prevent thundering herd. Target: 3 retries with base delay of 1s.
- Always honor `Retry-After` headers — don't guess when the API wants to be called again.
- Budget the retries. Every retry path needs a counter. Log when you hit the ceiling so you know when the agent is cycling without making progress.

**Layer 2 — Cascading failures (downstream API, service degradation)**
- Circuit breaker: after N consecutive failures, stop calling the service. After a cooldown period, allow a "probe" request. If it succeeds, close the circuit. Reduces false-positive retry storms by ~80%.
- Tuned thresholds matter more than the pattern. A threshold too low opens the circuit on normal variance; too high and it doesn't protect.

**Layer 3 — Stateful failures (process crash mid-workflow, OOM kill, pod eviction)**
- Checkpoint state after every logical step. The saved state is the agent's memory of what it has already done. On restart, resume from the last checkpoint — not the beginning.
- Use a durable execution engine (Temporal, LangGraph checkpointer, Pydantic AI with Temporal support, Vercel AI SDK 7 durable layer) to make this automatic. The engine quarantines every non-deterministic call (LLM invocations, tool calls) as a replay-proof activity — on restart, the engine replays the orchestration but never replays the thinking.
- Key primitive: idempotency keys on tool calls. Save tool outputs keyed by input hash. On replay, return the saved output instead of re-executing. This prevents duplicate charges, duplicate writes, and duplicate side effects.

**Layer 4 — Semantic failures (LLM returns valid but wrong output)**
- Schema validation catches malformed responses immediately. Pydantic validation on tool call outputs reduced undefined tool errors by ~60% in production systems.
- Cross-validate outputs against known constraints before accepting them. A payment confirmation should match expected amount and currency before the agent treats it as success.
- Fallback chain: when primary model produces a semantic failure, route to a secondary prompt, a different model, or a structured extraction step. Never let a wrong-but-valid response silently propagate.

**Layer 5 — Escalation (agent has exhausted recovery paths, needs human judgment)**
- Human-in-the-loop queue: preserve full workflow state (checkpoint + failure context), surface the failure clearly to a human reviewer, and resume from that exact state after the review. Do not ask the human to re-explain the task.
- The EU AI Act and enterprise procurement now treat human oversight as a compliance requirement, not a feature. For high-stakes domains (finance, legal, compliance, healthcare), Layer 5 is non-negotiable.

**Diagnosis — when you don't know why it failed**
- Post-hoc trace analysis: tools like `agent-triage` extract behavioral rules from system prompts, replay conversations step-by-step using an LLM-as-judge, and flag which turn broke, which agent caused it, and how failures cascade across routing and retrieval.
- Classify failures into five buckets: tool selection, tool arguments, tool execution, state/orchestration, and recovery policy. Most tool-calling failures start in one layer and amplify through weak validation in another.

## Evidence

- **GitHub issue:** Claude Code auto-compact entered an infinite retry loop after a macOS sleep, creating 27 subagent files, 4,246 API requests, and ~695M cache-read tokens — exhausting the session rate limit without any user interaction. Labels on the issue: `area:api`, `area:cost`, `bug`, `has repro`. — [github.com/anthropics/claude-code/issues/22758](https://github.com/anthropics/claude-code/issues/22758)
- **Blog post:** TensorPool Agent monitors distributed training jobs across GPU clusters, automatically diagnoses failure root cause (Xid errors, S3 checkpoint corruption), restarts from the last valid checkpoint, and re-allocates resources. Over 100,000 multinode training GPU hours handled. Graduated Y Combinator. — [TensorPool Agent — Hacker News](https://news.ycombinator.com/item?id=46812909) and [TensorPool Docs](https://docs.tensorpool.dev/features/agent)
- **Open-source tool:** `agent-triage` (converra/agent-triage) analyzes production agent traces, extracts behavioral rules from system prompts, replays step-by-step with an LLM-as-judge, and produces aggregated root-cause reports. No telemetry — only LLM API calls leave the machine. MIT license. — [github.com/converra/agent-triage](https://github.com/converra/agent-triage)
- **Blog post:** AgentMarketCap analysis: 40% of agentic AI projects will be abandoned by 2027 not because the models failed but because the pipelines did. The incident that illustrates this: 1,279 Claude Code sessions ran 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. — [Self-Healing Agent Pipelines 2026 — AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery)
- **Blog post:** Vadim's LangGraph durability analysis: "Only 1.6% of Claude Code's codebase is AI decision logic; the other 98.4% is operational infrastructure for context management, tool routing, and recovery." Math of failure: 10 steps × 85% success rate = ~20% overall success without durability. — [Durable Execution in LangGraph — Vadim's Blog](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)
- **Blog post:** PADISO error taxonomy study: 5–20% median error rate for production AI agents; 30–40% of initial production failures are syntactic (easiest to automate); Pydantic validation reduces undefined tool call errors by ~60%; 0.1% manual intervention rate for invoice reconciliation at 500K+ transactions/month. — [AI Agents in Production: Error Recovery and Retries — PADISO](https://www.padiso.co/blog/ai-agents-in-production-error-recovery-and-retries/)

## Gotchas

- **Naive retry burns money without fixing the problem** — a rate-limited API that returns 429 needs a backoff, not a re-send. An LLM that produced wrong output needs a different approach, not the same prompt again. Match the recovery to the failure class.
- **"Resume" and "replay" are different operations** — replay re-executes from a checkpoint (incurring LLM costs, potentially producing different outputs). Resume uses the checkpoint's outputs directly and continues from the next pending step. Use durable execution engines to make this distinction automatic, or implement idempotency keys on every tool call by hand.
- **The replay trap for LLM calls** — if you implement your own retry logic for agentic workflows and don't record tool outputs, any restart replays every LLM call from the beginning. For a 50-step workflow, that's 49 recomputed LLM calls and 49 potential different outputs. Budget for this cost or use an engine that handles it.
- **Partial batch failures (95/100 items succeed)** — don't treat this as "mostly success." The 5 failures may need individual review, compensating transactions, or human escalation. Retrying all 100 is wrong; retrying only the 5 requires tracking which succeeded.
- **Circuit breakers need tuning per service** — a threshold of 5 consecutive failures works for a stable internal API but fires constantly on a shared third-party API with normal variance. Measure actual error rates before setting the threshold.
