# S-1250 · The Failure Handling Stack: When Your Agent Loops for 35 Minutes and Produces Nothing

Your agent worked in the demo. In production, it hits a rate limit at step 3, retries incorrectly, accumulates stale context, gets stuck in a loop calling the same broken tool, burns through the day's API budget, and produces output that looks plausible and is completely wrong. No exception was thrown. No alarm fired. You only find out when a user complains.

## Forces

- **Agents fail without exceptions.** Unlike traditional software that crashes with visible stack traces, AI agents can return HTTP 200 with semantically wrong results, loop silently for minutes, or take irreversible actions before a human can intervene. The absence of errors is not evidence of success.
- **Failures are non-deterministic and trajectory-dependent.** A wrong tool call in step 2 of a workflow corrupts everything downstream. The failure isn't visible until the final output is checked — if it gets checked at all.
- **Self-correction loops can make things worse.** An agent that retries with the same strategy on a transient failure will amplify cost and latency. A retry-with-reflection loop can spiral into recursive collapse if the reflection prompt itself triggers further reflection.
- **Idempotency is hard in agentic workflows.** Unlike REST calls where `POST /orders` is idempotent-safe, agent actions like "send email" or "update record" don't have natural idempotency keys unless explicitly designed for it.
- **The system boundary is fuzzy.** The model, the orchestration framework, the tool interface, the external API, and the state store are all failure surfaces — and they're entangled. A tool that works in isolation can fail in a multi-step context.

## The Move

Build a layered failure handling harness around the agent loop — not just exception handling, but detection, recovery, containment, and escalation. The key insight from production teams: the harness is the product, not the agent.

### 1. Structured failure taxonomy at the loop boundary

Classify failures before deciding how to respond. The main categories practitioners use:

- **API-level errors** (rate limits, timeouts, 5xx): retry with backoff
- **Semantic errors** (tool returns 200 but wrong data, malformed JSON, schema mismatch): catch at validation, don't retry blindly
- **Hallucinated tools** (agent calls a tool that doesn't exist or isn't in the available set): detect at routing, fall back to a safe handler
- **Trajectory loops** (agent re-attempts the same failed action with the same strategy): detect via state hash or iteration count, break and escalate
- **Context overflow** (context window fills before task completion): checkpoint progress, truncate and restart with condensed history
- **Recursive collapse** (self-correction triggers self-correction): set a max reflection depth, hard break

### 2. Bounded retry with exponential backoff and jitter

```python
import time, random

def retry_with_backoff(fn, max_attempts=3, base_delay=1.0):
    for attempt in range(max_attempts):
        try:
            return fn()
        except TransientError as e:
            if attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(delay)
```

Never retry on semantic failures. Only retry on transient errors (rate limits, network timeouts). Add jitter to avoid thundering herd when the API recovers.

### 3. Checkpoint-and-resume at natural boundaries

LangGraph's checkpointing (`langgraph.checkpoint`) and Microsoft's Supervisor pattern both use this: after each meaningful step, snapshot state (messages, intermediate results, iteration count, tool results) to durable storage. On failure, resume from the last checkpoint rather than re-running from scratch.

```python
# LangGraph checkpoint pattern
checkpoint = compiler.checkpointer.get(config)
if checkpoint and checkpoint.metadata.get("status") == "partial":
    # Resume from last checkpoint instead of re-running
    state = checkpoint.state
```

Stateful rollbacks eliminate the cost of re-running completed work and prevent side-effect duplication on retry.

### 4. Circuit breaker on noisy tools

If a tool fails N times in a row (e.g., a rate-limited external API), open the circuit: stop calling it and return a fallback immediately for the duration of the window. Prevents retry storms from compounding load on a struggling service.

State machine: `CLOSED → OPEN → HALF_OPEN → CLOSED`. Track per-tool, not per-agent.

### 5. Human escalation gate for high-stakes actions

Actions that are irreversible (sending emails, updating records, approving payments) should have a human-in-the-loop checkpoint before execution. Pattern from AgentPatterns: escalation queue where the agent buffers the action, pauses the loop, and awaits human confirmation or rejection within a time window.

### 6. Hard limits as guardrails

- **Max iterations**: cap the number of agent loop turns (typically 10–50 depending on task complexity). An agent that hits the cap should surface partial results and stop.
- **Max token budget**: track cumulative spend per task and abort if it exceeds a threshold.
- **Terminator tool**: explicitly give the agent a `finish_task(result, status)` tool that signals completion cleanly — prevents conversational deadlock where neither agent nor orchestrator knows who has the final say.

## Evidence

- **Research synthesis:** AI Agent Self-Healing and Failure Recovery — Zylos Research (May 2026) identified 9 distinct failure modes across production deployments, with agentic-specific failures (hallucinated tools, recursive collapse, conversational deadlock) accounting for failures that traditional circuit breakers and retry logic don't address. — [Zylos Research](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)
- **Enterprise incident analysis:** Open Empower's analysis of 2026 enterprise deployments found runaway loops (agent retries same failed action with same strategy) as the #1 most common production failure — distinct from and more costly than simple API errors. — [Open Empower](https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026)
- **Framework patterns:** Cloudzy documented 6 failure modes in agent loops (looping on bad tool results, retry storms, context overflow, state divergence, deadlocks, resource contention), noting that "the loop ran clean forty times in testing. On the forty-first run, in production, it called the same SQL tool with the same broken query over and over until it burned through the day's API budget." — [Cloudzy Blog](https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production)
- **Implementation patterns:** Five production-tested patterns — exponential backoff, circuit breakers, checkpoint-and-resume, fallback strategies, and escalation queues — documented with Anthropic SDK code samples. — [AI Agents Blog](https://aiagentsblog.com/blog/agent-error-recovery-patterns)
- **Framework-level support:** LangGraph's `StateGraph` + `checkpointer` primitives and Microsoft Agent Framework's Supervisor pattern both implement checkpoint/resume natively. LangGraph's AI-system-design-guide explicitly moved from "try-catch blocks" to "agentic self-correction and stateful rollbacks." — [GitHub: ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Multi-agent failure decomposition:** MatterAI's LangGraph + CrewAI integration notes that self-correction loops in multi-agent systems need explicit state tracking (iteration counts, error logs, intermediate results) and conditional edges — agents cannot self-correct reliably without this state. — [MatterAI Guides](https://www.matterai.so/guides/agentic-workflows-building-self-correcting-loops-with-langgraph-and-crewai-state-machines)

## Gotchas

- **Don't retry blindly.** Retrying a semantically wrong action wastes budget and may compound the error. Retry only on transient, API-level errors. Validate tool outputs before retrying.
- **Self-correction loops can spiral.** An agent asked to "reflect on your errors and try again" may generate a reflection that triggers another reflection. Set a max reflection depth.
- **Checkpointing without idempotency causes duplication.** If your agent sends an email at step 3, you checkpoint, it fails at step 7, and you resume from the checkpoint — the email gets sent again unless the tool is idempotent or uses a transaction log. Design for this.
- **Hard limits aren't always respected.** If your agent has access to a `set_max_iterations()` function, a compromised or confused agent can raise its own limits. Put limits at the harness layer, not inside the agent's tool set.
- **The harness is the product.** Production teams consistently report that reliability comes from the system around the agent — tools, memory, orchestration, guardrails, context management, and recovery — not from model capability alone. ([Cloudzy](https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production))
