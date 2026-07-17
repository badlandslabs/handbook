# S1262 · The Agent Loop and Recovery Stack · When Your Agent Won't Stop or Can't Resume

The two failure modes that turn agent demos into production incidents: an agent that never stops (retry loops, infinite tool calls) and an agent that never resumes correctly (process crash loses all progress, context overflow erases state).

## Forces

- **Frameworks optimize for completion, not stopping.** Most agent frameworks (LangChain, AutoGen) default to "retry → retry again → no exit condition → keep trying." This is the right behavior for demos; it's the wrong behavior for unattended production runs.
- **Agents fail non-deterministically.** A prompt that works once fails the next time due to model drift, token limit changes, or a downstream API returning a different error format. Traditional try/catch doesn't cover these failure modes.
- **State is implicit until it disappears.** Context lives in the model's working memory. When a session crashes or context overflows, there's no durable record of where the agent was — it restarts from scratch.
- **Monitoring tools answer "what happened," not "is it stuck."** LangSmith, LangFuse, Arize, and Helicone show traces and latency, but don't flag behavioral anomalies like repeated identical tool calls or diminishing returns loops.
- **Cost compounds invisibly.** A $400 runaway loop (Anythoughts.ai, 2025) and a $47,000 episode (Waxell.ai, 2025) both went undetected for hours because token counts and cost metrics weren't enforced at the run level — only reported afterward.

## The Move

Layer four distinct mechanisms to make agent failure recoverable rather than catastrophic.

### 1. Structured completion signals in every tool response

Agents loop most often because tool output is ambiguous — an empty array could mean "search hasn't worked yet" or "no results found." Fix this at the interface level:

```json
{
  "status": "complete",       // or "partial" or "failed"
  "result": [...],
  "message": "Search completed. No results found. This is definitive."
}
```

This single change eliminates ~40% of production loops, per aiwave.hashnode.dev analysis of ReAct pattern failures. Every tool response must carry an explicit completion marker — not just data.

### 2. Hard budget guards before soft intelligence

Budget enforcement must be a hard limit, not an alert. By the time you receive a billing alert, you've already consumed the budget. Set enforcement at the orchestrator layer:

- **Max iterations** — unconditional halt after N agent turns (e.g., 10–50 depending on task complexity)
- **Max tokens per run** — kill switch on cumulative context growth
- **Max cost per task** — track spend in real time, abort when exceeded
- **Timeout per step** — individual tool calls get their own deadlines

These are deterministic overrides, not LLM suggestions. The manager agent or conditional router enforces them.

### 3. Checkpoint state after every completed step

Serialize agent state to durable storage after each step, not at the end of the workflow. The minimum checkpoint contains:

```python
{
  "step": 3,
  "completed_steps": [...],
  "current_reasoning": "...",
  "tool_call_history": [...],
  "accumulated_decisions": {...}
}
```

Resume loads the last checkpoint and skips completed steps. Microsoft Agent Framework (Python, `checkpoint_with_resume.py`) provides this via `CheckpointStorage` with a self-looping `WorkerExecutor` that checks state before each step. File-based checkpoints (JSON/Parquet) work for single-agent workflows; event sourcing is the upgrade path for multi-agent systems.

### 4. Error taxonomy drives the recovery strategy — not a single retry loop

Not all errors should be retried the same way. Classify first:

| Error type | Example | Recovery |
|---|---|---|
| **Transient** | HTTP 429, 503, DNS timeout | Retry with exponential backoff + jitter |
| **Semantic** | Malformed JSON, wrong tool args, schema violation | Re-prompt with corrective context |
| **Resource** | Token budget exceeded, context overflow | Summarize and truncate context, switch model |
| **Fatal** | Auth failure, revoked API key, policy violation | Fail fast, escalate to human |

Transistent errors use backoff (start at 1s, cap at 64s, add ±20% jitter). Semantic errors trigger a single re-prompt with the error message as context — if it fails twice, escalate. Resource errors trigger a context compaction routine (drop oldest results, summarize reasoning log). Fatal errors go directly to an escalation queue.

### 5. Circuit breaker for upstream failures

When an external tool or API fails N times consecutively (e.g., 5), open the circuit: stop calling it for a cooldown period (e.g., 30s–5min), return a fallback immediately, and only attempt the original call again after cooldown expires. This prevents cascading failures where a degraded upstream service causes your agent to burn through retry budgets uselessly. Implemented in tanayshah11/ai-agent-error-patterns as a Trigger.dev v4 integration; also available in Microsoft Semantic Kernel.

### 6. Partial success handling for batch operations

Don't treat a batch as all-or-none. Process items individually, track per-item outcomes, retry only the failures:

```
Batch: 100 documents → 95 succeeded, 5 failed
Action: retry failed 5 individually → 3 recovered, 2 escalated
Final:  98 complete, 2 human review
```

This requires structured result tracking at the item level, not just at the batch level. tanayshah11/ai-agent-error-patterns implements this pattern explicitly.

### 7. Escalation queue for human judgment

Route to a human when: the agent has hit max retries without resolution, the task involves irreversible actions (production deploys, financial transactions), or confidence scores fall below a threshold. The escalation queue is a holding state — the agent's progress is checkpointed, and the human resumes from exactly where it left off. This pattern is documented in both aiagentsblog.com and agentskill.sh's `failure-recovery` skill (Owl-Listener, 112 GitHub stars).

## Evidence

- **DEV Community (case study):** Outreach agent at Anythoughts.ai hit a rate-limited API (HTTP 429), retried ~90 minutes without stopping, burned $400. Root cause: no explicit exit condition and no max-retry cap. — [URL](https://dev.to/alex_wu_anythoughts_ai/the-infinite-loop-problem-how-we-stopped-our-agent-from-running-forever-3ckb)
- **DEV Community (HN-linked incident):** A developer's GPT-4o agent got stuck in a recursive retry loop in production — no alert, no warning, run continued until billing was noticed. Monitoring tools (LangSmith, LangFuse) showed traces but didn't flag the behavioral anomaly. — [URL](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai)
- **GitHub (open-source library):** tanayshah11/ai-agent-error-patterns — MIT-licensed, implements circuit breaker, partial success, HITL, and graceful degradation patterns as Trigger.dev v4 integrations. Documents that "most AI agent tutorials show the happy path" and these patterns are well-known in distributed systems but absent from AI-agent literature. — [URL](https://github.com/tanayshah11/ai-agent-error-patterns)
- **GitHub (Microsoft):** microsoft/agent-framework `checkpoint_with_resume.py` — demonstrates state checkpointing with `InMemoryCheckpointStorage`, a self-looping `WorkerExecutor` that checks state before each step, and a `StartExecutor` that sets upper limits. — [URL](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/checkpoint/checkpoint_with_resume.py)
- **Hashnode (technical analysis):** aiwave.hashnode.dev analysis of ReAct pattern failures — structured tool responses with explicit `status` fields eliminate ~40% of production loops; identifies four root causes: ambiguous tool results, no conversation history windowing, lack of max-turn limits, and goal drift. — [URL](https://aiwave.hashnode.dev/why-your-ai-agent-keeps-looping-and-how-to-fix-it-a-deep-dive-into-react-pattern-failures)
- **agentskill.sh (community skill):** `failure-recovery` skill by Owl-Listener (GitHub: Owl-Listener/ai-design-skills, 112 stars) — structured as a reusable agent skill covering multi-agent failure handling and graceful recovery, updated June 2026. — [URL](https://agentskill.sh/%40owl-listener/failure-recovery)
- **AI Agents Blog:** 5 patterns for production reliability using Anthropic SDK: exponential backoff with jitter, circuit breaker, checkpoint-and-resume, fallback strategies, escalation queue. Distinguishes agent failures from traditional software failures. — [URL](https://aiagentsblog.com/blog/agent-error-recovery-patterns)
- **Understanding Data:** Agent Memory Patterns article by James Phoenix — three-tier memory hierarchy (session, file-based, event-sourced) for checkpoint/resume, human-in-the-loop workflows, and fault tolerance. — [URL](https://understandingdata.com/posts/agent-memory-patterns)
- **Codieshub (engineering post):** Conditional routers in LangGraph as the most effective loop prevention mechanism — the reviewer agent evaluates output and routes back to researcher only when specific keywords appear, not unconditionally. — [URL](https://codieshub.com/for-ai/prevent-agent-loops-costs)

## Gotchas

- **Alerts ≠ enforcement.** Budget alerts tell you after the fact; hard caps enforce during execution. Most engineers set up alerts first and assume they're protected. They're not.
- **Checkpoint granularity matters.** Saving state only at the end of a multi-step workflow means every intermediate step is lost on crash. Save after every step — the storage cost is negligible; the recovery benefit is everything.
- **Retry without classification treats semantic errors as transient.** If a tool returns valid JSON but with wrong values, retrying it 5 times wastes budget and produces the same wrong answer. Re-prompt with corrective context instead.
- **Loops can be silent.** If your monitoring doesn't track behavioral patterns (repeated identical tool calls, token growth rate, turn-count-per-run), agents can loop for hours without triggering any alert. You need anomaly detection, not just trace logging.
- **Context compaction is not the same as checkpointing.** Summarizing context to fit the window prevents overflow but doesn't enable resume. You need both: compact for the model, checkpoint for the orchestrator.
