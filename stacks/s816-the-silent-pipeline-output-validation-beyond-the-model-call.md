# S-816 · The Silent Pipeline: Output Validation Beyond the Model Call

Your agent returned HTTP 200. The JSON parsed. The schema matched. The pipeline executed flawlessly — and applied a 1500% discount to 11,000 customer sessions. The model called `0.15` and the downstream parser interpreted it as `15`. The gap between "model output" and "business outcome" is where 68% of production AI incidents now live.

## Forces

- **The model call is the wrong place to focus reliability effort.** Teams instrument latency, failover, and prompt versioning — all necessary, none sufficient. The Stanford AI Index 2026 puts 68% of production agent incidents downstream of the model call: in parsing, type coercion, schema mismatch, and silent propagation.
- **HTTP 200 is a lie.** A successful API response from an LLM carries no guarantee of correct, safe, or well-typed output. The traditional APM stack shows green while the data goes red.
- **Type coercion is the silent assassin.** Python's `float("15.0")`, JavaScript's `Number(" fifteen ")`, and JSON.parse's permissive coercion silently transform unexpected strings into plausible-but-wrong values. These bugs survive every unit test because the code "works" — it just works on different data.
- **Structural validation catches format, not meaning.** Checking that a field is present and has the right type tells you nothing about whether the value is grounded, safe, or within business bounds.
- **Downstream propagation multiplies blast radius.** A hallucinated field written to a database infects every consumer. An incorrect email sent to a customer cannot be recalled. The later a validation error surfaces, the wider the damage.

## The move

Treat every model output as untrusted input to a separate, explicitly-validated subsystem. The model generates; a separate layer validates, coerces, and gates.

### 1. Schema-first output contracts

Do not ask the model to "return JSON." Define the contract first.

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class DiscountResult(BaseModel):
    rate: float          # must be 0.0–1.0, not a string
    unit: Literal["percent", "decimal"]
    applied_to: list[str]

    @field_validator("rate")
    @classmethod
    def rate_must_be_bound(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"rate {v} outside [0,1]")
        return v

    @field_validator("applied_to")
    @classmethod
    def non_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("applied_to cannot be empty")
        return v
```

The key move: `field_validator` raises before any coercion happens. `"0.15" as a string fails the `float` type check. `" fifteen "` fails the `Literal` check. The coercion layer never reaches downstream business logic.

### 2. Incremental verification at each pipeline stage

Validate each unit of work as it is produced, not the batch at the end.

```
model_output
    → parse_structured(schema_contract)   ← reject malformed immediately
    → validate_semantic(grounding_check) ← reject hallucinated facts
    → validate_business_rules(bounds)    ← reject out-of-range values
    → fenced_write(pipeline)             ← commit only after all gates pass
```

Each stage is a separate function with its own error type. When the discount parser rejects `"fifteen percent"`, the error is `CoercionError`, not a silent `15.0`.

### 3. The semantic exit gate

Before any downstream write (database, email, API call, another agent), run a grounded check:

```python
def semantic_exit_gate(output: dict, context: dict) -> bool:
    """
    Returns True only if the output is safe to propagate.
    """
    claims = extract_factual_claims(output)
    for claim in claims:
        if not claim.grounded_in(context.get("retrieved_docs", [])):
            raise SemanticGateError(f"Ungrounded claim: {claim.text}")
    if violates_business_invariant(output, context.get("account_state")):
        raise SemanticGateError(f"Business rule violated")
    return True
```

The gate runs in a fresh context — it cannot share the model's blind spots. This is why adversarial self-review (a separate model attacking the output) catches failures that the generating model misses.

### 4. Observable pipeline instrumentation

Every transformation — parse, coerce, validate, write — emits a span. Model outputs and downstream state are correlated in the same trace.

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("discount_pipeline") as span:
    span.set_attribute("input.raw", raw_output)
    parsed = parse_structured(raw_output, DiscountResult)
    span.set_attribute("output.rate", parsed.rate)
    semantic_exit_gate(parsed.model_dump(), context)
    span.set_attribute("pipeline.stage", "committed")
```

When the discount incident reproduces, the trace shows: `raw="fifteen percent"` → `CoercionError at parse stage` — not a mystery in the model call.

### 5. Fenced execution for downstream effects

Treat model output as a proposal, not a command. Stage writes, require explicit commit after all validation gates pass:

```python
# Stage 1: model generates
staged_changes = agent.propose_changes(intent)

# Stage 2: validate before committing
with fenced_transaction():
    for change in staged_changes:
        validate_change(change, business_context)
    commit(staged_changes)
```

A `fenced_transaction` rolls back all staged changes if any validation gate fails. The alternative — applying writes as the model produces them — makes partial corruption unrecoverable.

## Receipt

> Receipt pending — 2026-07-08
> Pattern distilled from: Stanford AI Index 2026 (68% downstream incident stat), Velocity Software Solutions production case study (1500% discount incident, Jun 2026), AgentMarketCap MCP Gateway report (Apr 2026), Zylos Research Agent FinOps (Apr 2026).

## See also

- [S-212](s212-semantic-output-validation-gate.md) — Semantic Output Validation Gate: validates *quality* before the output reaches anything that trusts it
- [S-433](s433-semantic-exit-gates.md) — Semantic Exit Gates: verifying correctness before delivery
- [S-803](s803-the-agent-failure-recovery-stack-getting-agents-to-resume-not-restart.md) — Agent Failure Recovery: silent failure is the worst failure mode; this entry is its structural fix
- [S-379](s379-the-observability-hole-traced-but-not-evaluated.md) — The Observability Hole: traces show what happened, not whether the output was right
