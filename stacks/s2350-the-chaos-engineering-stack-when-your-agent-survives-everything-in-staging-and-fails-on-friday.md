# S-2350 · The Chaos Engineering Stack — When Your Agent Survives Everything in Staging and Fails on Friday

Your agent passed every test. Unit tests: green. Integration suite: green. Staging: green. Then on Friday at 17:00, a third-party API started returning 429s and your agent started hammering it, running up a $4,200 bill and deleting nobody's data because a retry loop corrupted its state. Your monitoring was green. Your observability was green. The incident was not visible in any dashboard — it was visible in the invoice.

The discipline that prevents this is **agent chaos engineering**: the systematic practice of injecting controlled failures into agent systems to discover how they break before production does it for real.

## Forces

- **Agents amplify failure at autonomous speed.** A crashed microservice returns a 500 and stops. An agent in a retry loop makes 300 calls in 4 minutes, each one compounding state. Traditional chaos engineering (kill a pod, partition a network) tests infrastructure resilience — not the agent's failure modes.
- **Staging is not a stress test.** Staging tests happy paths and known failure modes. Chaos engineering finds the ones you didn't know existed: silent memory corruption, tool-result hallucination under load, policy bypass via error message injection.
- **Agents fail in categories that don't exist for microservices.** Context window overflow, model degradation mid-session, tool-schema drift, adversarial tool responses — none of these appear in classical SRE playbooks. You have to invent the experiments yourself.
- **Recovery behavior is harder to test than failure behavior.** You can easily break an agent. Proving it recovers cleanly — without corruption, without infinite loops, without credential leakage — requires intentional experiment design.

## The move

Agent chaos engineering tests four failure axes that standard chaos testing ignores:

### 1. Tool-chain failure injection

Inject faults at the tool boundary, not the infrastructure level.

```
# Mock tool that fails with increasing severity over time
class flaky_code_search:
    def __call__(self, query):
        call_count[0] += 1
        if call_count[0] < 3:
            return "search results..."  # normal
        elif call_count[0] < 6:
            raise ToolTimeout("connection reset")  # recoverable
        elif call_count[0] < 8:
            return "[]"  # silent empty — agent must detect
        else:
            raise ToolAuthError("token expired")  # non-recoverable
```

Watch: does the agent retry with backoff? Does it eventually escalate? Does it silently accept empty results and proceed? Does it leak the auth error message to a downstream tool call?

### 2. Context window stress

Overflow the context in controlled increments and measure behavior at each threshold.

```python
def context_stress_test(agent, task, sizes_kb=[64, 128, 256, 512]):
    for size_kb in sizes_kb:
        # inject noise: irrelevant context that fills but doesn't inform
        noise = generate_distracting_context(size_kb)
        result = agent.run(task, context_override=noise)
        log(
            context_size=size_kb,
            output_coherent=judge_coherence(result),
            tool_calls=result.tool_call_count,
            cost_usd=result.total_cost,
            recovered=detect_recovery_pattern(result)
        )
```

Measure: at what size does output coherence drop? Does the agent start truncating tool results? Does it abandon the task gracefully or produce confident nonsense?

### 3. Policy-path failure

Agents with governance layers need testing that specifically targets policy decision points.

```python
class PolicyAttackProbe:
    """Inject failures into the policy evaluation path."""
    def __init__(self, policy_engine):
        self.engine = policy_engine

    def run(self, agent_task):
        # Normal request
        baseline = self.engine.evaluate(agent_task)

        # Corrupt the policy cache
        self.engine.cache_corrupt(agent_task.tool_chain)

        # Time the policy decision under corrupted state
        start = time.time()
        corrupted = self.engine.evaluate(agent_task)
        latency_ms = (time.time() - start) * 1000

        # Verify: did the agent continue with a stale decision?
        return {
            "decision_changed": baseline != corrupted,
            "latency_ms": latency_ms,
            "agent_completed": agent_task.completed,
            "policy_overridden": agent_task.tools_called > baseline.allowed_tools
        }
```

The question: when policy evaluation silently fails, does the agent fail open (proceed) or fail closed (halt)?

### 4. Abort criteria

Every chaos experiment needs pre-defined stopping conditions. For agents:

```python
ABORT_CRITERIA = {
    "cost_per_minute_threshold": 10.00,   # stop if spend rate exceeds $10/min
    "max_tool_calls": 200,                 # stop if tool call count exceeds
    "max_session_duration_minutes": 15,    # stop if session exceeds 15 min
    "error_rate_threshold": 0.95,          # stop if 95%+ calls fail (total breakdown)
    "credential_exposure": True,           # stop IMMEDIATELY on any credential leak
}

def should_abort(metrics):
    for criterion, threshold in ABORT_CRITERIA.items():
        if metrics[criterion] >= threshold:
            return True, f"ABORT: {criterion} exceeded {threshold}"
    return False, None
```

Without abort criteria, chaos engineering is not engineering — it's a controlled incident.

## Receipt

> Verified 2026-08-08 — Pattern distilled from Cordum AI Agent Chaos Engineering Playbook (June 2026), Stack Pulsar AI Agent Reliability (2026), Cordum's 4-principle framework (hypothesis first, abort discipline, policy-aware validation, one experiment at a time). Core experiment taxonomy verified across agent reliability literature. Abort criteria structure drawn from production incident patterns documented in agent failure research. Code examples are structural illustrations; Receipt pending — needs live agent harness to confirm behavior thresholds.

## See also

- [S-1000 · The Agent Recovery Stack](/stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails.md) — foundation for understanding agent failure modes this stack exploits
- [S-2340 · The Control Plane Stack](/stacks/s2340-the-control-plane-stack-when-your-agent-needs-a-governor.md) — the governance layer that chaos engineering tests
- [S-1032 · The Dead Letter Stack](/stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — the billing failure mode chaos engineering is designed to catch before it happens
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the broader discipline that makes chaos engineering routine
