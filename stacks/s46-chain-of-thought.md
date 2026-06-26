# S-46 · Chain-of-Thought Elicitation

Chain-of-thought prompting makes the model show its reasoning before answering. For multi-step problems it improves accuracy; for simple tasks it adds 3–4× cost with no benefit; for reasoning models it wastes tokens and can actively degrade answers. The decision is one question: does the task benefit from the model working through intermediate steps?

## Situation

A pipeline adds "think step by step" to every prompt because it "helps the model." For the math and planning tasks it was benchmarked on, it did. But the same pipeline also handles simple Q&A and data extraction. Those tasks now produce 4× more output tokens with no accuracy gain — $441/month in extra output cost at 10k calls/day, and the extraction results are no better.

## Forces

- Chain-of-thought works by forcing the model to populate a reasoning trace before committing to an answer. On multi-step problems, errors in early steps are self-corrected when the model re-reads its own reasoning. On single-step tasks, the trace adds nothing to fix.
- CoT is orthogonal to reasoning models. Claude with extended thinking, GPT-o3, and similar models reason internally regardless of your prompt. Telling them to "think step by step" prompts them to produce *visible* CoT in the response — which is usually redundant and more expensive. Extended thinking is the API control for reasoning-model CoT budget.
- The cost of CoT is in output tokens, which are 4–5× more expensive than input tokens. A 23-token direct answer becomes a 121-token prompted CoT response — 4.1× the cost, driven by output pricing.
- There are two elicitation forms: prompted ("let's think step by step" in the user message) and structured (a `<thinking>` block in the prompt format). Structured is more controllable — the thinking is isolated from the answer, making extraction reliable. Prompted CoT mixes reasoning and answer, requiring parsing.
- The scratchpad pattern is the production form of structured CoT. Ask for reasoning in a `<thinking>` block and the answer in `<answer>`. The model can reference its own steps; you can extract just the answer without parsing the reasoning trace.

## The move

**Elicit CoT only when the task has intermediate steps where errors could propagate.**

| Task type | Elicit CoT? | Reason |
|---|---|---|
| Multi-step math / logic | Yes | Steps catch carry errors; gains well-documented |
| Complex planning / scheduling | Yes | Contradiction surfaces in trace before output |
| Ambiguous classification | Yes | Reasoning reveals which edge-case rule applies |
| Simple Q&A / lookup | No | 10-token answer → 100-token answer for same result |
| Data extraction (JSON fields) | No | CoT adds tokens without improving schema adherence; use T=0 |
| Creative writing | No | Pre-reasoning inhibits natural generation |
| Reasoning model (R-02) | No | Model reasons internally; prompting CoT duplicates it |

**Use the structured scratchpad form for production:**

```
<prompt>
Classify the support ticket priority (critical/high/medium/low).

Use <thinking> to work through the issue before answering. Return only the priority label in <answer>.

Ticket: [TICKET_TEXT]
</prompt>

Expected output:
<thinking>
The ticket says users cannot log in — this is a login outage affecting all users. That maps to "critical" by the escalation policy (100% user impact).
</thinking>
<answer>critical</answer>
```

Parse with: `output.match(/<answer>(.*?)<\/answer>/)?.[1]`

**Do not add "think step by step" to reasoning model prompts.** It increases output length (visible CoT) without engaging the model's internal reasoning differently, and can reduce answer quality by front-loading visible deliberation that the model's hidden reasoning already covered.

**For extended thinking (API-level CoT):** Set `budget_tokens` to match task complexity. Simple single-hop reasoning: 512–1024 tokens. Complex multi-step: 2048–8192. Budget tokens are billed as output tokens — the 32× cost multiplier in the receipt below is real. Use it for tasks that genuinely need it, not by default.

```js
// Claude extended thinking (API-level CoT — for complex multi-step tasks only)
const response = await client.messages.create({
  model: 'claude-opus-4-8',
  thinking: { type: 'enabled', budget_tokens: 2048 },
  messages: [{ role: 'user', content: problem }]
});
// Thinking content is in response.content[0] (type: 'thinking')
// Final answer is in response.content[1] (type: 'text')
```

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Cost model from real token measurements of four response strategies on a standard word problem. Output pricing at $15/M output tokens (mid-market 2026). Extended thinking cost assumes 1,024 budget_tokens consumed + 3-token answer. Accuracy gain from CoT is task-dependent and not independently reproduced here — directional claims only.

```
=== CoT strategy token cost comparison ===
Prompt: "A train leaves at 60 mph. Another leaves 1hr later at 80 mph..."
Prompt tokens: 42

Strategy                    output_tok  cost/1k-calls  vs direct
Direct answer                       23    $0.47         1.0×
Structured scratchpad               93    $1.52         3.2×
Prompted CoT (step-by-step)        121    $1.94         4.1×
Extended thinking (1024 budget)   1026   $15.52        32.9×

=== Scale impact of unnecessary CoT (10k calls/day) ===
Extra monthly cost from adding prompted CoT to simple tasks:
  $441/month (vs direct answer at same accuracy)
```

The 4.1× cost multiplier is only acceptable if the accuracy gain justifies it. For a classification task with clear criteria, the direct answer is as accurate as the CoT answer — it just has 4.1× more tokens. Measure before adding CoT, not after noticing the bill.

## See also

[R-02](../frontier/r02-reasoning-models.md) · [S-24](s24-self-consistency.md) · [S-16](s16-prompting.md) · [S-45](s45-sampling-parameters.md) · [R-08](../frontier/r08-inference-time-compute-scaling.md)

## Go deeper

Keywords: `chain of thought` · `CoT prompting` · `scratchpad` · `step by step` · `extended thinking` · `reasoning trace` · `structured reasoning` · `thinking tokens` · `inference-time compute`
