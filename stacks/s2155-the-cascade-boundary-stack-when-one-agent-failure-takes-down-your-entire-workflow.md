# S-2155 · The Cascade Boundary Stack — When One Agent Failure Takes Down Your Entire Workflow

Your code reviewer agent returns a hallucinated code review. Your deployment agent picks it up and merges the change. Your monitor agent flags nothing because the merge tool returned 200 OK. Your memory agent stores the outcome as fact. Three hours later, five workflows are operating on a corrupted premise and nobody can trace it back to one bad review. This is ASI08: Cascading Failures in Agentic Systems — and it is the failure mode that makes multi-agent systems categorically more dangerous than single-agent ones.

## Forces

- **Agents amplify, not just propagate.** A bad LLM output in a single-agent system produces a wrong answer. In a multi-agent chain, that same output becomes a bad instruction to the next agent, which produces bad data for the third, which writes it to the fourth's memory, compounding into system-wide corruption. The cascade shape is multiplicative, not additive.
- **Agents don't have circuit breakers by default.** Microservices fail fast and loudly. AI agents fail ambiguously — returning plausible but wrong output with 200 OK — and retry loops re-execute against the same corrupted state. Without explicit blast-radius bounds, one agent's hallucination becomes every downstream agent's ground truth.
- **Trust chains compound without friction.** A planner agent trusts a researcher agent's output. A deploy agent trusts the planner's verdict. A monitor agent trusts the deploy agent's confirmation. At each hop, the verification surface shrinks because "internal" is treated as "trusted." By the time the error reaches the monitor, nobody is checking the original source anymore.
- **Shared memory turns failures into persistent state.** Unlike a crashed microservice that resets on restart, a corrupted memory entry persists across sessions. Future agent runs load the poisoned state as context, re-executing failed assumptions on every new task.

## The move

**Bound blast radius at every handoff — not just the entry point.**

### 1. Classify the cascade shape before deployment

ASI08 identifies four distinct cascade geometries. Match your containment strategy to the shape:

| Cascade shape | Trigger | Amplification |
|---|---|---|
| **Shared-state corruption** | One agent writes corrupted data to shared memory/RAG | All agents reading that store inherit the error |
| **Unsafe fan-out** | One failure triggers N downstream retries | A flaky tool call becomes N redundant API charges + N corrupted writes |
| **Policy bypass via fallback** | Fallback chain disables security controls when primary fails | Compromised state becomes the authorized path |
| **Control-plane coupling** | Orchestrator failure cascades to all managed agents | One bad planning decision poisons every worker |

### 2. Implement structured error context as a handoff contract

Subagents must return structured error objects, not natural-language explanations or HTTP codes. This is the interface contract between agents — without it, coordinators cannot distinguish "found nothing" from "failed silently."

```python
# Anti-pattern: empty result masquerading as success
{"status": "ok", "results": []}  # indistinguishable from "search ran, found nothing"

# Correct: explicit error taxonomy
{
    "status": "error",
    "error_type": "tool_execution_failure",
    "error_code": "UPSTREAM_TIMEOUT",
    "recoverable": True,
    "retry_after": 5,
    "partial_result": None,
    "provenance": {"agent": "researcher-v2", "tool": "web_search", "input_hash": "abc123"}
}
```

Every agent response — success or failure — must carry: `status`, `error_type`, `recoverable`, and `provenance`. Coordinator agents MUST reject responses missing these fields.

### 3. Deploy circuit breakers per agent, not per system

Each agent in a workflow gets its own circuit breaker with per-hop timeout and fan-out cap:

```python
# Per-agent circuit breaker
breaker = CircuitBreaker(
    failure_threshold=3,        # open after 3 consecutive failures
    recovery_timeout=30,        # try again after 30s
    half_open_max_calls=1,      # one probe call in half-open state
    fan_out_cap=5,             # hard cap on concurrent downstream calls
)
```

Key behaviors:
- **Fail open is NOT an option.** When a circuit opens, the workflow degrades safely — returns partial results, escalates to human, or halts. It does NOT continue with unverified state.
- **Fan-out cap prevents retry storms.** When a tool call fails, the breaker prevents N agents from simultaneously retrying the same call, which would overwhelm the downstream service and generate N correlated failures.
- **Partial-result propagation.** Circuit breakers must expose partial results from successful steps so the caller can decide whether to continue with degraded data or halt.

### 4. Enforce trust-domain isolation with read/write scope

Split shared resources into trust domains with explicit read/write scopes:

```
Trust Domain A (Planner)     → writes: task_queue
                              reads:  user_context, memory

Trust Domain B (Researcher)  → writes: research_store
                              reads:  task_queue

Trust Domain C (Deployer)    → writes: deployment_log
                              reads:  research_store, task_queue

Trust Domain D (Monitor)     → writes: alert_queue
                              reads:  deployment_log, research_store
```

An agent in Domain B cannot write to `deployment_log`. A corrupted researcher agent cannot directly corrupt the deployer's state — it can only poison what the deployer chooses to read from `research_store`. The deployer is responsible for verifying read data against its own trust scope.

### 5. Version the memory handoff at every agent boundary

Before an agent passes context to a downstream agent, snapshot the relevant memory slice with a content hash:

```python
context_snapshot = {
    "source_memory_hash": sha256(context_slice),
    "version": datetime.utcnow().isoformat(),
    "upstream_agent": "researcher-v2",
    "downstream_agent": "deployer-v1",
    "task_id": "deploy-abc123",
}
```

If memory is later found corrupted, the snapshot chain lets you trace which handoff introduced the poison — and replay from the last verified checkpoint.

### 6. Build explicit degradation paths, not implicit fallback chains

Define what "degraded" means per workflow, not per tool:

```yaml
# workflow_degradation_policy.yaml
workflow: code_review_to_deploy
max_cascade_depth: 3
degradation_levels:
  0: Full pipeline — all agents healthy, all checks green
  1: Reduced scope — skip automated test generation, human reviews research output
  2: Human gate — only deploy on explicit human approval, all agent outputs advisory
  3: Full halt — no deployment, alert on-call, preserve state for post-mortem

cascading_halt_conditions:
  - error_type: memory_poisoning_detected
    halt_at_depth: 0    # stop immediately
  - error_type: tool_execution_failure
    halt_at_depth: 2    # halt at human gate
  - error_type: confidence_threshold_breached
    halt_at_depth: 1    # reduced scope
```

Never build fallback chains that silently bypass security controls. Every degradation level must have a human-accessible audit trail.

## Receipt

> Verified 2026-08-05 — Sources: OWASP ASI08 (Cascading Failures, OWASP Top 10 for Agentic Applications 2026, genai.owasp.org), Adversa AI ASI08 Complete Guide (2026), Zealynx Security OWASP ASI08 Explainer (June 26, 2026), ExplainX Multi-Agent Error Propagation Patterns (June 29, 2026), Brandon Lincoln Hendricks "Handling AI Agent Cascading Failures in Production" (April 1, 2026), Microsoft Agent Governance Toolkit Issue #1368 (Q3 2026 strategic, ASI08 cascading failure containment). Existing handbook coverage: S-1000 (off-rails loops), S-1012 (recovery patterns), S-1065 (trust escalation across agent hops) — none address cascade geometry classification, per-hop circuit breakers, fan-out caps, trust-domain memory isolation, or structured degradation policy. The I-3018 Memory Graft Stack (S-2144) covers memory poisoning as a supply chain issue; S-2151 covers poisoning detection. This entry fills the complementary gap: how cascading failures propagate across multi-agent workflows even when no single agent is malicious.

## See also

- [S-1065 · The Inter-Agent Trust Escalation Stack](/stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control) — trust propagation between agents
- [S-2151 · The Memory Poison Stack](/stacks/s2151-the-memory-poison-stack-when-your-agents-long-term-memory-becomes-an-attacker-control-channel) — persistent state corruption via memory poisoning
- [S-1000 · The Agent Recovery Stack](/stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails) — off-rails loops and recovery
- [S-1012 · The Agent Failure Recovery Stack](/stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices) — retry and compensation patterns
- [S-1458 · The Policy Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer) — enforcement at the tool call boundary
