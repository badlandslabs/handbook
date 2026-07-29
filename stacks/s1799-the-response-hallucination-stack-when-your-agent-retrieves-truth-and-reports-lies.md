# S-1799 · The Response Hallucination Stack — When Your Agent Retrieves Truth and Reports Lies

Your RAG pipeline returns a document. Your agent reads it. Your agent then confidently states something that contradicts the document. The document said "$26.97B." The agent said "$16.3B." Every tool call was successful. Every API returned HTTP 200. No error was raised. The retrieval worked perfectly — and the agent lied anyway. This is response hallucination: the failure mode that lives between the tool output and the final answer, where correct data enters the context and wrong data exits.

This is not tool hallucination. Tool hallucination is the tool returning fabricated data. Response hallucination is the model receiving correct data and producing incorrect output anyway. They require different fixes. Most teams only address the first.

## Forces

- **The completion model and the extraction model are the same model with different objectives.** When a model extracts data via tool call and then generates a natural language response, it is performing two distinct cognitive tasks: information retrieval and text generation. The generation head optimizes for fluency, coherence, and pattern completion — not for fidelity to the retrieval output. These objectives conflict. The model will sometimes prefer a plausible-sounding number over the exact retrieved number, especially when the retrieval output is mixed with other context.

- **LLM numeracy is structurally weaker than LLM literacy.** Models read text better than they read numbers. When a tool returns a structured payload like `{"revenue": "USD 26,974,000,000"}`, the model's extraction quality degrades significantly compared to the same information embedded in a prose paragraph. Numeric extraction errors compound: the model misreads "26,974" as "26.974" (wrong scale) or "26.97B" (dropping the comma), and then generates confident text around the misread value.

- **Confidence transfer from context to output.** LLMs transfer the high confidence of their general language modeling to specific factual claims. The model is highly confident in its ability to produce grammatically correct, well-formed sentences about financial data — and this confidence bleeds into the factual accuracy of the claims. A low confidence on the specific claim, combined with high confidence on the general form, produces confident wrong answers.

- **Context mixing amplifies hallucination.** When a retrieved document contains the correct answer alongside other relevant-but-contradictory information (an earlier year's figure, a competitor's figure, a figure from a different report), the model may synthesize across them incorrectly. The "best of both" heuristic — taking the most salient numbers from different sources — produces confident-sounding composite lies.

## The move

**The fix is a fact-consistency verification layer between retrieval and response.** Treat the tool output as ground truth and verify the response against it before delivery. This is different from self-correction (which relies on the model's own judgment) and different from output validation (which checks format, not content).

### Core pattern: structured extraction with forced fidelity

Never let the model read a number and then paraphrase it. Extract to structured output first, then render separately.

```python
# BAD: model reads number and generates prose around it
def bad_answer(question: str, doc: str) -> str:
    prompt = f"Document: {doc}\nQuestion: {question}\nAnswer:"
    return llm.complete(prompt)  # model paraphrases — may misstate numbers

# GOOD: extract to structured data, then render
def good_answer(question: str, doc: str) -> dict:
    extract_prompt = f"""Extract exact values from this document.
Return ONLY valid JSON. Do NOT paraphrase or round numbers.
Document: {doc}
Question: {question}"""
    raw = llm.complete(extract_prompt, json_mode=True)
    data = json.loads(raw)
    # Verify the extracted value matches the document
    return {"question": question, "answer": render_answer(data), "source": data}
```

### Pattern 2: Fact-tethered generation

For cases where you must generate prose (not just extract), anchor every factual claim to a source tag, then verify tagged claims against the source.

```python
SYSTEM_PROMPT = """When you state a fact, tag it with its source:
[source: tool_name, field: field_name]

Before responding, check every tagged claim against the actual tool output.
If any claim contradicts the source, replace it with the exact source value.
Do not round, approximate, or paraphrase numeric values."""

def fact_checked_answer(question: str, tool_outputs: list[dict]) -> str:
    prompt = build_prompt(question, tool_outputs)
    draft = llm.complete(prompt, system=FACT_TETHERED_SYSTEM)

    # Post-generation: scan for numeric claims and verify
    claims = extract_numeric_claims(draft)
    for claim, field in claims:
        source_val = lookup_source_field(field, tool_outputs)
        if not numbers_match(claim, source_val):
            draft = draft.replace(claim, str(source_val))
    return draft
```

### Pattern 3: Contrast verification

Ask the model to explicitly compare its answer against the retrieved data.

```python
VERIFY_PROMPT = """Given: retrieved_data = {retrieved}
Your answer: {draft}

Check each factual claim in your answer against retrieved_data.
List any contradictions (claim vs. retrieved value).
If no contradictions, respond "VERIFIED."
If contradictions exist, respond with the corrected values."""
```

### Pattern 4: Tool-output sandboxing

Restrict the model's access to raw tool outputs during response generation. Use a retrieval agent to handle data fetching and a separate completion agent that receives only pre-validated structured data. This prevents the completion model from mixing retrieved facts with its own parametric knowledge.

```python
class FactTetheredAgent:
    def __init__(self):
        self.retriever = RetrieverAgent()  # has tool access, no completion
        self.answerer = AnswerAgent()       # completion only, no tools

    def run(self, question: str) -> str:
        # Step 1: retrieve structured data — no completion here
        retrieved = self.retriever.extract(question, tools=[...])
        # Step 2: answer from structured data only
        return self.answerer.generate(question, structured_data=retrieved)
```

## Tradeoffs

- **Extra LLM call overhead.** Fact-checking adds 1–2 inference passes per answer. Budget this against the cost of a wrong answer.
- **Verification can also hallucinate.** A self-verification step still uses the same model. For high-stakes outputs, use a second model or a smaller verifier for the fact-check pass.
- **Structured extraction changes the UX.** If users expect prose answers, you need a separate rendering step. This is worth it — separating extraction from generation is the cleanest structural fix.
- **Not all hallucination is numeric.** The pattern extends to dates, names, specifications, and any factual claim that can be extracted, tagged, and verified.

## When to reach for this

- High-stakes outputs: financial data, legal facts, medical information, regulatory compliance
- RAG pipelines where retrieval is reliable but generation is not
- Multi-tool pipelines where output from one tool is used by another agent or passed to a user
- When you already have high tool-call accuracy but still see fact errors in responses

## Receipt

> Verified 2026-07-29 — Pattern validated against vectara/awesome-agent-failures (Apache 2.0, ~190 stars) failure mode taxonomy. The "Response Hallucination" entry explicitly documents the Nvidia revenue example: tool output = "$26.97B", agent response = "$16.3B." The S-767 "Tool-Call Hallucination Plateau" entry covers tool-output fabrication but does not cover response corruption of correct data — that gap is what this entry addresses.

## See also

- [S-767 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — tool output is fabricated; this entry covers when tool output is correct but the response still lies
- [S-1171 · The Claim Provenance Stack](s1171-the-claim-provenance-stack-when-one-false-claim-becomes-team-consensus-in-3-rounds.md) — cross-agent propagation of false claims; this entry covers the single-agent version
- [S-1313 · The Failure Barrier Stack](s1313-the-failure-barrier-stack-when-your-agent-returns-200-ok-and-everything-is-wrong.md) — success-coded failures; response hallucination is a success-coded failure that lives inside a successful tool call
