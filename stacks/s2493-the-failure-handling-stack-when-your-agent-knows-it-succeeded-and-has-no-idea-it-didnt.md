# S-2493 · The Failure Handling Stack — When Your Agent Knows It Succeeded and Has No Idea It Didn't

Your agent completes its task, returns a confident answer, and terminates cleanly. The logs say `status: success`. The user sees wrong data. The tool silently failed on step 3, the LLM interpreted the error as "keep going," and now you've shipped confident nonsense for six hours before anyone noticed. This is the core paradox of agentic failure: the agent cannot reliably distinguish success from failure, which means every failure handler you build must compensate for a system that doesn't know it broke.

## Forces

- **Agents fail ambiguously.** LLM APIs return HTTP 200 for rate-limit 429s, malformed JSON for hallucinations, and confident prose for reasoning errors. The error signal is absent at the exact moment the failure is most dangerous.
- **Retries are double-edged.** Bounded retries recover from transient failures — but agents caught in mutual recursion will retry their way to $47,000. The same mechanism that saves you from network hiccups can amplify the failure you're trying to contain.
- **Success and failure live on opposite sides of the same wall.** LLMs are better at evaluating output than generating it. But evaluation adds latency, cost, and complexity — so teams ship agents that skip it and ship confident errors instead.
- **Alerts are not enforcement.** An observability dashboard firing on a Saturday afternoon does not stop the API calls already in flight. Enforcement must live inside the execution boundary, not downstream of it.

## The Move

The failure handling stack is layered: detect → classify → recover → learn. Each layer addresses a different failure mode and must not depend on the layer below to be correct.

### Layer 1 — Error taxonomy and classification

Before you can handle a failure, you must classify it. Agent failures fall into four categories that demand different responses:

- **Infrastructure errors** (timeout, rate limit, network drop): transient, retryable with backoff.
- **Semantic errors** (hallucinated tool call, malformed output, wrong reasoning): HTTP 200, must be caught by validation upstream of retry — retries amplify these.
- **Loop errors** (repeating the same action without progress): not an error in the traditional sense, requires structural detection (hash of recent outputs, step count, budget).
- **Cost errors** (runaway spend without progress): a loop variant that manifests financially — requires hard limits, not alerts.

### Layer 2 — Self-correction via reflection

LLMs evaluate better than they generate. The reflection pattern: after producing output, invoke a second LLM call (lower temperature, critique-focused) to identify errors. If the critique surfaces issues, revise. One or two cycles typically suffice; beyond three, diminishing returns.

```python
# Evaluate-then-revise loop
critique = llm.generate(f"""Review this output for correctness:
Output: {current}
Task: {goal}
List specific problems or confirm it's correct.""")
if critique.indicates_errors():
    current = llm.generate(f"""Revise based on feedback:
    Original: {current}
    Critique: {critique}
    Requirements: {goal}""")
```

This catches semantic failures — hallucinations, logic errors, missed requirements — that never surface as HTTP errors.

### Layer 3 — Stateful rollback (checkpointing)

LangGraph and Microsoft Agent Framework expose checkpoint/resume primitives. On failure, the agent rewinds to a known-good state instead of starting over. Three-line pattern:

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(DB_URL)
app = workflow.compile(checkpointer=checkpointer)

# On failure — rewind to last checkpoint
config = {"configurable": {"thread_id": thread_id}}
app.update_state(config, {"status": "retry_from_checkpoint"})
```

Use PostgresSaver or Redis for production; SQLiteSaver is ephemeral in containers (pod restart wipes it). Pair with human-in-the-loop interrupts: the harness pauses on high-stakes steps and waits for a human signal before proceeding.

### Layer 4 — The stuck-loop escape ladder

Not all stuck states are equal. The recovery ladder escalates:

1. **Nudge** — inject a prompt variation ("try a different approach"), re-seed the reasoning context.
2. **Replan** — call the agent's planner with the current state and ask it to propose a new path.
3. **Reset** — clear short-term memory, re-initialize the conversation from the last confirmed-good state.
4. **Escalate** — route to a more capable model or a specialist agent.
5. **Hand off** — surface the full trajectory to a human, including what was tried and what went wrong.

Detect loops with: output-hash similarity (if N consecutive outputs are >95% similar, fire), step-count budget (hard cap on agent steps per session), or progress proxies (rising score on a convergence metric). Do not use activity volume — API calls rise during legitimate heavy work.

### Layer 5 — Budget enforcement (not alerts)

Enforce spend limits at the harness level, not at the billing dashboard. A budget has three properties: it is **enforced inside the request** (not after), it **stops execution immediately** (not at next human review), and it is **defined per agent, not per account**. Hard stops at $X per task, per session, and per agent prevent the $47,000 eleven-day runaway.

## Evidence

- **Production incident (Nov 2025):** Four LangChain agents fell into Analyzer/Verifier mutual recursion — Analyzer produces → Verifier requests more → repeat. Alert fired. Gap between alert and human shutdown was 11 days. Total: $47,000. No spend limit per agent, no enforcement. — [Kognita Blog](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch)
- **Production incident (Apr 2026):** 35-engineer SaaS shop accumulated an $87,000 monthly bill. A developer's autonomous refactoring weekend burned $4,200. "Alerts are asynchronous: by the time the page fires, every API call between the alert and the human reading it has already happened." — [Jatin Bansal, Agent Budgets and Runaway Prevention](https://blog.jatinbansal.com/ai-engineering/agent-budgets-and-runaway-prevention)
- **Microsoft Research:** AgentRx framework synthesizes guarded executable constraints from tool schemas and domain policies, logging evidence-backed violations step-by-step to pinpoint the "critical failure step" in long agent trajectories. — [Microsoft Research, March 2026](https://www.microsoft.com/en-us/research/blog/systematic-debugging-for-ai-agents-introducing-the-agentrx-framework/)
- **Real-world pattern — stuck-loop recovery ladder:** agentpatterns.ai documents the nudge → replan → escalate → reset → handoff ladder with maturity rating "adopted." Distinguishes stuck (flat progress across N heartbeats) from slow-but-converging (rising progress, even slowly). — [agentpatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/)
- **Framework evidence:** LangGraph's checkpointing (PostgresSaver/Redis), Microsoft Agent Framework's checkpoint/resume primitives, and the ARF (Agentic Reliability Framework) v3.3.9 all provide native rollback — confirming stateful recovery is production-grade, not experimental. — [GitHub: petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)

## Gotchas

- **Disabling SDK auto-retry is required when you own fallback logic.** LangChain and similar frameworks retry 429s by default; if your harness has its own exponential backoff, the SDK retries compound on your retries and you burn through rate limits twice as fast.
- **Hard-delete on the reflection cycle.** LLMs can spiral into increasingly elaborate wrong answers when asked to defend incorrect output. Cap at 2–3 cycles and escalate or hand off rather than looping.
- **LLM API errors (429, 500, timeout) are retryable; semantic errors are not.** Retrying a hallucinated tool call produces the same hallucination. Classify before you retry.
- **Checkpoint persistence is not automatic in containers.** SQLiteSaver in a Docker container without a persistent volume mount loses all checkpoints on pod restart — functionally identical to no checkpointing.
- **Cost budgets must be enforced at the task level, not the account level.** Per-account limits let a single runaway agent consume the entire budget, blocking all other tasks. Per-agent, per-task budgets contain blast radius.
