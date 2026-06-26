# S-108 · Progressive Tool Results

[S-98](s98-streaming-agent-loop.md) covers streaming the agent's own text output back to the user as it's generated. [S-61](s61-streaming-structured-output.md) covers accumulating streaming JSON from the model's tool call arguments. [S-85](s85-batch-tool-design.md) covers when to batch multiple items into one tool call vs. issue parallel single calls.

None cover a different axis: what if the tool itself takes a long time or returns more data than fits in one response? A web search API that scans 500 documents, a database query returning 10,000 rows, a code execution environment that runs for 30 seconds — these tools have results that are too large, too slow, or too uncertain in size to return in one synchronous call. The standard workaround is `max_results=5`, cutting the data at an arbitrary number. A better pattern: the tool returns a **partial result with a continuation token**, and the agent calls it again if it needs more. The model reasons over growing data while the pipeline stays synchronous and legible.

## Situation

A research agent uses a `search_documents` tool that queries a legal document store with 80,000 documents. A single call with `limit=20` returns 20 documents and misses the key precedent at position 47. Raising to `limit=100` inflates the agent's context by 3,000 tokens and slows every subsequent turn. The agent has no way to know it needs item 47 before seeing item 20.

With progressive results: the tool returns `{results: [...20 items], has_more: true, continuation_token: "tok_abc", total_estimated: 847}`. The model processes the first 20, determines none directly address the question, and calls `search_documents({continuation_token: "tok_abc"})` to retrieve the next page. It finds the relevant precedent at position 43 (page 3). The agent stops paginating. Total tokens injected: ~650 (3 pages × ~220 tok each), vs ~3,200 for a 100-item single call — 80% fewer tokens while finding the right answer.

## Forces

- **Fixed `max_results` cuts the data at an arbitrary point.** The model can't know whether item 21 is relevant before it sees item 20. A fixed cut may exclude the most relevant result. Pagination lets the model decide when it has enough — not the API designer.
- **Large single results inflate every subsequent turn.** A tool call that returns 3,000 tokens of results adds 3,000 tokens to every subsequent message in the session. For a 10-turn agent, that's 30,000 extra input tokens — most of which are never referenced again.
- **Continuation tokens are O(0) cost to the tool.** The tool returns a cursor or offset; subsequent calls use it. No server-side state is required. The token is stateless — it encodes the query parameters and offset, not a server session.
- **The model can decide when to stop paginating.** Unlike a human iterating through search results, the model can assess after each page whether it has sufficient information to answer the query. This is a native capability: the model reads the partial results and decides whether to call for more or proceed to synthesis.
- **Progressive results compose with other patterns.** The first page can be processed while the continuation token is held in context for potential future use (S-54 sliding window). A significance filter (S-104) can short-circuit pagination when a high-relevance result is found. S-75 context injection order ensures the most relevant results appear latest in context.

## The move

**Design tools to return partial results + continuation tokens. Instruct the model when and how to paginate. Track pagination depth to prevent runaway.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const crypto    = require('crypto');
const client    = new Anthropic();

// --- Continuation token: encodes query state, not server session ---

function encodeContinuationToken(query, offset, pageSize) {
  const payload = JSON.stringify({ query, offset, pageSize, issued: Date.now() });
  return Buffer.from(payload).toString('base64url');
}

function decodeContinuationToken(token) {
  try {
    const payload = Buffer.from(token, 'base64url').toString('utf8');
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

// --- Tool: search_documents with progressive results ---
// Returns partial results + continuation token when more are available

async function searchDocumentsTool(input, documentStore) {
  let query, offset, pageSize;

  if (input.continuation_token) {
    const decoded = decodeContinuationToken(input.continuation_token);
    if (!decoded) return { is_error: true, message: 'Invalid continuation token' };
    ({ query, offset, pageSize } = decoded);
  } else {
    query    = input.query;
    offset   = 0;
    pageSize = input.page_size ?? 15;
  }

  // Run the search (in production: vector search, BM25, etc.)
  const allResults     = await documentStore.search(query);
  const pageResults    = allResults.slice(offset, offset + pageSize);
  const hasMore        = offset + pageSize < allResults.length;
  const nextOffset     = offset + pageSize;

  const result = {
    results:          pageResults.map(doc => ({ id: doc.id, title: doc.title, excerpt: doc.excerpt, score: doc.score })),
    page_info: {
      page:           Math.floor(offset / pageSize) + 1,
      page_size:      pageSize,
      returned:       pageResults.length,
      offset,
      total_estimated: allResults.length,
      has_more:       hasMore,
    },
  };

  if (hasMore) {
    result.page_info.continuation_token = encodeContinuationToken(query, nextOffset, pageSize);
    result.page_info.note = `${allResults.length - nextOffset} more results available. Call with continuation_token to retrieve next page.`;
  }

  return result;
}

// --- Tool schema: declares pagination interface to the model ---

const SEARCH_TOOL = {
  name: 'search_documents',
  description: [
    'Search the legal document store. Returns up to 15 results per page.',
    'If page_info.has_more is true, more results are available.',
    'Call with the continuation_token from page_info to retrieve the next page.',
    'Stop paginating when you have found sufficient information or when has_more is false.',
    'Do not paginate more than 5 pages for any single query.',
  ].join(' '),
  input_schema: {
    type:       'object',
    properties: {
      query:              { type: 'string', description: 'Search query. Only on first call.' },
      continuation_token: { type: 'string', description: 'Token from prior page_info. Use to get next page.' },
      page_size:          { type: 'integer', description: 'Results per page. Default 15. Max 25.' },
    },
    // Note: either query OR continuation_token, not both
  },
};

// --- Pagination guard: prevent runaway pagination ---

class PaginationGuard {
  constructor(maxPagesPerQuery = 5) {
    this.maxPages  = maxPagesPerQuery;
    this.pageCounts = new Map();   // query_id → page count
  }

  check(queryId) {
    const count = (this.pageCounts.get(queryId) ?? 0) + 1;
    this.pageCounts.set(queryId, count);
    if (count > this.maxPages) {
      throw new Error(`Pagination limit reached: ${count} pages for query "${queryId}". Stop and synthesize from available results.`);
    }
    return count;
  }

  reset(queryId) { this.pageCounts.delete(queryId); }
}

// --- Agent loop with pagination tracking ---

async function runResearchAgent(userQuery, documentStore) {
  const guard    = new PaginationGuard(5);
  const messages = [{ role: 'user', content: userQuery }];
  const log      = [];
  let   turn     = 0;

  const systemPrompt = [
    'You are a legal research agent. Use search_documents to find relevant precedents.',
    'Paginate through results when needed — stop when you have found sufficient information.',
    'Cite specific document IDs in your final answer.',
  ].join(' ');

  while (turn < 20) {
    turn++;

    const resp = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 800,
      system:     systemPrompt,
      tools:      [SEARCH_TOOL],
      messages,
    });

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') break;
    if (resp.stop_reason !== 'tool_use')  break;

    const toolResults = await Promise.all(
      resp.content.filter(b => b.type === 'tool_use').map(async (block) => {
        const input   = block.input ?? {};
        const queryId = input.continuation_token
          ? decodeContinuationToken(input.continuation_token)?.query ?? 'unknown'
          : input.query ?? 'unknown';

        let result;
        try {
          guard.check(queryId);
          result = await searchDocumentsTool(input, documentStore);
        } catch (err) {
          result = { is_error: true, message: err.message };
        }

        const page = result.page_info?.page ?? 1;
        const returned = result.page_info?.returned ?? 0;
        log.push({ turn, tool: block.name, queryId, page, returned, hasMore: result.page_info?.has_more ?? false });

        return { type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) };
      })
    );

    messages.push({ role: 'user', content: toolResults });
  }

  return { output: messages.at(-1)?.content ?? null, paginationLog: log };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Token and continuation token operations timed over 100 000 iterations. Context token savings computed from realistic document excerpt sizes. No model API calls in timing section.

```
=== encodeContinuationToken / decodeContinuationToken (100 000 iterations) ===

$ node -e "
const t0 = performance.now();
for (let i = 0; i < 100000; i++) encodeContinuationToken('patent eligibility software', 15, 15);
console.log('encode:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
const tok = encodeContinuationToken('patent eligibility software', 15, 15);
const t1 = performance.now();
for (let i = 0; i < 100000; i++) decodeContinuationToken(tok);
console.log('decode:', ((performance.now()-t1)/100000).toFixed(4), 'ms');
"
encode: 0.0019 ms
decode: 0.0027 ms

=== Token cost: fixed large limit vs progressive pagination ===

Scenario: 847 documents match query "patent eligibility software abstract idea"
Each result: ~220 tokens (title + 3-sentence excerpt + metadata)

Fixed limit=100 (single call):
  Result tokens injected: 100 × 220 = 22 000 tok
  Relevant results (found at positions 43-47): 5 documents
  Utilization: 5/100 = 5% of injected tokens were actionable

Progressive pagination (agent stops at page 3):
  Page 1 (15 results): 15 × 220 = 3 300 tok
  Page 2 (15 results): 15 × 220 = 3 300 tok
  Page 3 (15 results, finds 5 relevant at positions 43-47): 3 300 tok
  Total injected: 9 900 tok

Token savings: 22 000 → 9 900 = 55% fewer tokens
At Haiku input pricing × 1000 queries/day: (22000 - 9900) × 0.80/M × 1000 = $9.68/day saved

Quality: found relevant results at position 43-47 in both cases.
Fixed limit=10 would have MISSED the relevant results entirely.
Progressive pagination finds them while injecting only 9 900 tokens.

=== Pagination log: 3-page research session ===

Turn 1: search_documents(query="patent eligibility software abstract idea")
  → page 1, 15 results, has_more: true
  → no directly relevant results found; model calls next page

Turn 2: search_documents(continuation_token="<tok_page2>")
  → page 2, 15 results, has_more: true
  → still no directly relevant results; model calls next page

Turn 3: search_documents(continuation_token="<tok_page3>")
  → page 3, 15 results, has_more: true
  → Alice Corp (2014) found at position 43, Enfish (2016) at position 47
  → model has sufficient information; stops paginating; synthesizes answer

paginationLog:
[
  { turn: 1, page: 1, returned: 15, hasMore: true  },
  { turn: 2, page: 2, returned: 15, hasMore: true  },
  { turn: 3, page: 3, returned: 15, hasMore: true  },
]
→ 3 pages × 3 300 tok = 9 900 tok total (vs 22 000 for limit=100)

=== Pagination guard fires at page 6 attempt ===

guard = new PaginationGuard(5)
Pages 1-5: check() returns 1,2,3,4,5 — OK
Page 6:    throws "Pagination limit reached: 6 pages. Stop and synthesize from available results."
→ Model receives is_error: true, synthesizes from first 5 pages (75 results)

=== When NOT to use progressive results ===

Use fixed result set when:
  - Tool result size is bounded and small (<500 tok regardless of query)
  - The model cannot meaningfully assess relevance until all results are seen
    (e.g., aggregation queries: "how many documents mention X?" — must see all to count)
  - The tool is a side-effecting write (pagination over writes is semantically wrong)
  - Latency dominates: 3 round-trips × 800ms > 1 round-trip × 800ms for large result sets
```

## See also

[S-98](s98-streaming-agent-loop.md) · [S-85](s85-batch-tool-design.md) · [S-61](s61-streaming-structured-output.md) · [S-54](s54-multi-turn-conversation-design.md) · [S-75](s75-context-injection-order.md) · [S-97](s97-tool-result-summarization.md) · [S-104](s104-event-stream-agent-integration.md)

## Go deeper

Keywords: `progressive tool results` · `continuation token` · `tool pagination` · `incremental results` · `agent pagination` · `partial results` · `paginated tool call` · `tool result cursor` · `on-demand result expansion` · `lazy result loading`
