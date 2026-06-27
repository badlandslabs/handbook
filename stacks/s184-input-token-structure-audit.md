# S-184 · Input Token Structure Audit

Every API call's input tokens divide into two buckets: **structural overhead** (system prompt, tool schemas, message framing — fixed regardless of what the user sends) and **content** (document, user query — varies per call). Most optimization effort goes toward content — compressing documents, trimming queries — because content is visible. The structural bucket is invisible until measured, and in agentic and extraction pipelines it is often the larger of the two.

A contract extraction call with verbose tool schemas: 598 structural tokens (78.1%) vs 168 content tokens. The visible content is only 22% of what the API bills. Halving the document length saves 11% of total input cost. Compressing the tool schemas (S-183) saves 19%. Optimizing in the wrong bucket costs effort and buys little.

The input token structure audit decomposes each call into its buckets, reports the structural percentage, and names the optimization target: `ATTACK_STRUCTURAL` (apply S-183, S-36, S-59, S-168) or `ATTACK_CONTENT` (apply S-31, S-122, S-56). It takes the call specification as input — system prompt text, tool schema list, document, user query — and returns the analysis in under 0.02 ms with no API call.

## Situation

A legal AI pipeline runs extraction calls with three tool schemas. The team has been trying to reduce costs by limiting document length. After auditing:

- Extraction with verbose tool schemas: 598 structural / 168 content / 766 total. Structural is 78.1%. Every dollar spent compressing documents returns only 22 cents in savings.
- After applying S-183 tool compression: 449 structural / 168 content / 617 total. Still 72.8% structural. Compression saves $1.19/day at 10k calls — real money — but structural overhead still dominates.
- Same pipeline on 4 000-token documents: 25 structural / 4 006 content / 4 031 total. Structural is 0.6%. Document compression now makes sense.

The audit makes the right target explicit before engineering effort is spent.

## Forces

- **Structural overhead is multiplied by volume, not content.** A 598-token structural baseline × 10 000 calls/day × $0.80/M = $4.78/day paid regardless of what the user asks. This cost exists even on calls where the model returns "I don't know." Content cost scales with input length; structural cost scales with call volume.
- **Run the audit on representative calls, not worst cases.** A 10 000-token document inflates the content bucket and makes the call look content-dominated. The structural percentage normalizes against typical traffic. Audit on p50 document length, not maximum.
- **Structural threshold of 40% is a heuristic, not a law.** In pipelines where documents average 200 tokens (short email classifications, chat turn processing), structural overhead of 40% is expected. In pipelines where documents average 2 000 tokens (contract analysis, long-form extraction), structural overhead above 15% warrants investigation.
- **Tool schemas are the largest structural component in tool-using agents.** System prompts are usually 100-300 tokens for well-written prompts. Tool schemas for 8 verbose tools: 1 720 tokens (S-183 receipt). The structural bucket is dominated by tool schemas in most agentic systems. The audit makes this visible before it is assumed.
- **Compose audit with targeted compression entries.** The audit is a diagnostic, not a fix. `ATTACK_STRUCTURAL` → run S-183 (tool schema compression), S-36 (system prompt architecture), S-59 (instruction density), S-168 (waste audit to remove zero-invocation tools). `ATTACK_CONTENT` → run S-31 (prompt compression), S-122 (retrieved chunk dedup), S-31, S-56 (pre-flight total check to catch overflow).
- **The 4-token message framing is real but minor.** Every API call includes ~4 tokens per message for role markers and structure. At 10 000 calls/day, that's 40 000 tokens/day — $0.03/day at Haiku. Log it for completeness but do not optimize it.

## The move

**Decompose the call into structural and content buckets. Report the structural percentage. Name the target.**

```js
// --- Input token structure audit ---
// Decomposes input tokens into fixed structural overhead vs per-call content.
// Run BEFORE deciding where to focus cost optimization effort.
// ATTACK_STRUCTURAL (> 40%): compress system prompt (S-36, S-59), tool schemas (S-183, S-168)
// ATTACK_CONTENT   (< 40%): compress document (S-31, S-122), reduce query verbosity

function estimateTokens(text) { return Math.ceil((text || '').length / 4); }

const MESSAGE_FRAMING_TOKENS = 4;  // per message: role label + structural overhead

function auditInputTokens(callSpec) {
  const structural = {
    systemPrompt:   estimateTokens(callSpec.systemPrompt),
    toolSchemas:    estimateTokens(JSON.stringify(callSpec.tools || [])),
    messageFraming: MESSAGE_FRAMING_TOKENS * (callSpec.messageCount || 1),
  };
  const content = {
    document:  estimateTokens(callSpec.document),
    userQuery: estimateTokens(callSpec.userQuery),
  };

  const structuralTok = Object.values(structural).reduce((a, b) => a + b, 0);
  const contentTok    = Object.values(content).reduce((a, b) => a + b, 0);
  const totalInput    = structuralTok + contentTok;
  const structuralPct = totalInput > 0 ? structuralTok / totalInput : 0;

  return {
    structural, content,
    structuralTok, contentTok, totalInput,
    structuralPct: (structuralPct * 100).toFixed(1) + '%',
    optimization: structuralPct > 0.40
      ? { target: 'ATTACK_STRUCTURAL',
          reason: 'Compress system prompt (S-36, S-59) and tool schemas (S-183, S-168).' }
      : { target: 'ATTACK_CONTENT',
          reason: 'Compress document (S-31, S-122) or reduce retrieval chunk count (S-179).' },
  };
}

// Usage
const audit = auditInputTokens({
  systemPrompt:  mySystemPrompt,
  tools:         myToolList,
  document:      documentText,
  userQuery:     userMessage,
  messageCount:  1,
});
console.log(audit.structuralPct, '→', audit.optimization.target);
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios: extraction call with verbose tool schemas, same call after S-183 compression, long document analysis, simple Q&A. Token estimates via `Math.ceil(text.length / 4)`. Zero API calls.

```
=== Input Token Structure Audit ===

--- Extraction call (verbose tool schemas) ---
  Structural:
    systemPrompt    :  145 tok
    toolSchemas     :  449 tok  ← dominant
    messageFraming  :    4 tok
  Content:
    document        :  156 tok
    userQuery       :   12 tok
  Structural total: 598 tok  (78.1% of total)
  Content total:    168 tok
  Total input:      766 tok
  → ATTACK_STRUCTURAL: Compress system prompt, tool schemas (S-183, S-168).
  Haiku cost per call: $0.00061

--- Same call after S-183 tool schema compression ---
  Tool schemas: 449 tok → 300 tok  (saved 149 tok)
  Total:        766 tok → 617 tok
  Structural:   78.1%  → 72.8%
  Savings at 10 000 calls/day: $1.19/day

--- Long document analysis (4 000-tok document, no tools) ---
  Structural:  25 tok  (0.6% of total)
  Content:  4 006 tok
  Total:    4 031 tok
  → ATTACK_CONTENT: Compress document (S-31, S-122), reduce retrieval chunks (S-179, S-122).

--- Simple Q&A (no document, no tools) ---
  Structural:  12 tok  (50.0% of total)
  Content:     12 tok
  Total:       24 tok
  → ATTACK_STRUCTURAL: minimal cost — nothing material to cut here

=== Structure Audit Summary ===
  Extraction (verbose tools)     struct= 598 tok (78.1%)  content= 168 tok  → ATTACK_STRUCTURAL
  Extraction (compressed tools)  struct= 449 tok (72.8%)  content= 168 tok  → ATTACK_STRUCTURAL
  Long doc analysis (no tools)   struct=  25 tok ( 0.6%)  content=4006 tok  → ATTACK_CONTENT
  Simple Q&A                     struct=  12 tok (50.0%)  content=  12 tok  → ATTACK_STRUCTURAL

auditInputTokens() with 3 tools: 0.0138 ms
```

## See also

[S-183](s183-tool-description-compression.md) · [S-168](s168-tool-definition-waste-audit.md) · [S-36](s36-system-prompt-architecture.md) · [S-59](s59-instruction-density.md) · [S-31](s31-prompt-compression.md)

## Go deeper

Keywords: `input token structure audit` · `token cost decomposition` · `structural overhead tokens` · `LLM call token breakdown` · `API call token analysis` · `tool schema token overhead` · `where to optimize token cost` · `input token budget` · `system prompt vs content tokens` · `agent call token cost`
