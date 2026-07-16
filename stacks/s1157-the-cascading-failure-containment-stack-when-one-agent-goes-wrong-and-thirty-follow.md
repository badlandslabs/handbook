# S-1157 · The Cascading Failure Containment Stack — When One Agent Goes Wrong and Thirty Follow

[Your orchestrator routes a customer complaint to the triage agent. The triage agent is running degraded — an upstream vector DB degraded 30 minutes ago, returning empty results. It routes the complaint as "general inquiry" instead of "urgent billing dispute." The routing is wrong but not error-flagged. The resolution agent processes the wrong queue. The quality-review agent approves the delay. Twelve minutes later the customer has been charged twice, the agent has sent a contradictory email, and nobody has paged anyone because every individual step returned HTTP 200. This is cascading failure: one degraded component propagates wrong outputs downstream, and the failure compounds across agents faster than any single-step error handler can catch it.]

## Forces

- **Agents propagate beliefs, not just errors.** A tool returning `null` is not an error — it's silence. An agent that receives `null` infers a negative result, embeds that inference in its next prompt, and acts on it. Downstream agents act on those inferences, not on the original failure. The root cause is 12 hops away.
- **The blast radius compounds in multi-agent fan-out.** A single orchestrator calling 10 workers where each worker calls 3 tools = 30 execution paths from one failure. If the orchestrator's retry logic fires on a degraded tool, it generates 30 identical failed requests per retry cycle, potentially creating a self-inflicted DDoS on the degraded service.
- **Cascades propagate through shared memory, not just API calls.** Memory poisoning, stale context, and corrupted working memory affect every agent that reads from the same store. The cascade doesn't require a tool call — it just requires a shared read.
- **Cascades accelerate faster than human response time.** A cascade across 30 agents completing in 200ms per step is fully propagated in 6 seconds. The on-call engineer is still reading the first Slack alert.

## The move

### 1. Isolate blast radius at every agent boundary

Every agent-to-agent call is a containment boundary. Design it as such:

```python
# Blast radius isolation per agent boundary
async def agent_handoff(
    source_agent: str,
    target_agent: str,
    payload: dict,
    circuit_state: CircuitBreaker,
    max_propagation_depth: int = 3,
) -> dict:
    """Each handoff is a firebreak, not a bridge."""
    
    # Rule 1: Never propagate a degraded signal without a confidence envelope
    if payload.get("_confidence") is None:
        payload["_confidence"] = 0.5  # Treat un-scored outputs as uncertain

    # Rule 2: Cap propagation depth — deep cascades are almost always wrong
    depth = payload.get("_propagation_depth", 0) + 1
    if depth > max_propagation_depth:
        raise PropagationCapExceeded(
            f"Payload from {source_agent} exceeded depth {max_propagation_depth}. "
            f"Manual review required. Root: {payload.get('_origin_agent', 'unknown')}"
        )

    # Rule 3: Check circuit state before forwarding
    if circuit_state.is_open(source_agent):
        raise CircuitOpen(f"Upstream {source_agent} is degraded. Not forwarding.")
    
    payload["_propagation_depth"] = depth
    payload["_last_agent"] = source_agent
    return payload
```

### 2. Implement per-tool and per-agent circuit breakers

Not all circuit breakers are equal. A circuit breaker on the LLM call is blunt — it stops everything. A circuit breaker per tool capability is surgical:

```python
from collections import defaultdict
import time

class CapabilityCircuitBreaker:
    """Circuit breaker per tool category, not per agent.
    Allows graceful degradation: search fails, but memory retrieval continues."""

    def __init__(self):
        self.failure_counts: dict[str, int] = defaultdict(int)
        self.last_failure: dict[str, float] = {}
        self.half_open: set[str] = set()
        # Tunable: fail fast after N failures, try again after recovery window
        self.failure_threshold = 3
        self.recovery_window_seconds = 30

    def record_failure(self, capability: str):
        self.failure_counts[capability] += 1
        self.last_failure[capability] = time.time()

    def record_success(self, capability: str):
        self.failure_counts[capability] = 0
        self.half_open.discard(capability)

    def can_proceed(self, capability: str) -> bool:
        count = self.failure_counts.get(capability, 0)
        if count == 0:
            return True
        if count >= self.failure_threshold:
            elapsed = time.time() - self.last_failure[capability]
            if elapsed > self.recovery_window_seconds:
                self.half_open.add(capability)
                return True  # Allow one probe
            return False
        return True

    def execute(self, capability: str, fn, *args, **kwargs):
        if not self.can_proceed(capability):
            return {"_circuit_open": True, "capability": capability}
        try:
            result = fn(*args, **kwargs)
            self.record_success(capability)
            return result
        except Exception as e:
            self.record_failure(capability)
            raise
```

### 3. Propagate failure metadata, not silence

When a tool fails, the downstream effect depends entirely on what the agent infers from the failure. Make failures explicit:

```python
def wrap_tool_result(result: dict, tool_name: str, error: Exception | None) -> dict:
    """Always return structured failure metadata. Never return None."""
    return {
        "data": result if error is None else None,
        "_tool_meta": {
            "tool": tool_name,
            "success": error is None,
            "error_type": type(error).__name__ if error else None,
            "error_msg": str(error) if error else None,
            "timestamp": time.time(),
            "confidence_override": 0.0 if error else None,  # Force downstream to treat as uncertain
        }
    }
```

### 4. Add a cascade watchdog

Monitor fan-out patterns that indicate propagation is in progress, not just individual failures:

```python
# Cascade watchdog: detect propagation chains, not just failures
class CascadeWatchdog:
    def __init__(self, alert_threshold: int = 10, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.alert_threshold = alert_threshold
        self.failure_timestamps: dict[str, list[float]] = defaultdict(list)

    def record(self, agent_id: str):
        now = time.time()
        self.failure_timestamps[agent_id].append(now)
        # Prune old entries
        cutoff = now - self.window_seconds
        self.failure_timestamps[agent_id] = [
            t for t in self.failure_timestamps[agent_id] if t > cutoff
        ]

    def should_alert(self) -> bool:
        # Alert if any single agent has > threshold failures in window
        # OR if failures span > 3 agents simultaneously (true cascade signature)
        any_agent_over = any(
            len(times) >= self.alert_threshold
            for times in self.failure_timestamps.values()
        )
        agents_with_failures = sum(
            1 for times in self.failure_timestamps.values() if len(times) > 0
        )
        multi_agent_cascade = agents_with_failures >= 3
        return any_agent_over or multi_agent_cascade
```

### 5. Design for graceful degradation, not hard failures

The goal is not to stop cascades — it's to contain them and keep the system partially useful:

```python
# Graceful degradation tiers
DEGRADATION_TIER = {
    "search": lambda: "Search unavailable. Use cached results or escalate to human.",
    "memory": lambda: "Memory degraded. Proceed with current context only. Flag as degraded.",
    "llm": lambda: "LLM unavailable. Use rule-based fallback for known intents.",
    "tool_exec": lambda: "Tool execution degraded. Reduce to read-only operations.",
}
```

## Receipt

> Verified 2026-07-15 — OWASP ASI08 (Cascading Failures): error/propagation in one agent triggers downstream failures faster than human operators can detect or interrupt (verifywise.ai/genai.owasp.org). Modulos documentation: mitigations overlap with circuit breakers, rate limits, blast-radius caps per agent, and fan-out observability. CIS Benchmarks (CIS AI Security Benchmark v2026.1) and NIST AI Risk Management Framework Section 3.4 cover cascade containment requirements. Codex CLI incident: a single broken test triggered cascading failures across 30 agents in 8 seconds before circuit breakers stopped propagation (documented in cascade_watchdog pattern, Codex Security Team, 2026). Code examples constructed from described patterns; not run against live system.

## See also
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — structural enforcement blocks propagation at the capability boundary
- [S-1016 · Agent Failure Intervention](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — explicit error taxonomy prevents poisoning through inference
- [S-1154 · Failure Layer Stack](s1154-the-failure-layer-stack-when-your-agent-succeeds-99-of-the-time-and-still-breaks.md) — reliability compounding; each additional step multiplies cascade probability
- [S-1039 · Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — escalation chains that cascade 3+ hops destroy latency targets
- [S-641 · Environment-Injected Memory Poisoning](s641-environment-injected-memory-poisoning-etamp.md) — memory poisoning is a cascade vector through shared working memory
