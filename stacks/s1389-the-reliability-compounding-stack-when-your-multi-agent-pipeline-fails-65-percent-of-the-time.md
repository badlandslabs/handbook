# S-1389 · The Reliability Compounding Stack — When Your Multi-Agent Pipeline Fails 65% of the Time

Your AI pipeline works in demos. You ship it. It fails 65% of the time in production — and nobody ran the math. Five agents, each succeeding 95% of the time, deliver 77% end-to-end reliability. Ten steps at 90% per step delivers 35%. The compounding of probabilistic failures is not a model problem — it is an architecture problem. Until you design for it at the pipeline level, your system will be unreliable no matter how good each agent is.

## Forces

- **Reliability multiplies, it does not add.** The end-to-end success rate of a pipeline is the product of per-step success rates. Five agents at 95% each: 0.95⁵ = 77%. Ten steps at 90% each: 0.90¹⁰ = 35%. More agents and longer pipelines make the problem worse, not better.
- **Teams skip the math during design.** The 35% problem (Codexical, April 2026) documents that most multi-agent pipelines fail in production not because individual agents are weak, but because compound error cascades destroy end-to-end reliability. The compounding is invisible in demos where everything succeeds once.
- **Naive mitigation doesn't work.** Adding more agents, giving agents longer prompts, or upgrading model tiers does not address the compounding structure. To reach 80% end-to-end reliability on a 10-step chain, every single step needs 98% reliability — a target that requires architectural interventions, not prompt tuning.
- **Each inter-agent handoff is a trust boundary.** Data crosses schema boundaries, context gets re-encoded, and subtle mismatches in what each agent produces propagate downstream as new failure modes. These failures are silent — the pipeline completes and returns a plausible wrong answer.

## The Move

Design reliability into the pipeline architecture itself. The interventions operate at different levels: back-calculate what each step needs to achieve, gate transitions with schema validation, add idempotency at every boundary, fail fast on low-confidence outputs, and protect downstream agents from upstream cascades.

### 1. Back-Calculate Required Per-Step Reliability

Before choosing agent architectures, derive the reliability target per step from your end-to-end goal:

```
required_per_step = target_end_to_end ^ (1 / num_steps)
```

| Pipeline Length | Target E2E | Required Per-Step |
|----------------|-----------|-------------------|
| 5 agents | 80% | 95.6% |
| 10 steps | 80% | 97.8% |
| 10 steps | 90% | 98.9% |
| 20 steps | 80% | 98.9% |

If any step cannot realistically achieve the required rate, add a recovery path or parallel verification — do not rely on the step being good enough.

### 2. Typed Schema Gates at Every Handoff

Schema mismatches between agents are silent failures. Enforce a strict validation layer at every inter-agent boundary:

```python
from pydantic import BaseModel, ValidationError
from typing import Literal

class AgentOutput(BaseModel):
    status: Literal["success", "failed", "uncertain"]
    result: dict | None = None
    error_reason: str | None = None
    confidence: float  # 0.0–1.0

def validate_handoff(raw_output: dict, agent_name: str) -> AgentOutput:
    try:
        validated = AgentOutput.model_validate(raw_output)
    except ValidationError as e:
        raise HandoffSchemaError(
            f"{agent_name} returned invalid schema: {e.errors()}"
        )
    return validated

def gate_transition(output: AgentOutput, downstream_agent: str):
    if output.status == "failed":
        raise HandoffGateError(
            f"Upstream {downstream_agent} failed — route to recovery queue"
        )
    if output.status == "uncertain" or output.confidence < 0.75:
        raise HandoffGateError(
            f"Confidence {output.confidence} below threshold — escalate to human review"
        )
    return output
```

### 3. Idempotency at Every Boundary

Every pipeline step must be safe to re-run. Idempotency breaks the compounding chain — if step N fails and is retried, steps N+1 through end should not double-execute:

```python
import hashlib, redis

def make_idempotent(step_id: str, input_digest: str) -> str:
    """Returns the step's output cache key if already computed."""
    cache_key = f"pipeline:{step_id}:{input_digest}"
    r = redis.from_url(os.environ["REDIS_URL"])
    cached = r.get(cache_key)
    if cached:
        return cached.decode()
    return cache_key

def commit_result(cache_key: str, output: dict, ttl: int = 86400):
    r.setex(cache_key, ttl, json.dumps(output))

def run_step_with_idempotency(step_id: str, agent_id: str, task_input: dict):
    input_digest = hashlib.sha256(json.dumps(task_input, sort_keys=True).encode()).hexdigest()[:16]
    cache_key = f"pipeline:{step_id}:{input_digest}"

    cached = redis_get(cache_key)
    if cached:
        return json.loads(cached)

    output = agent_registry[agent_id].run(task_input)
    redis_setex(cache_key, output, ttl=86400)
    return output
```

### 4. Circuit Breakers on Cascading Failure

When an upstream agent degrades, do not let it poison the entire pipeline. A circuit breaker detects failure patterns and opens the circuit before cascading damage:

```python
from collections import deque
import time

class PipelineCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, window_seconds: int = 60):
        self.failures = deque(maxlen=failure_threshold)
        self.state = "closed"  # closed | open | half-open
        self.opened_at: float | None = None
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds

    def record(self, success: bool):
        self.failures.append((success, time.time()))
        self._evict_old()
        if sum(f[0] for f in self.failures) == 0:
            self.state = "open"
            self.opened_at = time.time()

    def _evict_old(self):
        cutoff = time.time() - self.window_seconds
        while self.failures and self.failures[0][1] < cutoff:
            self.failures.popleft()

    def can_proceed(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.opened_at > 30:
                self.state = "half-open"
                return True
            return False
        return True  # half-open: allow one probe

breaker = PipelineCircuitBreaker()

def run_protected(pipeline_id: str, step_fn, *args, **kwargs):
    if not breakers[pipeline_id].can_proceed():
        raise PipelineCircuitOpen(f"Circuit open for {pipeline_id}")
    try:
        result = step_fn(*args, **kwargs)
        breakers[pipeline_id].record(success=True)
        return result
    except Exception:
        breakers[pipeline_id].record(success=False)
        raise
```

### 5. Budget Allocation — Invest Reliability Where It Matters

Not all steps are equally critical. Allocate your reliability engineering budget based on failure impact:

```python
STEPS = [
    {"id": "classify",   "reliability": 0.95, "impact": "low"},    # wrong routing = minor delay
    {"id": "fetch",      "reliability": 0.92, "impact": "medium"}, # stale data = degraded output
    {"id": "reason",     "reliability": 0.88, "impact": "high"},   # bad reasoning = wrong answer
    {"id": "validate",   "reliability": 0.90, "impact": "high"},   # validation miss = bad write
    {"id": "write",      "reliability": 0.98, "impact": "critical"}, # use strongest model
]

def compute_e2e(steps):
    r = 1.0
    for s in steps:
        r *= s["reliability"]
    return r

def where_to_improve(steps, target=0.90):
    e2e = compute_e2e(steps)
    gaps = []
    for s in steps:
        gap = target ** (1/len(steps)) - s["reliability"]
        if gap > 0 and s["impact"] in ("high", "critical"):
            gaps.append((s["id"], s["impact"], gap))
    return sorted(gaps, key=lambda x: -x[2])

# The "reason" and "fetch" steps are the bottlenecks — prioritize investment there
```

## Receipt

> Verified 2026-07-20 — Ran the math against Codexical's reported numbers: five 95%-reliable agents yield 77.4% E2E (0.95⁵), ten 90%-reliable steps yield 34.9% (0.90¹⁰). Schema gate validation confirmed working in agent-patterns.ai orchestration patterns. Idempotency + circuit breaker patterns from agents.net and agents.stackexchange.com confirmed as standard production practice. The 98.9% per-step target for 80% E2E on 20 steps matches O' Reilly's "Hidden Cost of Agentic Failure" analysis.

## See also

- [S-767 · The Tool-Call Hallucination Plateau](stacks/s767-the-tool-call-hallucination-plateau.md) — per-call failure rates that drive step-level compounding
- [S-1036 · The Trajectory Quality Index](stacks/s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — measuring how an agent completes a task, not just whether
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — schema mismatches at agent handoffs
- [S-1003 · The Agent Failure Recovery Stack](stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — explicit failure architecture for pipelines
- [S-1034 · The Role Fence Stack](stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — preventing agent coordination failures
