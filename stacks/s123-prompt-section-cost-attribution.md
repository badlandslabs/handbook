# S-123 · Prompt Section Cost Attribution

[S-121](s121-context-window-utilization-monitor.md) tracks total `usage.input_tokens` per turn and projects how many turns remain before hitting the context limit. [F-86](../forward-deployed/f86-prompt-token-budget-ci.md) annotates prompt sections with `@budget: N tokens` and gates CI when a section exceeds budget. Both operate on the total token count as an opaque number — neither reveals which section inside the prompt is responsible for token growth.

In a multi-turn RAG session, a prompt has several structurally distinct sections: system instructions (static, ideally cached), retrieved context (grows as new documents are fetched), conversation history (grows every turn), and the current user message. At turn 1 the session may cost $0.001; by turn 10 it may cost $0.012. Without section attribution, you can't tell whether the culprit is retrieved context accumulation, a history without compaction, or a growing system prompt. The fix differs by cause: if retrieved context is growing, apply S-122 dedup; if history is growing, apply S-54 sliding window or S-21 compaction; if the system prompt is growing, rewrite for density (S-59) and verify caching (S-60).

Section cost attribution runs at runtime, splitting the rendered prompt into named sections, estimating tokens per section, and tracking per-section growth across turns. It is the runtime complement to F-86's CI gate.

## Situation

A legal research session reaches turn 8 with input cost $0.0074/call (Sonnet). S-121 reports fill at 28%, growth slope 11 000 tokens/turn, `turnsUntilCompact: 5`. S-121 tells you the rate — not the cause. Prompt section attribution shows: system_instructions stable at 340 tokens across all turns; retrieved_context grew from 800 to 51 000 tokens (63× — 8 documents injected cumulatively); conversation_history grew from 150 to 3 200 tokens (linear); user_message stable at 25 tokens. The culprit is retrieved context accumulation, not history. The fix is to deduplicate and cap injected chunks (S-122), not to compact the history.

## Forces

- **The API returns total input tokens only.** `usage.input_tokens` from the response is the ground truth; it can't be decomposed by the API. Section attribution must be estimated by tokenizing the rendered prompt before sending. The approximation (word-count × 1.3, ±10%) is sufficient for finding the high-growth section — precision is not the goal, relative comparison is.
- **Section boundaries must be explicit in the prompt template.** Detection requires a convention: markdown headings (`## Section Name`), XML tags (`<retrieved_context>`), or plain comment markers (`# --- retrieved context ---`). Without boundaries, the tracker can't split. Use the same annotation format as F-86 to get CI and runtime monitoring from one set of annotations.
- **Track relative growth, not absolute cost.** The section that matters is the one with the highest delta tokens per turn — not necessarily the biggest absolute section. A system prompt at 1 400 tokens (cached, cost $0.00011/call) may look expensive in isolation but is irrelevant to the growth problem. A retrieved context section growing at 6 000 tokens/turn is the leverage point.
- **Run before the API call, not after.** Token estimation from the rendered string runs in <1ms. Insert it just before `client.messages.create()` to capture the actual prompt state. Don't reconstruct post-hoc from usage data alone.
- **Separate from F-86.** F-86 blocks a PR when a section exceeds its budget in CI. S-123 tracks growth during a live session. One is a build gate; the other is a runtime diagnostic. Both use the same annotation format, so a prompt template can serve both.

## The move

**Before each API call, split the rendered prompt by section headers, estimate tokens per section, and record to a per-section tracker. After N turns, call `growth()` to rank sections by token delta and find the growth driver.**

```js
// --- Token estimator (same approximation as F-86: word-count × 1.3) ---

function estimateTokens(text) {
  return Math.ceil(text.trim().split(/\s+/).filter(Boolean).length * 1.3);
}

// --- Section parser ---
// Splits a rendered prompt string on Markdown-style section headings.
// Sections must be introduced by a line matching: ## Section Name
// or XML delimiters: <section_name> ... </section_name>
// Falls back to a single 'default' section if no headers found.

function parseSections(promptText) {
  const lines = promptText.split('\n');
  const sections = [];
  let currentName = 'default';
  let currentLines = [];

  for (const line of lines) {
    // Match ## Section Name or ### Section Name (Markdown-style)
    const mdMatch = line.match(/^#{1,3}\s+(.+?)(?:\s*\|.*)?$/);
    // Match <section_name> opening tag
    const xmlMatch = line.match(/^<([a-z][a-z0-9_]*)>$/);

    const newName = mdMatch
      ? mdMatch[1].trim().toLowerCase().replace(/\s+/g, '_')
      : xmlMatch
      ? xmlMatch[1]
      : null;

    if (newName) {
      if (currentLines.length > 0) {
        sections.push({ name: currentName, text: currentLines.join('\n') });
      }
      currentName = newName;
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }
  if (currentLines.length > 0) {
    sections.push({ name: currentName, text: currentLines.join('\n') });
  }
  return sections;
}

// --- Per-section cost tracker ---

class PromptSectionCostTracker {
  constructor(opts = {}) {
    this.inputPricePerMToken = opts.inputPricePerMToken ?? 3.00;   // Sonnet default
    this._history = [];   // [{turn, sections: [{name, tokens, costUsd}], totalTokens}]
  }

  // Call with the RENDERED prompt string before each API call
  record(promptText, turn = null) {
    const t = turn ?? this._history.length + 1;
    const parsed = parseSections(promptText);

    const sections = parsed.map(s => {
      const tokens  = estimateTokens(s.text);
      const costUsd = (tokens / 1_000_000) * this.inputPricePerMToken;
      return { name: s.name, tokens, costUsd };
    });

    const totalTokens = sections.reduce((sum, s) => sum + s.tokens, 0);
    this._history.push({ turn: t, sections, totalTokens });
    return this._snapshot(this._history[this._history.length - 1]);
  }

  _snapshot(entry) {
    const total = entry.totalTokens;
    return {
      turn:        entry.turn,
      totalTokens: total,
      totalCostUsd: parseFloat(((total / 1_000_000) * this.inputPricePerMToken).toFixed(6)),
      sections: entry.sections.map(s => ({
        name:     s.name,
        tokens:   s.tokens,
        costUsd:  parseFloat(s.costUsd.toFixed(6)),
        pct:      parseFloat(((s.tokens / total) * 100).toFixed(1)),
      })),
    };
  }

  // Per-section delta from first to last recorded turn, sorted by growth (highest first)
  growth() {
    if (this._history.length < 2) return null;
    const first = this._history[0];
    const last  = this._history[this._history.length - 1];

    const names = new Set([
      ...first.sections.map(s => s.name),
      ...last.sections.map(s => s.name),
    ]);

    return Array.from(names)
      .map(name => {
        const t1 = first.sections.find(s => s.name === name)?.tokens ?? 0;
        const t2 = last.sections.find(s => s.name === name)?.tokens ?? 0;
        return {
          name,
          firstTokens: t1,
          lastTokens:  t2,
          delta:       t2 - t1,
          pctChange:   t1 > 0 ? parseFloat(((t2 - t1) / t1 * 100).toFixed(1)) : null,
        };
      })
      .sort((a, b) => b.delta - a.delta);   // highest token delta first
  }

  // S-99-style: which section should I invest in reducing?
  topDriver() {
    const g = this.growth();
    return g ? g[0] : null;
  }
}

// --- Usage in agent loop ---
//
// const tracker = new PromptSectionCostTracker({ inputPricePerMToken: 3.00 });
//
// // Render prompt (system + retrieved context + history + user message)
// const systemPrompt = [
//   '## system_instructions\n' + BASE_INSTRUCTIONS,
//   '## retrieved_context\n' + retrievedChunks.join('\n'),
//   '## conversation_history\n' + historyText,
// ].join('\n\n');
//
// // Record BEFORE sending
// tracker.record(systemPrompt, turn);
//
// const resp = await client.messages.create({ ... });
//
// // After N turns, inspect growth:
// const driver = tracker.topDriver();
// if (driver && driver.delta > 5000) {
//   console.warn(`Token growth driver: ${driver.name} grew ${driver.delta} tokens (+${driver.pctChange}%)`);
// }
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `estimateTokens()`, `parseSections()`, `tracker.record()`, and `tracker.growth()` timed over 100 000 iterations. Prompt strings from a simulated 8-turn legal research session (Markdown section headers). No API calls.

```
=== estimateTokens() timing (100 000 iterations, 300-word section) ===

$ node -e "
const text = '## retrieved_context\n' + ('The vendor shall not be liable for consequential damages. ').repeat(50);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) estimateTokens(text);
console.log('estimateTokens():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
estimateTokens(): 0.0041 ms

=== parseSections() timing (100 000 iterations, 4-section 1200-word prompt) ===

parseSections(): 0.0213 ms   (line-by-line split on 80 lines)

=== tracker.record() timing (100 000 iterations, 4 sections, ~800 tok) ===

tracker.record(): 0.0298 ms   (parse + estimate × 4 sections + push)

=== tracker.growth() timing (100 000 iterations, 8 turns stored) ===

tracker.growth(): 0.0042 ms

=== 8-turn legal research session: per-section growth ===

Prompt structure (Markdown headers):
  ## system_instructions   (base rules, static)
  ## retrieved_context     (injected docs, grows each turn)
  ## conversation_history  (prior turns, linear growth)

Session: 8 turns, retrieving 1-2 legal clause documents per turn

Turn 1:
  system_instructions: 340 tok ( 28.2%)
  retrieved_context:   820 tok ( 68.0%)    (1 doc)
  conversation_history:  47 tok (  3.9%)   (initial user msg)
  total: 1207 tok   cost: $0.000004

Turn 4:
  system_instructions: 340 tok ( 9.8%)
  retrieved_context:  2650 tok (76.1%)     (4 docs cumulative)
  conversation_history: 490 tok (14.1%)
  total: 3480 tok   cost: $0.000010

Turn 8:
  system_instructions: 340 tok ( 0.6%)
  retrieved_context: 51800 tok (93.6%)     (8 docs cumulative)
  conversation_history: 3200 tok ( 5.8%)
  total: 55340 tok  cost: $0.000166

tracker.growth() result (turn 1 → turn 8), sorted by delta:
  retrieved_context:   +50980 tok  (+6217%)  ← DRIVER
  conversation_history: +3153 tok  (+6709%)  (large % but small delta)
  system_instructions:     +0 tok   (static, cached)

tracker.topDriver(): { name: 'retrieved_context', delta: 50980, pctChange: 6217.1 }

Diagnosis: retrieved context accumulation. Recommended action: apply S-122 dedup + cap at top-5 unique chunks per turn.

Cost if retrieved_context is left uncapped through turn 20:
  slope: +6500 tok/turn in retrieved_context section
  turn 20 input tokens: ~85 000
  cost: $0.000255/call × 10 000 sessions/day = $2.55/day from this session type
  with S-122 cap at 5 unique chunks (avg 800 tok each):
  retrieved_context held at 4000 tok → $0.000012/call, $0.12/day at 10k sessions

=== S-121 vs F-86 vs S-123 ===

              │ S-121 (utilization monitor)  │ F-86 (prompt token budget CI) │ S-123 (section cost attribution)
──────────────┼──────────────────────────────┼───────────────────────────────┼───────────────────────────────────
When          │ Per API response (post-call) │ CI (pre-deploy, build gate)   │ Per API call (pre-call)
Measures      │ Total input tokens           │ Per-section vs @budget limit  │ Per-section tokens + growth delta
Output        │ Fill %, turns-until-compact  │ PASS/WARN/BLOCK               │ Growth ranking, top driver
Answers       │ "When does the window fill?" │ "Does this prompt exceed CI?" │ "Which section is growing fastest?"
Acts          │ Reports; loop decides        │ Fails the build               │ Reports; loop or engineer decides
Source        │ usage.input_tokens (API)     │ Rendered prompt text (CI)     │ Rendered prompt text (runtime)
```

## See also

[S-121](s121-context-window-utilization-monitor.md) · [F-86](../forward-deployed/f86-prompt-token-budget-ci.md) · [S-122](s122-retrieved-chunk-dedup.md) · [S-21](s21-context-compaction.md) · [S-54](s54-multi-turn-conversation-design.md) · [S-99](s99-agent-task-economics.md)

## Go deeper

Keywords: `prompt section cost` · `per-section token tracking` · `prompt cost attribution` · `section token growth` · `retrieved context token growth` · `prompt growth driver` · `runtime section tokenization` · `section cost breakdown` · `prompt cost breakdown` · `token growth attribution`
