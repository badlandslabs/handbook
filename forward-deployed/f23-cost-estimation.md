# F-23 · Pre-Build Cost Estimation

Before writing a line of agent code, estimate what it will cost. The estimate takes 15 minutes; the invoice surprise takes weeks to notice and longer to fix. Token costs are predictable if you measure the right things in advance.

## Situation

A team ships a document summarization agent and discovers the monthly bill is $900 — three times what they budgeted. The documents were longer than expected (1,500 tokens, not 500), they chose a multi-turn agent loop when a single call would do, and they hadn't run a sensitivity analysis on document length. All three errors were avoidable with a 15-minute pre-build estimate.

## Forces

- Token cost has two asymmetric components: input and output. Input (context, prompt, documents) is cheap; output (the generated response) is typically 4–5× more expensive per token. A task that generates long responses costs more than one that generates short ones, even with the same input.
- Architecture multiplies cost. A 3-turn agent loop costs ~3.2× more input tokens than a single call (accumulated context each turn) and ~1.5× more output. Choosing the right architecture before building is the primary cost lever — not the runtime tricks in F-08.
- Document length variance dominates. A ±50% swing in average document length causes a ±30–50% swing in cost. Measuring 10 real samples before building is worth more than any optimization after.
- Output token estimates are harder than input estimates. You can measure input components exactly (tokenize the system prompt, sample real input documents). Output length must be estimated from task analysis — what is the model expected to produce? A three-bullet summary is ~50 tokens; a detailed analysis is ~400 tokens. The difference is 8× in output cost.
- Multi-agent architectures are commitment decisions. They set a cost floor that runtime optimizations cannot fully overcome ([F-18](f18-architecture-sets-the-cost-floor.md)). Estimate before you commit to a topology.

## The move

**Estimate in four steps before writing code.**

**Step 1 — Measure each input component separately.**
```js
// Tokenize your planned system prompt
const { encode } = require('gpt-tokenizer'); // or tiktoken
const sysPromptTok = encode(yourSystemPrompt).length;

// Sample 10 real documents from the actual data source
const docSamples = await fetchRealSamples(10);
const avgDocTok = docSamples.map(d => encode(d).length).reduce((a,b) => a+b) / 10;

const inputPerCall = sysPromptTok + avgDocTok;
```

Do not guess token counts. Tokenize the actual content with the same tokenizer the provider uses. Providers differ: GPT-4 uses cl100k; Claude uses a similar BPE tokenizer. Counts vary by ~5–10%; real measurement beats assumed.

**Step 2 — Estimate output length from the task spec.**

Read the task description and estimate what the output should contain. A structured JSON with 3-5 bullets and a label: ~150 tokens. A paragraph summary: ~100 tokens. A detailed code review: ~400 tokens. If unsure, generate 3 sample outputs by hand and tokenize them.

**Step 3 — Apply price and scale.**
```
cost_per_call = (input_tok × input_price) + (output_tok × output_price)
daily_cost    = cost_per_call × calls_per_day
monthly_cost  = daily_cost × 30
```

Use the provider's actual price list. Note that input and output have different prices — do not use a single blended rate for estimation (the blended rate in F-08 is for tracking actuals, not estimation).

**Step 4 — Run a sensitivity analysis.**

Document length is usually the biggest unknown. Before finalizing the estimate:
- Measure P50, P90, P99 of input length from your sample set
- Run the cost formula at each percentile
- Use P90 as your planning number, P99 as your worst-case budget

Architecture multipliers to apply before picking a topology:

| Architecture | Input multiplier | Output multiplier |
|---|---|---|
| Single call | 1.0× | 1.0× |
| 3-turn agent loop | ~3.2× | ~1.5× |
| 2-agent pipeline | ~2.1× | ~2.0× |
| 5-turn loop | ~7× | ~2× |

These are order-of-magnitude guides — your actual multipliers depend on how much context accumulates each turn ([S-38](../stacks/s38-agent-state-design.md)).

**Commit to the cheapest architecture that meets the requirement.** If a single call can do the job, don't build a multi-turn loop. The loop is for tasks that genuinely require it — iterative refinement, tool use with unknown intermediate steps, tasks where output must be checked against a verifier. Not for tasks that can be done in one shot.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Document summarization agent estimated before build. System prompt tokenized directly (48 tokens). Document length varied across a realistic range. Architecture multipliers modeled from F-18 measurements and S-35 loop analysis.

```
=== Document summarization agent: pre-build estimate ===
System prompt:   48 tokens
Avg document:   800 tokens (measured from 10-sample document set)
Input/call:     848 tokens
Output/call:    150 tokens (3-5 bullets + sentiment label, estimated)

Cost/call:   $0.00479  (input $0.00254 + output $0.00225)
At 500 calls/day: $2.40/day → $72/month

=== Sensitivity: document length (500 calls/day) ===
  200-token docs:  $45/month   ← short memos
  500-token docs:  $58/month   ← typical pages
  800-token docs:  $72/month   ← planning number (P50)
1,500-token docs: $103/month   ← P90 estimate
3,000-token docs: $171/month   ← worst-case budget

=== Architecture comparison (same task, same docs) ===
Single call:          $72/month   ← baseline
Agent loop (3 turns): $173/month  (2.4× more) ← only if iteration is required
Multi-agent:          $148/month  (2.1× more) ← only if specialist split is needed
```

The sensitivity analysis is the most useful output: planning on 500-token average documents when the P90 is 1,500 tokens produces a 43% underestimate. Running this before build prevents the "invoice surprise."

## See also

[F-08](f08-agent-cost-control.md) · [F-18](f18-architecture-sets-the-cost-floor.md) · [S-35](../stacks/s35-latency-budget.md) · [S-38](../stacks/s38-agent-state-design.md) · [S-02](../stacks/s02-context-budget.md)

## Go deeper

Keywords: `cost estimation` · `token budget` · `pre-build planning` · `sensitivity analysis` · `architecture cost` · `LLM cost model` · `token counting` · `gpt-tokenizer` · `tiktoken`
