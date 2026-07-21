# S-1406 · The Tool Chaining Failure Stack — When Your Agent Succeeds at Each Step and Fails at the Goal

Your agent chains four tool calls. Each call returns cleanly. HTTP 200, well-formed JSON, no exceptions. On step five, the agent reaches an answer that is confidently wrong — the retrieval tool returned stale data, the classifier misread a field, and both downstream steps proceeded without detecting either. The pipeline completed. The output is garbage. This is the tool chaining failure cascade: the dominant failure mode in production agentic systems, where errors propagate silently through sequential tool calls until they surface as confident nonsense at the output.

## Forces

- **Each tool call is a trust boundary.** When a tool returns, the agent trusts its output as ground truth for the next step. A single wrong output poisons every downstream decision.
- **200 OK is not a quality signal.** HTTP success and semantic correctness are independent. A tool that returns malformed data, stale records, or an empty result set still returns HTTP 200.
- **Error propagation compounds.** A 2025 study (OpenReview) found error propagation to be the most common failure pattern in failed LLM agent trajectories, with memory and reflection errors as the most frequent cascade sources. March 2026 production data across 6,259 agents and 4.5M tests found an aggregate success rate of 56.6% — most failures were not crashes but silent quality degradations through the chain.
- **Longer chains amplify failure probability.** Each additional step multiplies cumulative error risk. A chain with 4 tools has 4 independent failure surfaces; a chain with 12 has 12.
- **Context bloat and CoT compounding.** Chain-of-Thought prompting, which generally boosts performance, can introduce new error sources as longer prompts reduce accuracy in complex pipelines.
- **Users over-trust confident outputs.** Research shows users are less likely to question or verify outputs when agents deliver them with higher confidence — even when that confidence is misplaced.

## The Move

### 1. Validate at Every Boundary

Every tool output entering the next step must pass a schema + semantic guard before use. This is not optional hygiene — it is the primary defense against cascade.

```python
from pydantic import BaseModel, field_validator
from enum import Enum

class RetrievalResult(BaseModel):
    records: list[dict]
    source: str
    fetched_at: str  # ISO timestamp

    @field_validator('records')
    @classmethod
    def records_not_empty(cls, v):
        if not v:
            raise ValueError("Empty retrieval result — downstream steps cannot proceed")
        return v

    @field_validator('fetched_at')
    @classmethod
    def not_stale(cls, v):
        import datetime
        age = datetime.datetime.now() - datetime.datetime.fromisoformat(v)
        if age.total_seconds() > 300:  # 5-minute freshness
            raise ValueError(f"Retrieval result stale by {age.total_seconds():.0f}s")
        return v

def validate_and_forward(tool_output: dict, next_step_name: str):
    """Validate each tool output before it enters the next pipeline step."""
    schema = {
        "retrieval": RetrievalResult,
        "classification": ClassificationResult,
        "enrichment": EnrichmentResult,
    }.get(next_step_name)
    
    if not schema:
        return tool_output  # Passthrough for untyped steps
    
    try:
        validated = schema.model_validate(tool_output)
        return validated.model_dump()
    except ValueError as e:
        raise ToolChainValidationError(
            f"Step '{next_step_name}' received invalid input: {e}"
        ) from e
```

### 2. Plan-Then-Execute Architecture

Separate the planning phase (which tools, in what order, with what parameters) from the execution phase (run each tool, validate output, proceed or abort). This prevents the cascade where a wrong tool selection propagates through the entire execution.

```
Phase 1 — Plan:  [Agent] → "fetch_user(id) → classify(text) → enrich(profile) → format(json)"
Phase 2 — Execute:
  Step 1: fetch_user(id) → validate(schema + staleness) → [pass | ABORT]
  Step 2: classify(text) → validate(confidence > 0.7 | ESCALATE) → [pass | ESCALATE | ABORT]
  Step 3: enrich(profile) → validate(schema + non-empty) → [pass | FALLBACK]
  Step 4: format(json) → validate(schema + completeness) → [pass | HUMAN_REVIEW]
```

The key architectural decision: at each step, you have three choices — proceed, escalate to a different model, or abort entirely. Never let a step continue with an output it cannot meaningfully use.

### 3. Circuit Breaker on Tool Failure

Track the error rate per tool in the chain. When a tool exceeds a failure threshold (e.g., 3 consecutive errors or 20% failure rate in a 10-call window), trip the circuit breaker and short-circuit the chain to a safe fallback or human review.

```python
from collections import deque
from dataclasses import dataclass
import time

@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    window_seconds: float = 60.0
    half_open_after: float = 30.0
    
    _errors: deque = None
    _tripped_at: float = 0.0
    
    def __post_init__(self):
        self._errors = deque(maxlen=self.failure_threshold)
    
    def record(self, success: bool):
        if success:
            self._errors.clear()
        else:
            self._errors.append(time.time())
            self._cleanup_old()
    
    def _cleanup_old(self):
        cutoff = time.time() - self.window_seconds
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()
    
    def is_open(self) -> bool:
        if self._tripped_at and (time.time() - self._tripped_at) < self.half_open_after:
            return True
        self._cleanup_old()
        if len(self._errors) >= self.failure_threshold:
            self._tripped_at = time.time()
            return True
        return False
```

### 4. Keep Chains Short

Every additional step is a multiplicative failure surface. The 2026 production data is unambiguous: chains with 3 or fewer tools succeed at significantly higher rates than chains with 6 or more. If a chain exceeds 5 tools, decompose it into sub-agents, each with its own validation and abort path.

### 5. Trace Everything from Day One

Use span-attached evaluation — every tool call in the chain produces a span with input hash, output hash, execution time, and a quality flag. This enables cascade analysis: when the final output is wrong, you can backtrack to exactly which step produced the contaminated input.

## Receipt

> Verified 2026-07-20 — Sources: Future AGI "How Tool Chaining Fails in Production" (Mar 2026); OpenReview error propagation study (PFR4E8583W, 2025); 4.5M test production dataset (Mar 2026, n=6,259 agents, 10 regions); Zylos Research AI Agent Self-Healing (May 2026); Data-Gate AI Reliability Engineering (2026); Mikul Gohil Tool Calling Patterns (Nov 2025). All patterns tested against real pipeline failures. Circuit breaker and validation patterns are standard distributed systems practice adapted for LLM tool chains.

## See also

- [S-1302 · Agent Failure Handling and Recovery](s1302-agent-failure-handling-recovery.md) — general failure recovery; this entry focuses on the specific cascade mechanics of sequential pipelines
- [S-1018 · Component-Level Attribution](s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) — 200 OK is not correctness; attribution identifies which component broke
- [S-1067 · Orchestration Patterns](s1067-the-orchestration-pattern-stack-when-everyone-builds-the-wrong-topology-first.md) — topology choice determines failure modes; sequential chains fail differently than fan-out
