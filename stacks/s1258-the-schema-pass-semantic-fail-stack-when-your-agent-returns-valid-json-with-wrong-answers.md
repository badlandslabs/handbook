# S-1258 · The Schema-Pass, Semantic-Fail Stack

Your agent returns perfectly valid JSON. Every field matches the schema. The types are correct, required keys are present, and your parser never throws. Then you discover it approved a negative invoice amount, sent a prescription for the wrong diagnosis code, and enriched a contact with someone else's phone number. Structured output guarantees shape. It guarantees nothing about whether the shape contains truth.

## Forces
- Provider-native structured output (OpenAI `response_format`, Anthropic forced tool use, Gemini `responseSchema`) guarantees schema compliance — valid JSON, correct types, required fields — and nothing more
- Downstream systems consume schema-compliant data as if it were correct, propagating errors silently until they surface in audits, financial reports, or user complaints
- The failure mode is invisible to both the LLM (it satisfied the constraint) and the developer (the code never errors)
- Adding more schema fields increases surface area for hallucinations — each required field is a fabrication target when the model doesn't know the answer
- LLM semantic verification on every output is expensive; skipping it means wrong-but-valid data reaches production

## The move

Three-tier validation stack, each layer with distinct failure modes and cost profiles:

**Tier 1 — Structural/schema validation** (near-zero cost, always run)
- JSON parses without error
- Required fields present
- Types match (`amount` is a number, not a string)
- Enums have valid values
- This is what `response_format` already guarantees — but re-validate in your own code; provider-side bugs happen

**Tier 2 — Business-rule validation** (low cost, always run)
- Amount ≥ 0 (for financial outputs)
- Date is within expected range (not 1847)
- Email passes regex / DNS check
- Foreign keys reference existing entities
- These are typed as Pydantic validators or JSON Schema `$defs` with custom keywords
- Business rules are deterministic — no LLM needed

**Tier 3 — Semantic verification** (LLM call, run selectively)
- Is this entity actually the right one?
- Does this amount match the source document?
- Is this decision consistent with prior context?
- Trigger on: high-stakes outputs (financial, medical, legal), outputs where the model had low confidence signals, outputs that pass Tier 1–2 but fail a plausibility heuristic (e.g., an invoice amount 10× the historical average)

```python
from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

class InvoiceApproval(BaseModel):
    amount: float
    vendor_id: str
    approval_code: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Invoice amount must be positive")
        return v

    @field_validator("vendor_id")
    @classmethod
    def vendor_id_format(cls, v: str) -> str:
        if not v.startswith("VEN-"):
            raise ValueError("vendor_id must be VEN- prefixed")
        return v


class TieredValidator:
    """
    Three-tier validation for agent-structured outputs.
    Tier 1: schema (Pydantic). Tier 2: business rules (validators).
    Tier 3: semantic (LLM judge, gated by risk + confidence heuristics).
    """

    def __init__(self, llm_judge=None):
        self.llm_judge = llm_judge  # Optional: LLM-as-judge for Tier 3

    def validate(self, output: BaseModel, context: dict | None = None) -> dict:
        # Tier 1 + 2: Pydantic raises on structural or business-rule violation
        # No LLM call needed — ValueError on any failure
        errors = output.model_validate(output.model_dump())
        if errors:
            return {"tier": "1-2", "passed": False, "errors": errors}

        # Tier 3: semantic gate — only if high-stakes or low-confidence heuristic
        risk_signals = self._is_high_stakes(output, context)
        if risk_signals and self.llm_judge:
            semantic_ok = self.llm_judge.verify(
                output.model_dump(),
                context=context,
            )
            if not semantic_ok:
                return {"tier": "3", "passed": False, "reason": "semantic_fail"}

        return {"tier": "1-2", "passed": True}

    def _is_high_stakes(self, output: BaseModel, context: dict | None) -> bool:
        # Heuristic: flag financial amounts > $10k, medical codes, legal actions
        if hasattr(output, "amount") and output.amount > 10_000:
            return True
        if hasattr(output, "icd_codes") or hasattr(output, "legal_action"):
            return True
        return False


# Usage in agent loop:
validator = TieredValidator(llm_judge=judge_agent)
for tool_result in agent.execute_plan(plan):
    parsed = InvoiceApproval.model_validate_json(tool_result.content)
    result = validator.validate(parsed, context=conversation_context)
    if not result["passed"]:
        agent.retry_with_feedback(
            f"Validation failed at tier {result['tier']}: {result.get('errors', result.get('reason'))}"
        )
```

**Schema hygiene rule**: prune required fields to what downstream actually consumes. A 23-field schema for a 3-field answer is a hallucination factory — every required field the model doesn't know becomes a fabrication target.

## Receipt

> Verified 2026-07-17 — Pattern confirmed via three independent sources: Supergood Solutions "Structured Outputs Won't Save You" (March 2026), AgentMarketCap production enforcement guide (April 2026), and Tian Pan "Structured Generation" (March 2026). All three converge on the three-tier validation model (structural → business-rule → semantic) as the production standard. Real incident patterns: negative financial approvals, wrong-diagnosis ICD-10 codes, hallucinated contact enrichment — all schema-compliant. S-04 covers structural output guarantees; this entry covers the post-guarantee validation gap.

## See also
- [S-04 · Structured Output](s04-structured-output.md) — structural guarantees, no semantic layer
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — what to do when the agent is wrong
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — eval infrastructure for quality gates
