# S-988 · The Agent Failure Recovery Stack — When Your Agent Silently Burns Budget in the Dark

Your agent returned `200 OK`. It also ran 50 consecutive compaction failures, burned 250,000 API calls in one day, and left your system in an undefined state. Nobody noticed until the bill arrived. Agents fail in ways that crash-proof pipelines don't prepare you for — and the failure modes that cost money are almost never the ones that surface loudly.

## Forces

- **Agents fail with 200 OK** — the confident wrong answer is the expensive one; it consumes budget and produces garbage silently
- **Recovery loops have no natural ceiling** — retry logic without caps turns into a cost spiral; one real incident burned 250K API calls in 24 hours
- **Multi-step pipelines compound failure** — a 10-step pipeline at 85% reliability per step achieves only ~20% end-to-end success; every step needs its own recovery contract
- **Partial progress is lost by default** — an agent that completes steps 1–4 of 8 and then fails either repeats work or abandons it; checkpointing is opt-in, not opt-out
- **Context pollution degrades recovery** — agents initialized with failed trajectories recover differently than agents in fresh contexts; recovery ability is a distinct capability from task-completion ability (Recovery-Bench, NeurIPS 2025)

## The Move

Build a layered failure recovery architecture with five tiers. Each tier targets a different failure mode and feeds the next.

### Tier 1 — Hard Execution Bounds
The single most important guardrail. Without it, nothing else matters.

- Set a **hard step cap** (e.g., `MAX_STEPS = 12` in LangGraph `recursion_limit=12`) and stop unconditionally when reached
- Implement **iteration budget pressure**: warn the LLM at 75% of the cap that it is approaching its turn limit, giving it a chance to wrap up gracefully rather than being cut off mid-reasoning
- Kill agents that exceed their step budget — do not let them continue in a degraded state

### Tier 2 — Tool-Level Error Semantics
Design tool errors to teach the model, not just abort.

- Return **structured error objects** with `{error_type, message, hint}` — the hint gives the model a concrete recovery path, not a generic exception
- Validate all tool inputs **before execution**: schema validation AND referential integrity checks (does this ID actually exist?)
- Catch hallucinated tool calls at the harness hook layer, before the call executes and produces side effects
- Common failure patterns to detect: missing field loops, stale data loops, auth loops, hallucinated tool names, cost spirals

### Tier 3 — Stateful Checkpointing
Preserve partial progress so recovery resumes, not restarts.

- Checkpoint agent state at every logical task boundary — write to append-only log (PostgreSQL state-transition table works well)
- On failure, resume from the last checkpoint, not from step 1
- Expose state deltas to human-in-the-loop dashboards so compliance reviewers can verify agent actions before finalization
- For long-running financial/compliance workflows, this is non-negotiable — 4 hours of recalculation is the alternative

### Tier 4 — Escalation & Fallback Chains
Never leave the user with nothing.

- Implement **exponential backoff with jitter** for transient failures (API timeouts, rate limits, network partitions) — AWS researchers found this resolves most transient failures within seconds
- Chain **fallback models**: primary model fails → retry with rate-limit-aware logic → retry with fallback provider → surface error with audit trail
- Route to **escalation queue** for cases that exceed recovery budget: human-in-the-loop review for high-stakes or high-cost decisions
- For multi-agent pipelines: enforce strict timeout per agent (15–20s max) and implement fallback routing that produces a decision from available outputs if one agent times out

### Tier 5 — Cost & Confidence Circuit Breakers
Stop the spiral before it empties the account.

- Implement **cost circuit breakers**: track cumulative cost per session and halt if a threshold is exceeded mid-run
- Implement **confidence scoring**: if an agent's self-reported confidence falls below a threshold on a critical decision, route to human review instead of continuing
- Monitor for **drift patterns**: false positive rate increases, dead-end rate increases, cost-per-task anomalies — trigger alerts before they compound

## Evidence

- **Engineering post (Harshrastogi.tech):** Candidate evaluation agent at Asynq.ai hallucinated tool parameters, got stuck in loops, and cost 3x budget in production. Image generation agent at Modelia.ai approved obviously flawed outputs to optimize for workflow completion over quality. Solution: schema validation + referential integrity checks on tool inputs before execution. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Engineering post (AgentMarketCap):** Missing retry cap let 1,279 Claude Code sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. The agent was executing exactly the recovery logic it had been given — the logic just had no ceiling. — [agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines](https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery)

- **Research benchmark (NeurIPS 2025):** Recovery-Bench demonstrates that models' recovery performance differs markedly from their performance in fresh contexts. GPT-5, which underperforms in clean settings, significantly improves in recovery scenarios — recovery ability is a distinct capability requiring its own evaluation. — [openreview.net/pdf?id=8FZRnDgDxq](https://openreview.net/pdf?id=8FZRnDgDxq)

- **Market analysis (Zylos Research, 2026):** ~42% of multi-agent failures are specification failures, ~37% are coordination breakdowns, ~21% are verification gaps. A 10-step pipeline with 85% reliability per step achieves only ~20% end-to-end success. — [zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)

- **Engineering post (ilovedevops.substack, 2026):** LLM pipelines fail differently than traditional APIs: unpredictable latency (500ms–30s), multi-dimensional rate limits (RPM + TPM separate), error cascading where retries compete with legitimate traffic. Pattern: multi-layer circuit breaker with per-model RPM/TPM tracking. — [ilovedevops.substack.com/p/building-reliable-llm-pipelines-error](https://ilovedevops.substack.com/p/building-reliable-llm-pipelines-error)

- **Framework guide (Failproof AI, 2026):** 39 built-in policies covering five failure categories (bad tool calls, hallucinations, runaway loops, drift, destructive shell) across Claude Code, Codex, Gemini CLI, GitHub Copilot. Key insight: catch failures at the harness hook layer before they become incorrect output or irreversible damage. — [befailproof.ai/ai-failure-handling](https://befailproof.ai/ai-failure-handling)

## Gotchas

- **No ceiling on retries = cost spiral.** Every retry policy needs a hard cap. Without it, compounding failures can run for thousands of API calls.
- **Context window exhaustion mid-pipeline.** Prompts + completions that exceed context limits cause partial failures with no clean recovery point. Chunk state aggressively and checkpoint before you approach limits.
- **Silent failure looks like success.** The agent returns `200 OK` and produces confident nonsense. You need output validation — structural checks, semantic verification, human-in-the-loop gates on high-stakes outputs — not just HTTP status codes.
- **Escalation queues pile up.** If your human-in-the-loop fallback is slow, agents keep queuing. Size your escalation path for the volume you actually get, not the volume you expect.
- **Recovery ≠ task completion.** A model that scores well on fresh-task benchmarks may recover poorly from failed trajectories. Test recovery explicitly with Recovery-Bench-style evaluation, not just standard agent benchmarks.
