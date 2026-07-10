# S-906 · The Self-Correction Illusion — When Your Agent Finds Everyone Else's Bugs But Misses Its Own

Your agent reviews a colleague's code and flags the exact bug. Your agent reviews its own code and signs off on the same class of bug it just caught in someone else's. This is not a fluke. It is a structural property of how LLMs process self-directed versus third-party evaluation — and it makes naive self-correction loops in agentic systems unreliable in ways that are hard to detect.

## Situation

You build an agent loop: the agent generates output, a verifier step checks for errors, the agent corrects and re-generates. The loop runs three times. The agent never catches the class of mistake that made it into the first draft. The verification step is inside the same agent's context window. Every round, the agent is both defendant and judge.

## Forces

- **Self-correction rate on third-party content is dramatically higher than on own output.** Models trained with reasoning traces show near-ceiling correction rates when evaluating equivalent claims made by others, but significantly lower rates when evaluating their own prior outputs. The gap is not a reasoning deficit — it is structural.
- **The addressability account: you can't easily re-examine what you've already internalized.** When a model encounters a claim as its own output, it has already committed to it as a coherent narrative. The act of generation closes the loop. When the same claim arrives as external input, it is available as a verifiable object. The agent can step back and interrogate it. Self-generated content loses this critical distance.
- **Naive self-correction loops are circular by design.** If the verification step lives inside the same model's context — not inside a separate process with its own identity and weights — the verification inherits the model's blind spots, not its strengths.
- **The "correct others, not self" gap is amplified in agentic loops.** A single-step re-generate-and-retry adds one more self-generated iteration to the context. If the agent started with a wrong assumption, each iteration builds a narrative that makes that assumption more coherent, not less.

## The move

### 1. Never put verification inside the same model call as generation

Separate the judge from the defendant. The generation agent and the verification agent should be distinct — different system prompts, ideally different model configurations or at minimum different inference contexts. The verification step should receive the output as *external evidence*, not as a continuation of internal reasoning.

```python
# Wrong: verification inside same agent context
response = agent.generate(prompt)
verified = agent.verify(response, criteria)  # Same model, same blind spots

# Right: verification as a separate agent with different identity
response = generator_agent.generate(prompt)
verified = verifier_agent.verify(output=response, criteria=criteria, role="external_auditor")
```

### 2. Make verification inputs maximally external

Pass claims as structured, de-anchored evidence. Strip ownership cues — do not label outputs as "my answer" or "the agent said." Present each claim as a standalone proposition to be evaluated. The framing shift from "am I right?" to "is this claim correct?" recovers the third-party correction advantage.

```python
# Strip self-referential context from verification inputs
verification_prompt = f"""
Claim to evaluate: "{extracted_claim}"
Context: [present only the raw facts, not the model's own narrative]
Criteria: [explicit, de-anchored evaluation rubric]
Role: You are an independent auditor evaluating this claim, not the author.
"""
```

### 3. Use external tooling for unambiguous failure classes

For error types with ground truth — type errors, schema violations, API contract breaches, computed arithmetic — don't rely on the model's self-assessment at all. Use deterministic checkers: linters, validators, contract tests, schema assertions. These are immune to the self-correction illusion.

```python
# Deterministic checks before model-based evaluation
schema_valid = validate_json_schema(agent_output, required_schema)
type_valid = mypy_check(generated_code)  # No model involved
assert test_result == expected  # Ground truth comparison

# Only fall back to model evaluation for ambiguous cases
if schema_valid and type_valid:
    quality_score = evaluator_agent.evaluate(..., role="critical_reviewer")
```

### 4. Add an explicit contradiction search step

Before accepting a self-corrected output, inject a targeted adversarial prompt: "Find the strongest argument that this output is wrong." This externalizes the self-critique and recovers some of the third-party correction gap within a single model.

```python
adversarial_verdict = adversarial_agent.challenge(
    output=response,
    challenge_type="contradiction_search"
)
if adversarial_verdict.strong_challenge_found:
    response = agent.regenerate(prompt, constraints=adversarial_verdict.challenges)
```

### 5. Track correction rates by ownership, not just by outcome

Instrument your self-correction loop to distinguish: (a) did the agent correct an external error? (b) did it correct its own error? (c) did it fail to correct its own error? The self-correction illusion will surface as a systematic gap between (a) and (b) rates — not as random noise.

## Receipt

> Verified 2026-07-10 — Chen et al. (2026), arxiv:2606.05976: LLM correction rate on third-party claims significantly exceeds self-correction rate on equivalent self-generated claims, explained by the "addressability account" (loss of critical distance on self-generated content). ReliabilityBench (arxiv:2601.06112) methodology confirms fault-injection-based eval is the strongest signal; self-verification alone produces falsely high confidence. Microsoft Agent Framework (2026) documentation on handoffs explicitly notes that context carryover in self-review scenarios degrades evaluator objectivity — supporting the intervention of structurally separate verification agents.

## See also

- [S-903 · The Cascading Failure Stack](s903-the-cascading-failure-stack-when-your-agent-succeeds-nine-times-and-fails-once-that-matters.md) — failure compounding in agent loops
- [S-229 · Iteration Budgets](s229-iteration-budgets-the-loop-control-pattern-max_iterations-gets-wrong.md) — why looping agents consume tokens without converging
- [S-896 · The Stochastic Test Suite](s896-the-stochastic-test-suite-when-your-agent-improvement-is-a-statistical-artefact.md) — why eval quality determines whether you catch failures at all
- [S-212 · Semantic Output Validation Gate](s212-semantic-output-validation-gate.md) — structured output verification patterns
