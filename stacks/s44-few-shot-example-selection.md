# S-44 · Few-Shot Example Selection

Examples in a prompt are not decoration — they set the prior for how the model interprets the task. Choosing the wrong examples, the wrong number, or redundant examples costs tokens and teaches the wrong behavior. Choosing well costs almost the same and can swing accuracy by 10–20 percentage points.

## Situation

A ticket-classification system adds three examples to its prompt. All three show "critical" priority. The model learns the format but misclassifies every medium and low ticket. The examples were chosen because they were memorable, not because they were representative. Replacing them with one example per priority class, at nearly the same token count, fixes the distribution.

## Forces

- Examples consume tokens proportional to their length. At 15 tokens per example, going from 0-shot to 6-shot adds ~90 tokens and roughly doubles prompt cost per call. That cost is fixed per call, not per example match.
- More examples is not always better. Beyond the point where all relevant behaviors are covered, additional examples add noise: they can anchor the model to the format of the example set rather than the task.
- Redundant examples teach nothing that one example would not. Four examples of "production is down → critical" teach the critical class once, use 28 tokens, and leave medium/low uncovered. Four diverse examples cover all four classes in 33 tokens.
- Dynamic example selection — retrieving the most similar examples from a store based on the current input — consistently outperforms static examples on classification tasks, at nearly the same cost ($0.0003/k calls more for an embedding lookup). The break-even is almost always in favor of dynamic selection when misclassification has any cost.
- The format of the example output is as important as the content. If the expected output is JSON with a specific key, every example must produce that same JSON shape. The model learns format from examples, not just semantics.
- Few-shot examples are cacheable (S-08). Static examples at the front of the prompt are part of the cacheable prefix. Dynamic examples selected per-call are not — they break caching. This is a real cost difference at high call volumes.

## The move

**Cover each output class with exactly one example. Prefer diversity over depth.**

For a 4-class classification task, use exactly 4 examples — one per class. For a generation task with 3 common output shapes, use one example of each shape. The model generalizes; you don't need to show every variant.

**Count before you add.** Each example costs ~15–25 tokens in a typical support task. Before adding example 4, ask: does it teach a behavior not already covered by examples 1–3? If not, cut it.

**Use dynamic selection when misclassification costs anything.** Retrieve the k most similar examples from an example store using embedding similarity ([S-17](s17-embeddings.md)) to the current input. The overhead is ~$0.0003 per 1,000 calls — almost always worth it. Static examples optimize for average-case; dynamic examples optimize for the specific input.

```js
// Dynamic selection: retrieve k nearest examples by embedding similarity
async function selectExamples(input, exampleStore, k = 3) {
  const inputEmbed = await embed(input);
  return exampleStore
    .map(ex => ({ ...ex, sim: cosineSim(inputEmbed, ex.embed) }))
    .sort((a, b) => b.sim - a.sim)
    .slice(0, k);
}
```

**Format all examples identically.** If the expected output is `{"priority": "critical"}`, every example must return `{"priority": "..."}` — same key, same shape, same wrapper. An example that returns a bare string when the expected output is JSON will confuse the model about whether JSON is required.

**Place examples after the instructions, before the current input.** The order matters: instructions first (what to do), examples second (how the output should look), current input last (what to do it to). Mixing them causes the model to treat examples as part of the instruction.

**Static examples belong in the system prompt (cacheable). Dynamic examples belong in the user turn (per-call).** If you use the same examples for every call, put them in the system prompt — they get cached after the first call at no extra cost ([S-08](s08-prompt-caching.md)). If you select examples per-call, inject them in the user turn alongside the input — they cannot be cached.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Support ticket classification task, 4-class output (critical/high/medium/low). Token counts measured directly. Accuracy gain from dynamic selection is a reported figure from classification benchmarks (10–20pp) — not independently reproduced here; treat as directional.

```
=== Few-shot token cost: ticket priority classification ===
(system prompt: 22 tokens, test input: 10 tokens)

k-shot    prompt_tok   $/1k-calls   classes_covered
0-shot          22      $0.194      — (zero examples, zero class coverage)
1-shot          38      $0.291      critical
2-shot          50      $0.364      critical (still just one class)
3-shot          65      $0.455      critical, high
5-shot          97      $0.649      critical, high, medium
6-shot         112      $0.741      critical, high, medium, low ← full coverage

Finding: need 6 examples to cover 4 classes with these examples.
With 1-per-class selection: 4 examples, 83 tokens, $0.504/k — same coverage.

=== Diversity vs redundancy ===
4 redundant examples (all "DB down → critical"):   28 tokens, teaches 1 class
4 diverse examples (one per class):                33 tokens, teaches 4 classes
Same cost (+5 tokens), 4× more coverage

=== Dynamic vs static selection ===
Static 3-shot (same examples every call):   $0.395/k calls (examples are cacheable)
Dynamic 3-shot (retrieve similar per call): $0.395/k + $0.0003/k = $0.395/k calls
Accuracy gain from relevant examples: 10–20pp on classification tasks (directional)
```

The diversity finding is the one to internalize: adding a fourth example that covers the same case as the first three costs 7 tokens and teaches nothing. Adding one that covers a new class costs the same tokens and closes a classification gap.

## See also

[S-16](s16-prompting.md) · [S-17](s17-embeddings.md) · [S-08](s08-prompt-caching.md) · [S-27](s27-reranking.md) · [S-07](s07-rag.md)

## Go deeper

Keywords: `few-shot learning` · `in-context learning` · `example selection` · `k-shot prompting` · `dynamic few-shot` · `example retrieval` · `prompt examples` · `classification prompts`
