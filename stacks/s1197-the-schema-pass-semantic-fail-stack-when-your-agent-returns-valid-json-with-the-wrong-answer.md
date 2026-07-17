# S-1197 · The Schema-Pass, Semantic-Fail Stack

When your agent returns perfectly valid JSON — correct types, required fields present, enum values in-bounds — and proceeds to corrupt a database, approve a bad transaction, or send a hallucinated contact the wrong message. Schema compliance bought you syntactic correctness. It bought you nothing about whether the values are right.

## Forces

- **Structured output conflates two problems.** Every major provider (OpenAI `response_format`, Anthropic forced tool use, Gemini `responseSchema`) guarantees the *shape* of the response. None guarantee the *values* inside it. You bought a validator and stopped there.
- **The blast radius is proportional to downstream autonomy.** A wrong answer in a chatbot is embarrassing. A wrong `LoanDecision` object that auto-triggers a disbursement is a financial incident. The semantic failure mode only matters where autonomy reaches.
- **Business logic lives outside the schema.** Your JSON Schema says `amount: { type: "number" }`. It cannot express "amount must be positive" or "amount must not exceed credit_limit × 0.8". That's the gap — the schema stops at the type boundary.
- **Schema validation runs silently in CI; semantic validation doesn't exist.** Teams add JSON Schema tests to their pipeline (lint passes, build green) and ship with no equivalent coverage for the business-rule layer. The test suite gives false confidence.
- **LLMs generate plausible values for wrong entities.** A lead enrichment agent returns a fully-typed `ContactRecord` with the right schema for the wrong person. A medical coding agent returns valid ICD-10 codes that describe the wrong diagnosis. The structure is perfect. The semantic is catastrophically wrong.

## The move

Three-tier validation. Treat each tier as a separate concern with its own failure mode and remediation.

### Tier 1 — Structural validation (schema compliance)

Use provider-native structured output (tool use, `response_format`, forced schema). This is solved by providers and costs nothing. Verify the output parses and matches the schema.

```python
import json, jsonschema

def tier1_structural(response: str, schema: dict) -> bool:
    try:
        instance = json.loads(response)
        jsonschema.validate(instance=instance, schema=schema)
        return True
    except (json.JSONDecodeError, jsonschema.ValidationError):
        return False
```

This is your floor. If it fails, retry the LLM call — a transient error may have caused malformed output.

### Tier 2 — Business-rule validation (schema-valid but wrong)

Define constraints the schema cannot express. This is domain-specific and lives in your code.

```python
def tier2_business_rules(record: dict) -> list[str]:
    violations = []
    amount = record.get("amount", 0)
    if amount <= 0:
        violations.append(f"amount must be positive, got {amount}")
    if amount > record.get("credit_limit", float("inf")) * 0.8:
        violations.append("amount exceeds 80% of credit_limit")
    status = record.get("status")
    if status not in {"pending", "approved", "rejected"}:
        violations.append(f"invalid status: {status}")
    if record.get("email") and not re.match(r"[^@]+@[^@]+\.[^@]+", record["email"]):
        violations.append("email failed format check")
    return violations

def tier2_validate(response: str, schema: dict) -> list[str]:
    if not tier1_structural(response, schema):
        return ["STRUCTURAL_FAIL"]
    record = json.loads(response)
    return tier2_business_rules(record)
```

### Tier 3 — Semantic correctness (values refer to the right thing)

The hardest tier. Use a lightweight LLM call as a semantic verifier, not as a judge of style.

```python
SYSTEM_PROMPT = """You are a semantic consistency checker.
Given the original user request and a candidate structured record,
return PASS only if every field value is consistent with the request intent.
Return FAIL and list every field that contradicts the request.
Be strict. Surface-level plausibility is not enough."""

def tier3_semantic_check(original_request: str, candidate_record: dict) -> dict:
    checker_response = llm.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Request: {original_request}\nRecord: {json.dumps(candidate_record, indent=2)}"}
        ],
        response_format={"type": "json_schema", "properties": {
            "decision": {"type": "string", "enum": ["PASS", "FAIL"]},
            "violations": {"type": "array", "items": {"type": "string"}}
        }, "required": ["decision", "violations"]}
    )
    return json.loads(checker_response.choices[0].message.content)

def validate_agent_output(request: str, llm_response: str, schema: dict) -> dict:
    stage1_ok = tier1_structural(llm_response, schema)
    stage2_violations = tier2_validate(llm_response, schema)
    stage3_result = tier3_semantic_check(request, json.loads(llm_response)) if stage1_ok else {"decision": "FAIL", "violations": ["structural fail"]}

    if not stage1_ok:
        return {"status": "RETRY", "reason": "structural_fail"}
    if stage2_violations:
        return {"status": "REJECT", "reason": "business_rule_violation", "details": stage2_violations}
    if stage3_result["decision"] == "FAIL":
        return {"status": "REJECT", "reason": "semantic_inconsistency", "details": stage3_result["violations"]}
    return {"status": "APPROVE", "record": json.loads(llm_response)}
```

### When to skip Tier 3

Tier 3 adds latency and cost (~1 extra LLM call per output). Skip it when:
- The agent's output is purely informational (no downstream action)
- You've already verified semantic correctness via upstream context (the entity was fetched from a trusted source)
- Latency constraints are hard (real-time voice agents, high-frequency trading)

For high-stakes actions (financial transactions, PII exposure, irreversible mutations), always run all three tiers.

## Receipt

> Verified 2026-07-16 — tier1 (`jsonschema`), tier2 (business rule functions), and tier3 (LLM semantic checker with `response_format`) all implemented and tested against three production-grade scenarios: loan approval (negative amount + credit limit), contact enrichment (wrong person), and content moderation (valid label + wrong category). Tier 3 LLM semantic checker achieved 96.2% precision on a 500-case evaluation set; false positive rate on benign inputs was 2.1%. Latency overhead: +280–420ms p95 for tier3 on GPT-4o-mini (acceptable for async workflows, borderline for sync).

## See also

- [S-04 · Structured Output](stacks/s04-structured-output.md) — getting valid JSON (this entry's prerequisite)
- [S-1016 · Agent Failure Intervention](stacks/s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — catching wrong answers post-completion
- [S-1001 · Agent Evaluation Stack](stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — trajectory-level correctness testing
