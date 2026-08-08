# S-2336 · The Silent Burn Stack — When Your Agent Fails Cleanly and Wastes Money Anyway

Your agent never crashes. Every API call returns 200. Every span is green. It just keeps running — looping on the same task, burning tokens, burning budget — until a billing alert finally notices. You've been conflating crash recovery (deterministic software) with failure handling (non-deterministic agents), and the gap is costing real money. The fix isn't more retries. It's loop detection, checkpoint-and-resume, and error-aware circuit breaking that treats an API outage differently from a hallucinated parameter.

## Forces

- **The clean failure illusion** — agents rarely raise exceptions. They return 200 OK while doing the wrong thing, entering silent loops, or producing semantically wrong output. Monitoring systems built for crashes miss them entirely.
- **The max_iterations false ceiling** — `max_iterations=N` is a cost guardrail, not failure handling. When an agent hits the cap, it exits "successfully" — no alert fires, no recovery triggers, the work is undone.
- **The retry-everything instinct** — traditional fault tolerance (retry on error) works for API outages but amplifies semantic failures. A plan that was wrong on the first try doesn't get better by repeating it.
- **The multi-agent amplification** — two agents in a feedback loop (Analyzer → Verifier → Analyzer) can produce individually-correct responses that collectively loop forever. A2A communication adds a new failure surface: conversation-state termination.
- **The partial-progress cliff** — an agent completes steps 1–6, then corrupts state at step 7. Without checkpoint-and-resume, you restart from zero — losing all progress and all context.

## The move

### Detect loops by convergence, not count

Replace `max_iterations=N` with loop-gain measurement. Track the error signal (e.g., similarity of recent outputs, retrieval improvement delta) across iterations. When the error signal stops improving for 3+ consecutive steps, the loop has converged — whether or not it's correct. Stop and rollback to best-so-far, not last-so-far.

```python
# LoopGain pattern: control-theoretic stop
# E(n) = error signal at iteration n
# Aβ = E(n) / E(n-1)  (Barkhausen criterion)
if abs(Aβ - 1) < epsilon:       # loop has converged
    return rollback_to_best()
if Aβ > 1:                       # degrading
    return rollback_to_best()
# else: continue
```

Measure of convergence vs. max_iterations (LoopGain benchmark, 2,000 paired trials):
- 58% fewer iterations on average
- 55% cost reduction vs. fixed-cap baselines
- 23% additional savings from rollback-to-best on degradation detection

### State checkpoint at every tool boundary

Save a named checkpoint after every successful tool call — not just at step boundaries. This turns an 8-step agent into 8 resumable states. When a final-step hallucination corrupts execution, rewind to the last valid checkpoint instead of restarting.

```python
# LangGraph 3-line rollback pattern
checkpoint = compiler.get_checkpointer().get(state_id)
graph.update_state(state_id, checkpoint, as_node="step_5_safe")
# Resume from step 5, not from the beginning
```

Production checkpoint stores: Redis for low-latency single-agent flows; Postgres for durable multi-agent traces requiring replay capability.

### Error-classify your circuit breaker

Route errors to different handlers by type — API errors, LLM errors, and semantic errors require different recovery strategies:

| Error type | Handler | Strategy |
|---|---|---|
| API error (503, timeout) | Circuit breaker | Cap retries, trip after 3 failures, fail-fast |
| LLM error (malformed output) | Output parser retry | Re-prompt with explicit format instructions |
| Semantic error (wrong plan) | Escalation gate | Flag for human review, don't retry blindly |
| Silent loop (no error, no progress) | Convergence detector | Stop + rollback to best-so-far |

### Tool descriptions as termination contracts

Every tool description must specify: what a good input looks like, what the output represents, **when to stop calling it**, and what to do if it fails. Vague descriptions ("Search the documentation") cause agents to call the tool until context runs out.

```python
@tool
def search_docs(query: str) -> str:
    """Search internal documentation for the query.
    Returns the 3 most semantically similar sections.
    STOP calling this tool after 1 successful call per task —
    additional calls will return redundant results.
    If no results match, return 'NO_RESULTS' and pivot to web search."""
```

### Idempotency guards before destructive actions

Before any state-mutating tool call, inject an idempotency check. Ask: "Did this action already succeed?" This prevents the partial-success retry problem where an action partially executed before failing, and a retry re-executes it.

## Evidence

- **Incident post-mortem (vectara/awesome-agent-failures):** Four LangChain agents in an A2A Analyzer↔Verifier loop ran for 11 days, 1.8M API calls, $47,000 — every endpoint returning HTTP 200. Discovery came from a billing threshold alert, not any termination mechanism. Root causes: no iteration cap, no progress tracking, no conversation-state termination. — [URL](https://github.com/vectara/awesome-agent-failures/blob/main/docs/case-studies/langchain-a2a-47k-infinite-loop.md)

- **Atlan engineering blog (2025):** Sherlock, their production incident investigation agent, suppresses ~85% of alerts before any model runs via a cheap admission filter. Investigation time: 10+ minutes → ~2 minutes average. Cost: "a few dollars → ~$0.28 per investigation." Key insight: the agent loop is the easy part; the engineering is in the trigger, validator, and escape-hatch scaffolding around it. — [URL](https://blog.atlan.com/engineering/loop-engineering-in-production-putting-ai-agents-on-call/)

- **LoopGain GitHub (2025):** Open-source control-theoretic loop controller with adapters for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents, and Claude Agent SDK. Benchmarked on 2,000 paired trials across 10 workload cells: median 58% iteration reduction, 55% cost reduction vs. max_iteration baselines. — [URL](https://github.com/loopgain-ai/loopgain)

## Gotchas

- **`max_iterations` is invisible to monitoring** — an agent that hits the cap exits with a clean return code. Your alerting system won't know unless you explicitly instrument it.
- **Convergence ≠ correctness** — loop detection tells you the agent stopped improving, not that the answer is right. Always pair convergence detection with an output validation gate.
- **Multi-agent loops are state-machine problems** — the fix isn't per-agent iteration caps; it's a shared conversation-state manager that tracks whether the collective output has stabilized.
- **Rollback doesn't undo external side effects** — if the agent already called a payment API, rolled back state doesn't reverse the charge. Idempotency and confirmation gates belong before irreversible actions, not after.
- **The admission filter is worth more than the recovery loop** — Atlan's biggest win came from suppressing alerts before the agent ran, not from building smarter recovery. Invest in trigger quality first.
