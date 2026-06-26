# R-02 · Reasoning Models

Models that "think before they answer" — spending extra tokens on internal reasoning before producing output. What changes, what doesn't, and when to use them.

## Forces
- Harder reasoning tasks (math, multi-step logic, code) benefit from extended thinking
- Reasoning tokens are expensive — the model may spend 10K tokens thinking to save 1 wrong answer
- Not every task needs reasoning; using it on simple tasks wastes budget
- The quality ceiling is higher, but so is the latency and cost

## The move

**What reasoning models do differently:**
Standard model: receives prompt → generates answer.  
Reasoning model: receives prompt → generates internal chain-of-thought (often hidden from output) → generates answer informed by that reasoning.

**When to use:**
- Multi-step math or logic problems
- Complex code generation or debugging
- Tasks requiring planning across many constraints
- Any case where standard models demonstrably fail and you've ruled out prompt engineering

**When NOT to use:**
- Simple extraction, classification, or formatting — reasoning adds cost, zero benefit
- Latency-sensitive user-facing features — reasoning adds seconds to minutes
- Tasks where the answer is retrieved, not reasoned (use RAG instead)

**Models with reasoning capability (mid-2026):**
- Claude (extended thinking mode) — set `thinking: {"type": "enabled", "budget_tokens": N}`
- OpenAI o3, o4-mini — reasoning is automatic, not toggled
- DeepSeek R1 — open-source, strong on math/code

**Claude extended thinking:**
```python
response = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=16000,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000  # max tokens for internal thinking
    },
    messages=[{"role": "user", "content": "Solve this step by step: ..."}]
)
# Thinking blocks are separate from answer blocks in response.content
```

**Cost reality:** thinking tokens are billed at full input/output rates. A 10K thinking budget on a complex problem can cost more than 10 standard calls. Measure before using in production loops.

## Receipt
> Receipt pending — 2026-06-25. Extended thinking API syntax follows Anthropic documentation. Budget_tokens behavior and billing confirmed in docs; run against your task to verify cost impact.

## See also
[R-01](r01-model-landscape.md) · [R-07](r07-post-training-rlvr.md) · [S-24](../stacks/s24-self-consistency.md) · [S-06](../stacks/s06-model-routing.md) · [S-02](../stacks/s02-context-budget.md)

## Go deeper
Keywords: `chain of thought` · `extended thinking` · `o3` · `o4-mini` · `DeepSeek R1` · `reasoning budget` · `test-time compute` · `inference scaling`
