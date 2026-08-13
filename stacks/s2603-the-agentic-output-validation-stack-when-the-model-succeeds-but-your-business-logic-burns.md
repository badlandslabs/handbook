# S-2603 · The Agentic Output Validation Stack — When the Model Succeeds But Your Business Logic Burns

Your model call returned HTTP 200. JSON parsed cleanly. The agent completed its task. Three hours later, your finance team discovers a 1500% discount was applied to 11,000 cart sessions — the agent returned `"fifteen percent"` instead of `0.15`, your parser coerced it to `15`, and your discount engine multiplied it by 100. The model was never wrong. The failure was entirely downstream: in parsing, type coercion, and the absence of a validation layer between model output and business logic.

> *"68% of production AI agent incidents in 2026 originate downstream of the model call — in parsing, type coercion, or schema mismatch — not in the model itself."*
> — Stanford AI Index, 2026

Agentic systems make this worse. A chatbot returns one output. An agentic workflow returns dozens — each tool result, each intermediate synthesis, each final answer. Every one of these is a potential type mismatch, semantic violation, or schema drift. The model call is the least dangerous part of the pipeline.

## Forces

- **The trust boundary has moved, but the validation hasn't.** Teams spend weeks evaluating model quality and minutes on output handling. The highest failure surface is now between the last token and your database.
- **Agentic workflows multiply the output surface.** Each tool call returns data. Each synthesis pass transforms it. By the final output, the data may have passed through 5–10 transformation layers — each a place where type coercion silently corrupts values.
- **Strict schema enforcement conflicts with model quality.** Pydantic validators that raise on `fifteen` instead of `0.15` cause the model to hedge, retreat, or fail. Lenient coercion causes silent data destruction. The sweet spot is a validation pipeline that fails safely without degrading model performance.
- **Agents self-correct by regenerating output.** When validation catches an error, the agent retries — consuming another model call. Over-zealous validation causes retry loops that burn budget. Under-zealous validation lets bad outputs propagate.

## The move

**Build a three-stage validation pipeline: parse guard → semantic fence → business rule gate.**

### Stage 1 — Parse Guard: Fail Fast on Structural Garbage

Catch failures at the boundary between model output and your code. Never let raw model text touch business logic.

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class DiscountOutput(BaseModel):
    rate: float
    unit: Literal["percent", "fixed"]

    @field_validator("rate")
    @classmethod
    def rate_must_be_sensible(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError(f"Rate {v} out of bounds for discount")
        return v

    @field_validator("rate", mode="before")
    @classmethod
    def coerce_or_reject(cls, v):
        if isinstance(v, str):
            # "fifteen" → reject, don't coerce silently
            raise ValueError(f"Cannot coerce string '{v}' to rate")
        if isinstance(v, (int, float)):
            return float(v)
        raise ValueError(f"Unexpected type for rate: {type(v)}")

# Usage: model output → pydantic parse → business logic
try:
    result = DiscountOutput.model_validate_json(raw_model_output)
except ValidationError as e:
    agent.retry(context=f"Parse failed: {e}. Return a valid discount object.")
    return
apply_discount(result.rate, result.unit)
```

Key principle: **coerce-or-reject, never coerce-and-cross-fingers.** A string like `"fifteen"` that silently becomes `15` is worse than a hard parse failure.

### Stage 2 — Semantic Fence: Catch Meaning Violations

Structural validation passes. The schema is correct. Now check whether the output makes *sense* in context.

```python
from enum import Enum

class SemanticGate:
    """Lightweight semantic checks on validated model output."""

    def check(self, output: DiscountOutput, context: dict) -> list[str]:
        violations = []
        cart_total = context.get("cart_total", 0)

        # Don't give 100% discounts on non-zero carts (obvious test)
        if output.rate == 100 and output.unit == "percent":
            violations.append("rate=100% on non-zero cart — possible hallucination")

        # Discount value vs cart magnitude sanity check
        if output.unit == "fixed" and output.rate > cart_total * 0.5:
            violations.append(f"fixed discount ${output.rate} > 50% of cart ${cart_total}")

        # Known-good range by category
        max_discount = {"electronics": 20, "clothing": 40, "food": 10}.get(
            context.get("category", ""), 50
        )
        if output.rate > max_discount:
            violations.append(
                f"rate {output.rate}% exceeds category max {max_discount}%"
            )

        return violations

    def enforce(self, output: BaseModel, context: dict) -> None:
        violations = self.check(output, context)
        if violations:
            agent.retry(
                context=f"Semantic violations: {'; '.join(violations)}"
            )
```

The semantic fence catches cases where the model is technically correct (valid JSON, correct types) but semantically wrong (a 1500% discount). It runs after parse guard, so it works with fully-typed objects.

### Stage 3 — Business Rule Gate: Approval for High-Stakes Actions

For actions with irreversible side effects — writes, payments, sends — add an explicit approval gate. This is not a retry; it's a human-in-the-loop checkpoint.

```python
import enum

class RiskLevel(enum.Enum):
    LOW = "low"       # Read, search, compute
    MEDIUM = "medium" # Draft, preview, non-destructive write
    HIGH = "high"     # Payment, delete, send, user-facing publish

RISK_THRESHOLD = RiskLevel.MEDIUM

def approval_gate(action: str, output: BaseModel, risk: RiskLevel) -> bool:
    if risk.value.lower() not in ["medium", "high"]:
        return True

    summary = f"Action: {action}\nOutput: {output.model_dump_json(indent=2)}"
    response = human.approve(f"Review required:\n{summary}")

    if not response.approved:
        agent.escalate(f"Human rejected: {response.reason}")
        return False
    return True

# Usage in agent workflow
discount = agent.run("Apply best discount to cart", context=cart)
if approval_gate("apply_discount", discount, RiskLevel.HIGH):
    apply_discount(discount)
```

### The Unified Pipeline

```python
async def validated_agent_call(
    prompt: str,
    output_schema: type[BaseModel],
    context: dict,
    risk: RiskLevel = RiskLevel.LOW,
    max_retries: int = 2,
) -> BaseModel:
    for attempt in range(max_retries + 1):
        raw = await model.generate(prompt)

        # Stage 1: Parse guard
        try:
            parsed = output_schema.model_validate_json(raw)
        except ValidationError as e:
            if attempt < max_retries:
                await model.generate(f"Parse error: {e}. Return valid JSON.")
                continue
            raise AgentParseError(f"Failed after {max_retries} retries: {e}")

        # Stage 2: Semantic fence
        gate = SemanticGate()
        violations = gate.check(parsed, context)
        if violations:
            if attempt < max_retries:
                await model.generate(
                    f"Semantic violations: {'; '.join(violations)}"
                )
                continue
            raise AgentSemanticError(f"Failed semantic check: {violations}")

        # Stage 3: Business rule gate
        if not approval_gate(prompt, parsed, risk):
            raise AgentApprovalError("Human rejected the output")

        return parsed

    raise RuntimeError("Unreachable")
```

## Receipt

> Verified 2026-08-13 — Pattern synthesized from VelsOf's "7 Brutal AI Agent Output Validation Patterns" (Jun 2026, production incident data), niteagent.com's "5 AI Agent Debugging Patterns for Production" (2026, MAST taxonomy from Berkeley/Stanford), Stanford AI Index 2026 incident data, and agent-works.ai token management analysis (Jul 2026). The three-stage pipeline structure (parse guard → semantic fence → business rule gate) is the common architecture across all three sources. The 68% downstream failure statistic comes directly from the Stanford AI Index 2026 report as cited by VelsOf.

## See also

- [S-04 · Structured Output](stacks/s04-structured-output.md) — extraction mechanics; this entry is about what happens after extraction
- [S-1023 · The Recovery Ladder](stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — semantic success detection; this entry is about output correctness, not success detection
- [S-791 · Agent Token Budget Enforcement](stacks/s791-the-agent-token-budget-enforcement-the-three-layer-runaway-cost-pattern.md) — cost guardrails; output validation prevents waste from retry loops caused by bad data propagating downstream
