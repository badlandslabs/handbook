# S-1378 · The Agent Recovery Stack — When Your Agent Crashes Mid-Task and You Lose Everything

Your 500-item batch job crashes at item 347. Your agent loops for 35 minutes with no output. Your tool call fails silently for 3 days. Your checkpoint saves the conversation history — but replaying it produces a different reasoning path, and item 346 already sent a duplicate email to the customer. You have no recovery state, no failure taxonomy, and no idea where to start debugging. This is the agent failure handling problem, and the standard try/catch wrapper is not the solution.

## Forces

- **Standard retry logic fails for agents.** Retries that work for web services break for LLMs because failure modes differ: model hallucinations, token limit violations, non-deterministic outputs. A blind retry on a malformed JSON response just burns tokens until you hit the same wall again.
- **Conversation replay is not recovery.** The most intuitive approach — save the full transcript and replay it on restart — fails because LLM responses are non-deterministic, context replay is expensive, and already-committed side effects can be duplicated.
- **Every failure type needs a different recovery path.** A rate-limit error (transient) should retry with backoff. A schema violation (semantic) should re-prompt with corrective context. A revoked API key (fatal) should abort immediately. Treating them all the same is how you get silent failures that burn budget and corrupt state.
- **Auto-replay without policy checks duplicates side effects.** A DLQ that replays a failed job without re-evaluating guardrails can create a second ticket, send a second email, or push a second config change — the "empty DLQ quickly" goal actively conflicts with safe recovery.
- **Self-healing is real but bounded.** LLM agents can reason about their own failures and attempt corrections — but without iteration limits and exit gates, self-healing loops become the failure mode itself.

## The Move

**Build a layered failure recovery architecture.** Classify errors by type before deciding what to do. Layer retry logic, state checkpointing, DLQ triage, and bounded self-healing into a coherent stack.

### 1. Classify before you retry

Separate failure into four tiers, each with its own response:

| Error type | Examples | Response |
|---|---|---|
| **Transient** | Rate limits (429), network timeouts, 503s | Exponential backoff + jitter; retry up to N times |
| **Semantic** | Malformed JSON, wrong tool name, schema violations | Re-prompt with corrective context; do not retry the same call |
| **Resource** | Token limit, context overflow, spending cap | Reduce payload — summarize, drop older results, switch to cheaper model |
| **Fatal** | Auth failures (401), revoked keys, policy violations | Abort immediately; log, alert, escalate |

> Classify before you retry. A retry loop that hammers a 401 endpoint wastes tokens and delays the alert.

### 2. Make retries safe with idempotency keys

Every step that creates side effects (sends email, writes records, creates tickets) must carry an idempotency key. On retry, the system checks whether the step already succeeded before replaying it. This is the difference between a safe retry and a double-send.

- Separate retry configs for idempotent vs non-idempotent operations
- Log the idempotency key in every DLQ record so replay can check it

### 3. Checkpoint structured state, not conversation history

Save the minimal state needed to resume: **goal, plan, completed steps, and results**. On restart, reconstruct a fresh agent context from this summary. This avoids three failure modes of conversation replay (non-deterministic re-response, expensive context cost, and subtle path divergence).

Practical checkpoint tools:
- `agent-resume` (MukundaKatta): zero-dependency Python library; checkpoint per item, resume from last index — works for batch jobs processing 500+ documents
- LangGraph and Temporal: first-class checkpoint primitives for stateful agent workflows
- Dapr Actors: virtual actors maintain state across restarts automatically

Checkpoint at **step boundaries**, not arbitrary intervals. A step boundary is when you have a verifiable output and no uncommitted side effects.

### 4. Build an actionable DLQ with reason codes

When retries are exhausted, emit to DLQ — but with metadata that drives recovery decisions:

```json
{
  "reason_code": "max_scheduling_retries",
  "reason": "max scheduling retries exceeded (attempts=50)",
  "attempts": 50,
  "idempotency_key": "run_2f91:step_3",
  "policy_snapshot": "sha256:ab91...",
  "replay_status": "pending_review"
}
```

Triage failures by type before replay:
- **Transient failures** (timeout, rate limit): auto-replay with backoff
- **Poison pills** (repeated failures on same item): isolate and flag for human review
- **Governance failures** (policy violation, auth revoked): escalate to human gate, never auto-replay
- **Side-effect uncertainty** (unclear whether step committed): human review before replay

**Always re-evaluate policy before replaying.** Replay must go through the full policy check again — otherwise you bypass guardrails that may have changed since the original run.

### 5. Bounded self-healing loops

When a tool call fails, let the agent read the error, reason about it, and attempt a different approach. Cap this at 2-3 correction attempts per step to prevent infinite loops. Use the error message as corrective context in the re-prompt:

> "Tool call failed with: [error]. The parameter was [X] but the API expects [Y]. Try again with corrected parameters."

Track self-healing outcomes in your eval pipeline. If the same error type keeps requiring human correction, it is a signal to improve the tool definition or add a guardrail, not to add more retry loops.

### 6. Add circuit breakers

After N consecutive failures (miaoquai.com uses 5), open the circuit breaker for 30 seconds and fall back to degraded mode. This prevents the "silent 3-day failure" where an MCP server is returning errors but the agent keeps hammering it. On circuit open, notify operators and switch to a fallback tool or model.

## Evidence

- **GitHub Discussion:** miaoquai.com runs 5 autonomous AI agents 24/7 for 95+ days using a 4-layer stack: connection resilience (exponential backoff + 30% jitter + circuit breaker after 5 consecutive failures), model fallback chain (Opus → Sonnet → Haiku → queue), tool failure isolation (30-second timeout per tool, structured error return, degraded continuation), and state checkpointing — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **GitHub Repo:** `MukundaKatta/agent-resume` — zero-dependency Python library for checkpoint-and-resume on batch agent jobs; saves processed-item index to durable store, resumes from last checkpoint, prevents full restarts — [dev.to/mukundakatta/agent-resume](https://dev.to/mukundakatta/agent-resume-checkpoint-and-resume-long-running-ai-agent-jobs-in-python-4n22)
- **Engineering Guide:** Cordum's DLQ pattern caps scheduling retries at 50 (~25 minutes), then emits DLQ metadata with reason codes and policy snapshots; emphasizes that replay must re-run policy evaluation and that side-effect uncertainty requires a human gate — [cordum.io/blog/ai-agent-dlq-replay-patterns](https://cordum.io/blog/ai-agent-dlq-replay-patterns)
- **Research Synthesis:** Zylos Research documents that long-running agent workflows need checkpointing + event-history replay + idempotent tool design; notes that frameworks with first-class checkpoint primitives (LangGraph, Temporal, Dagster) are the practical implementation path — [zylos.ai/research/2026-03-04](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability)
- **Blog Post:** KnightLi's guide on interrupted long tasks: save goal, checkpoint list, and workspace state; on restart, inspect git status and logs, rebuild context from the latest checkpoint, and continue only from unfinished items — [knightli.com/en/2026/07/10/ai-agent-long-task-resume-guide](https://knightli.com/en/2026/07/10/ai-agent-long-task-resume-guide)
- **Company Engineering:** LangChain's self-healing GTM agent detects deploy regressions, triages whether changes caused them, and kicks off a fix agent to open a PR — bounded self-healing at the pipeline level, not just the tool-call level — [langchain.com/blog/how-my-agents-self-heal-in-production](https://www.langchain.com/blog/how-my-agents-self-heal-in-production)
- **Production Incident Repo:** Yun1976/ai-agent-incidents collects real post-mortems from multi-agent systems; 33 lessons covering gateway outages, model failures, runaway tasks, and cascading errors — [github.com/Yun1976/ai-agent-incidents](https://github.com/Yun1976/ai-agent-incidents)

## Gotchas

- **Do not wrap the whole agent in a single try/catch.** Each LLM call and each tool call needs its own retry contract — exception classes, max attempts, and backoff strategy defined per call site, not a blanket handler around the entire run.
- **Conversation history is not a checkpoint.** Saving `messages` and replaying them on restart produces different LLM responses and can double-execute side-effectful steps. Save structured state (goal + completed steps + results) instead.
- **Auto-replay without idempotency checks creates duplicates.** If you do not verify that a failed step did not commit before replaying it, you will send duplicate emails, create duplicate tickets, and corrupt external state. Every side-effectful step needs an idempotency key in the DLQ record.
- **Self-healing loops need hard exit conditions.** Without iteration limits, a broken tool definition will cause the agent to loop indefinitely attempting corrections. Cap at 2-3 attempts per step and escalate to DLQ on exhaustion.
- **Circuit breakers must cover tool servers, not just models.** The most insidious silent failures are when an MCP server or API endpoint degrades silently (returns 200 with bad data, or times out). A circuit breaker at the tool-call level — not just the model level — catches this.
