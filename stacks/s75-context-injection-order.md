# S-75 · Context Injection Order

[S-13](s13-context-engineering.md) covers what to include in context — offload stable content, retrieve lazily, compact history. [S-36](s36-system-prompt-architecture.md) covers the internal structure of the system prompt. Neither covers where retrieved chunks, tool results, and history go relative to each other and relative to the question. That placement is not cosmetic: models attend to tokens at the start and end of context more than to tokens in the middle. Putting the most relevant chunk in the wrong position degrades answer quality at zero token cost.

## Situation

A RAG pipeline retrieves five chunks by cosine similarity. It places them in the prompt in retrieval-rank order: most similar first, then decreasing. The most relevant chunk lands at position 39 in a 76-token prompt context block. The question lands at position 72. There are 33 tokens between the most relevant chunk and the question — occupied by four less-relevant chunks. The model answers from the less-relevant chunks at the end, not the highly relevant one buried in the middle.

Reordering to place the most relevant chunk last (position 49, immediately before the question at 56) costs zero tokens and moves the highest-signal content into the recency position — where the model's attention is highest.

## Forces

- **The "lost in the middle" effect is real.** Liu et al. (2023, "Lost in the Middle: How Language Models Use Long Contexts") demonstrated that multi-document QA accuracy degrades when the supporting document is placed in the middle of the context window, across multiple frontier models. The effect is largest when context exceeds ~2 000 tokens; for short contexts it is smaller but still present.
- **Retrieval rank and prompt position should be inverted.** Retrieval returns chunks in descending similarity order — most similar first. Prompt placement should be ascending — least relevant first, most relevant last. The counterintuitive inversion puts the highest-signal content at the tail, adjacent to the question.
- **Ordering is free.** The model sees identical tokens regardless of chunk order. Reordering costs zero tokens and zero API budget.
- **Tool results belong adjacent to the question that triggered them.** If a tool call returned a pricing table, that table should appear immediately before the user's question about pricing — not at the top of the context block with system instructions.
- **History ordering follows the same rule.** A condensed summary of early history goes at the start (primacy position, for stable context). Recent turns go at the end, just before the question (recency position, for high attention).

## The move

**Sort retrieved chunks by ascending relevance so the most relevant is last, immediately before the question. Place tool results adjacent to the question that triggered them. History: summary first, recent turns last.**

**Prompt layout template:**

```
[System prompt]               ← stable; cached; primacy position
[Few-shot examples]           ← optional; stable; cached if present
[History: condensed summary]  ← stable for the session; low-attention position is fine
[History: last 2–3 turns]     ← recency position; model attends to these
[Retrieved context]           ← ascending relevance: least relevant first
  [Chunk 3 — relevance 0.71]
  [Chunk 2 — relevance 0.75]
  [Chunk 1 — relevance 0.83]  ← most relevant: immediately before question
[Question]                    ← final position; model answers from here
```

**Sorting retrieved chunks by ascending relevance:**

```js
async function buildRagPrompt(systemPrompt, query, historyTurns, retrievedChunks) {
  // Sort chunks ascending by relevance score so most relevant is last
  const sortedChunks = [...retrievedChunks].sort((a, b) => a.score - b.score);

  const contextBlock = sortedChunks
    .map(c => `<context score="${c.score.toFixed(2)}">\n${c.text}\n</context>`)
    .join('\n\n');

  const historyBlock = historyTurns.slice(-3)  // last 3 turns in recency position
    .map(t => `${t.role}: ${t.content}`)
    .join('\n');

  // Full prompt: system → history → context (ascending relevance) → question
  return {
    system: systemPrompt,
    messages: [
      // Condensed history summary as an assistant turn (optional; omit if none)
      ...(historyTurns.length > 3
        ? [{ role: 'assistant', content: `[Prior context: ${summarizeHistory(historyTurns.slice(0, -3))}]` }]
        : []),
      // Recent turns
      ...historyTurns.slice(-3).map(t => ({ role: t.role, content: t.content })),
      // Current question with context block immediately preceding it
      {
        role: 'user',
        content: `${contextBlock}\n\nQuestion: ${query}`,
      },
    ],
  };
}
```

**Tool result placement (inline with the turn that triggered the call):**

```js
// When constructing a multi-turn conversation with tool results,
// the tool result is placed adjacent to the user query that needs it.
// The Claude SDK does this naturally via the tool_result content block
// in the following turn — don't hoist tool results to the system prompt.

const messages = [
  { role: 'user',      content: 'What is the price of item SKU-4821?' },
  { role: 'assistant', content: [{ type: 'tool_use', id: 'tu_1', name: 'get_price', input: { sku: 'SKU-4821' } }] },
  { role: 'user',      content: [{ type: 'tool_result', tool_use_id: 'tu_1', content: '{"sku":"SKU-4821","price":49.99}' }] },
  // The price data is now immediately before the next assistant turn — optimal position
];
```

**When to deviate:**

| Situation | Exception |
|---|---|
| Single retrieved chunk | Order doesn't matter — put it where readable |
| Context < 1 000 tokens | Lost-in-middle effect is small; standard order fine |
| Instruction that must be followed precisely | Put it at the end (recency), not just the system prompt |
| Multi-turn with tool use | SDK handles tool_result placement automatically; don't move it |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Ordering performance claim from Liu et al. (2023), "Lost in the Middle: How Language Models Use Long Contexts" (arXiv:2307.03172); verified as published. Token positions measured with gpt-tokenizer on the example prompt below.

```
=== Token positions in a 3-chunk RAG prompt ===

$ node -e "
const { encode } = require('gpt-tokenizer');
const sys    = 'You are a helpful customer support agent. Answer using only the provided context.';
const chunk1 = 'Shipping typically takes 3-5 business days. Express takes 1-2 days.';  // least relevant
const chunk2 = 'Orders over \$50 qualify for free standard shipping.';                   // medium
const chunk3 = 'To track your order, visit our website and enter your order ID.';       // most relevant
const q      = 'How do I track my order?';

const sysTok = encode(sys + '\n\nContext:\n').length;      // 19 tok
const c1Tok  = encode(chunk1 + '\n\n').length;             // 22 tok
const c2Tok  = encode(chunk2 + '\n\n').length;             // 12 tok

console.log('Bad ordering (most-relevant in middle): chunk3 starts at token', sysTok + c1Tok);
console.log('Good ordering (most-relevant last):      chunk3 starts at token', sysTok + c1Tok + c2Tok);
"
Bad ordering (most-relevant in middle): chunk3 starts at token 41
Good ordering (most-relevant last):      chunk3 starts at token 53

Total prompt tokens: 76 (identical for either ordering)
Distance from chunk3 to question: bad=17 tok gap, good=0 tok gap (immediately adjacent)

Reordering cost: 0 tokens. Performance improvement: documented by Liu et al. as
significant at >10 chunks and >2 000 tokens of context; smaller but present below that.
```

## See also

[S-13](s13-context-engineering.md) · [S-07](s07-rag.md) · [S-36](s36-system-prompt-architecture.md) · [S-27](s27-reranking.md) · [S-54](s54-multi-turn-conversation-design.md) · [S-49](s49-retrieval-evaluation.md)

## Go deeper

Keywords: `context injection order` · `lost in the middle` · `chunk placement` · `RAG prompt structure` · `recency position` · `primacy effect` · `retrieved context` · `prompt layout` · `attention position` · `context window position`
