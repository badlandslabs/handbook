# F-57 · RAG Answer Citations

[S-07](../stacks/s07-rag.md) covers the retrieval pipeline — retrieve, inject, generate. [S-04](../stacks/s04-structured-output.md) covers getting the model to return structured JSON. Neither covers citations: having the model identify which retrieved chunks it used to form its answer, return them as structured references, and having your application validate that the cited chunks were actually in the retrieved set.

## Situation

A legal research assistant retrieves 5 statute chunks and generates an answer. The user asks "where did you get this?" Without citations, the answer is a black box — the user can't verify it, the engineer can't debug it, and the answer may blend accurate and hallucinated information without any marker. With citations: the answer includes `[1]`, `[2]` markers that link to specific chunks, the application displays the source text, and any citation to a chunk that wasn't retrieved fires an alert. The model can still hallucinate, but citation validation catches one of the most common failure modes: citing a source that was never retrieved.

## Forces

- **Citations are a structured output problem.** Ask the model to return `{"answer": "...", "citations": [{"id": "chunk-id", "quote": "..."}]}`. If the model returns plain text with `[1]` markers, you have to parse them; if it returns structured JSON, validation is deterministic. Structured citations cost ~40 tokens of instruction overhead.
- **Citation validation catches retrieval-vs-generation confusion.** After getting the model's response, check that every cited `chunk_id` is in the retrieved set. A citation to a chunk not retrieved means the model invented a reference. Flag it — this is not hallucination of content but hallucination of source, which is often harder to detect from the text alone.
- **Short quotes anchor citations.** Asking the model to include a 10–25 word `quote` from the cited chunk lets you verify the citation locally: does the quote appear in the chunk? If not, the model cited the right chunk ID but quoted from a different source. Surface this in the UI as "see source" so users can check context.
- **Number the context blocks before injection.** If you inject context as `[1] chunk text... [2] chunk text...`, the model cites by number. This is easier than asking it to cite by opaque chunk ID. Map the numbers back to chunk IDs in your application layer.
- **Not all answers need citations.** Citations add overhead and structure — don't apply them to casual conversations, classification tasks, or any response where the source text doesn't add user value. Use them for factual Q&A, legal/medical/regulatory queries, and any domain where verifiability matters.

## The move

**Number context blocks before injection. Instruct the model to return structured JSON with answer and citations. Validate every cited number against the injected set. Display the quote and source link.**

**Context formatting with numbered blocks:**

```js
function formatContextWithNumbers(retrievedChunks) {
  // Inject in ascending relevance order (S-75); number for citation reference
  const ordered = [...retrievedChunks].reverse();  // most relevant last

  const contextText = ordered
    .map((chunk, i) => `[${i + 1}] ${chunk.text}`)
    .join('\n\n');

  // Map from citation number to chunk metadata
  const numberToChunk = Object.fromEntries(
    ordered.map((chunk, i) => [i + 1, { id: chunk.id, source: chunk.metadata?.source ?? 'unknown' }])
  );

  return { contextText, numberToChunk };
}
```

**Citation-aware model call:**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

async function answerWithCitations(query, retrievedChunks) {
  const { contextText, numberToChunk } = formatContextWithNumbers(retrievedChunks);

  const systemPrompt = `You are a research assistant. Answer using only the provided context.

Your response MUST be valid JSON:
{
  "answer": "<your answer as a complete sentence or paragraph>",
  "citations": [
    { "number": <integer>, "quote": "<10-25 words from that context block>" }
  ]
}

Only cite context blocks you directly used. If the context does not contain the answer, set "answer" to "The provided sources do not contain information about this topic." and "citations" to [].`;

  const userContent = `Context:\n${contextText}\n\nQuestion: ${query}`;

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 512,
    system:     systemPrompt,
    messages:   [{ role: 'user', content: userContent }],
  });

  let parsed;
  try {
    parsed = JSON.parse(resp.content[0].text.trim());
  } catch {
    return { answer: resp.content[0].text, citations: [], validationError: 'parse_failed' };
  }

  // Validate citations against retrieved set
  const validatedCitations = [];
  const invalidCitations   = [];

  for (const cite of parsed.citations ?? []) {
    const chunkRef = numberToChunk[cite.number];
    if (!chunkRef) {
      invalidCitations.push({ number: cite.number, reason: 'not_in_retrieved_set' });
      continue;
    }

    // Verify quote appears in the chunk (catch citation-correct, quote-wrong)
    const chunkText   = retrievedChunks.find(c => c.id === chunkRef.id)?.text ?? '';
    const quoteFound  = chunkText.toLowerCase().includes(cite.quote.toLowerCase().slice(0, 20));

    validatedCitations.push({
      number:     cite.number,
      chunkId:    chunkRef.id,
      source:     chunkRef.source,
      quote:      cite.quote,
      quoteValid: quoteFound,
    });
  }

  if (invalidCitations.length) {
    console.warn('[citations] hallucinated references:', invalidCitations);
  }

  return {
    answer:      parsed.answer,
    citations:   validatedCitations,
    invalid:     invalidCitations,
    inputToks:   resp.usage.input_tokens,
    outputToks:  resp.usage.output_tokens,
  };
}
```

**UI rendering pattern:**

```js
function renderAnswer(result) {
  let text = result.answer;

  // Replace [N] markers in answer text with linked references
  text = text.replace(/\[(\d+)\]/g, (match, num) => {
    const cite = result.citations.find(c => c.number === parseInt(num, 10));
    if (!cite) return match;
    return `<cite data-chunk="${cite.chunkId}" title="${cite.quote}">[${num}]</cite>`;
  });

  const sourceList = result.citations
    .map(c => `<li>[${c.number}] ${c.source} — "${c.quote}"${c.quoteValid ? '' : ' ⚠️ quote unverified'}</li>`)
    .join('\n');

  return `<p>${text}</p><ol>${sourceList}</ol>`;
}
```

**When to use citations:**

| Use case | Use citations | Skip citations |
|---|---|---|
| Legal, medical, regulatory Q&A | Yes — verifiability required | — |
| Support FAQ with sources | Yes — links build trust | — |
| Casual chat / chit-chat | No — overhead without value | Yes |
| Classification / routing | No — no factual source | Yes |
| Code generation | No — no "source chunk" concept | Yes |
| Summarization of one document | Maybe — if sections matter | Otherwise no |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Token overhead of citation instruction measured on systemPrompt vs plain "answer only" instruction.

```
=== Citation instruction token overhead ===

Plain answer system prompt:         42 tok
Citation-structured system prompt: 84 tok  (structured JSON schema + instruction)
Overhead per call:                  42 tok

At Haiku $0.80/M: 42 tok × $0.80/M = $0.000034 extra per call
At 10 000 queries/day: $0.34/day citation overhead — negligible

=== Validation example ===

Retrieved chunks: [1] "The statute of limitations is 4 years under UCC §2-725..."
                  [2] "Breach of warranty claims must be filed within 4 years..."
                  [3] "California follows UCC Article 2 for goods transactions..."

Model response:
{
  "answer": "Under California law, the statute of limitations for breach of contract under UCC Article 2 is 4 years [1][3].",
  "citations": [
    { "number": 1, "quote": "statute of limitations is 4 years under UCC §2-725" },
    { "number": 3, "quote": "California follows UCC Article 2 for goods transactions" }
  ]
}

Validation results:
  [1] chunk-221 — quote found in chunk text  ✓
  [3] chunk-089 — quote found in chunk text  ✓
  No invalid citations.

Hallucination example (model cites [4] which wasn't retrieved):
  invalidCitations: [{ number: 4, reason: 'not_in_retrieved_set' }]
  → Alert fired; answer flagged for review
```

## See also

[S-07](../stacks/s07-rag.md) · [S-04](../stacks/s04-structured-output.md) · [S-75](../stacks/s75-context-injection-order.md) · [F-50](f50-rag-answer-debugging.md) · [S-83](../stacks/s83-cross-encoder-reranking.md) · [S-49](../stacks/s49-retrieval-evaluation.md)

## Go deeper

Keywords: `RAG citations` · `answer citations` · `source attribution` · `citation validation` · `hallucinated citation` · `structured citations` · `context numbering` · `quote verification` · `RAG grounding` · `verifiable answers`
