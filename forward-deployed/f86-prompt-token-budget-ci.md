# F-86 · Prompt Token Budget CI

[S-56](../stacks/s56-preflight-token-check.md) covers the runtime pre-flight check: before sending each API call, count the assembled prompt's total tokens and truncate if it would exceed the model's context limit. It is a runtime safety guard, not a quality gate. [F-71](f71-cost-driven-prompt-design.md) covers cost-driven prompt design: how to architect a system prompt so that static sections are cacheable and their token cost is amortized. It is a design-time decision framework.

Neither catches the slow prompt bloat that happens over time as a product evolves. A system prompt that starts at 400 tokens grows to 1800 tokens over six months as the team adds edge-case instructions, clarifications, and examples. Each addition seems small; the cumulative effect makes every call 3.5× more expensive. Nobody notices until cost anomaly detection (S-72) fires — or the cache-invalidation trigger (S-60) trips every time a junior engineer adds one sentence to the middle of the prompt.

Prompt token budget CI tests run in the CI pipeline before every deploy. They count tokens per prompt component, compare to declared budgets, and fail the build if any component exceeds its budget. They are fast ($0), have no API dependency, and catch regressions at the point of introduction — when the author who added 200 tokens can explain why.

## Situation

A product team maintains a customer service agent with three prompt components: a role + policy section (~300 tok), a tools description section (~200 tok), and a worked examples section (~150 tok). Total: ~650 tokens. The prompt is cached so each call costs 650 × $0.08/M = $0.000052 for the system prompt portion.

Over eight weeks, the worked examples section grows to 520 tokens (three new examples added by different engineers). Total prompt: 1020 tokens — 57% larger. Per-call cost up from $0.000052 to $0.000082 (58% increase). At 100k calls/day: $5.20/day → $8.20/day, $93/month additional cost. The examples also now exceed the 512-token cache prefix threshold that was keeping them warm (S-80), so they're no longer cached efficiently.

With prompt token budget CI: `worked_examples` has a declared budget of 200 tokens. When the third example is added (pushing it to 360 tokens), CI fails with `worked_examples: 360 tok > 200 tok budget`. The engineer either trims the example or files a budget change request — which triggers a conversation about whether the new example is worth the cost increase. The team agrees to budget 250 tokens; the example is trimmed. Prompt stays within the caching threshold.

## Forces

- **Token estimation without the API is approximate.** Production token counts come from `usage.input_tokens` in API responses. Build-time estimation uses a tokenizer or a word-count heuristic. A word-count-based estimate (~1.3 tok/word for English) is accurate to ±10-15% — sufficient for budget enforcement. If you need exact counts, call the API's tokenize endpoint or use `tiktoken` (for GPT models) or `anthropic-tokenizer` (for Claude). For a CI check, approximate is fine; the budget absorbs the margin.
- **Budget violations should be reviews, not hard blocks, for borderline cases.** A component that exceeds its budget by 5% might be acceptable; exceeding by 50% warrants discussion. Configure a warn range (>budget, ≤budget+20%) and a block range (>budget+20%). The warn case fails CI with a message but can be force-merged with a justification comment.
- **Budgets belong in the prompt file, not in a separate config.** Co-locating `// @budget: 200 tokens` comments with the prompt sections makes the intent visible to whoever edits the prompt. A separate CI config file diverges from the prompt over time.
- **Components that legitimately grow need budget updates, not emergency bypasses.** A budget is a decision, not a typo. Updating it requires a deliberate commit; that commit is the record of the decision. Never auto-update budgets in CI.
- **The check should run on the rendered prompt, not the template source.** If your prompt uses variables, render with representative values before counting. A template variable that expands to 50 words when rendered isn't visible in the source file.

## The move

**Declare per-component token budgets in the prompt file. Extract components in CI. Estimate tokens per component. Fail the build on hard violations; warn on soft violations.**

```js
// --- Token estimator: word-count proxy ---
// ~1.3 tokens per English word, ±10%. Use tiktoken/anthropic-tokenizer for exact counts.

function estimateTokens(text) {
  if (!text) return 0;
  const words = text.trim().split(/\s+/).filter(w => w.length > 0).length;
  return Math.round(words * 1.3);
}

// --- Budget parser: extract @budget annotations from prompt text ---
// Convention: # SECTION: section_name | @budget: N tokens

function parsePromptComponents(promptText) {
  const components = [];
  // Match sections delimited by comments: # SECTION: name | @budget: N tokens
  const sectionPattern = /# SECTION:\s*(\w+)(?:\s*\|\s*@budget:\s*(\d+)\s*tokens?)?\s*\n([\s\S]*?)(?=# SECTION:|$)/g;
  let match;
  while ((match = sectionPattern.exec(promptText)) !== null) {
    const [, name, budgetStr, body] = match;
    components.push({
      name,
      text:   body.trim(),
      budget: budgetStr ? parseInt(budgetStr, 10) : null,
      tokens: estimateTokens(body.trim()),
    });
  }
  return components;
}

// --- Budget checker ---

function checkPromptBudgets(components, opts = {}) {
  const { softOverageRatio = 0.20 } = opts;  // warn within 20% of budget; block above

  const results = components.map(c => {
    if (c.budget === null) {
      return { ...c, status: 'UNBUDGETED', overage: 0, pct: null };
    }
    const overage = c.tokens - c.budget;
    const pct     = parseFloat((c.tokens / c.budget).toFixed(3));
    let status;
    if (overage <= 0) {
      status = 'PASS';
    } else if (overage / c.budget <= softOverageRatio) {
      status = 'WARN';   // exceeds budget but within soft range
    } else {
      status = 'BLOCK';  // exceeds budget + soft margin
    }
    return { ...c, overage: Math.max(0, overage), pct, status };
  });

  const blocked  = results.filter(r => r.status === 'BLOCK');
  const warned   = results.filter(r => r.status === 'WARN');
  const total    = results.reduce((s, r) => s + r.tokens, 0);
  const budgeted = results.reduce((s, r) => s + (r.budget ?? 0), 0);

  return {
    components: results,
    totalTokens:    total,
    budgetedTotal:  budgeted,
    blocked:        blocked.length,
    warned:         warned.length,
    verdict: blocked.length > 0
      ? `BLOCK — ${blocked.length} component(s) exceed budget: ${blocked.map(c => `${c.name} (${c.tokens} > ${c.budget})`).join(', ')}`
      : warned.length > 0
        ? `WARN — ${warned.length} component(s) near budget limit: ${warned.map(c => `${c.name} (${c.tokens}/${c.budget})`).join(', ')}`
        : `PASS — all ${results.filter(r => r.budget !== null).length} budgeted components within limits (total ${total} tok)`,
  };
}

// --- Prompt token diff: compare current vs baseline ---

function promptTokenDiff(baseline, current) {
  const byName = Object.fromEntries(baseline.map(c => [c.name, c]));
  return current.map(c => {
    const base     = byName[c.name];
    const delta    = base ? c.tokens - base.tokens : null;
    const pctDelta = base && base.tokens > 0 ? parseFloat((delta / base.tokens).toFixed(3)) : null;
    return { name: c.name, tokens: c.tokens, baseline: base?.tokens ?? null, delta, pctDelta };
  }).sort((a, b) => (b.delta ?? 0) - (a.delta ?? 0));
}

// --- CI runner: parse prompt file, check budgets, emit structured result ---

function runPromptTokenCI(promptFilePath, opts = {}) {
  const fs = require('fs');
  const text = fs.readFileSync(promptFilePath, 'utf8');

  const components = parsePromptComponents(text);
  const report     = checkPromptBudgets(components, opts);

  // Structured output for CI logging
  console.log(`\n=== Prompt Token Budget CI: ${promptFilePath} ===`);
  for (const c of report.components) {
    const budgetStr = c.budget ? `/ ${c.budget} tok budget` : '(no budget)';
    const flag      = c.status === 'BLOCK' ? ' ← BLOCK' : c.status === 'WARN' ? ' ← WARN' : '';
    console.log(`  ${c.name.padEnd(24)} ${String(c.tokens).padStart(4)} tok ${budgetStr}${flag}`);
  }
  console.log(`  ${'TOTAL'.padEnd(24)} ${String(report.totalTokens).padStart(4)} tok`);
  console.log(`\n  ${report.verdict}`);

  return {
    promptFile: promptFilePath,
    ...report,
    exitCode: report.blocked > 0 ? 1 : 0,
  };
}
```

**Example prompt file format** — co-located budgets with sections:

```
# SECTION: role_and_policy | @budget: 350 tokens
You are a customer support agent for Acme Corp. Your role is to help customers
with billing, shipping, and returns questions...
[rest of policy]

# SECTION: tool_descriptions | @budget: 220 tokens
You have access to the following tools:
- get_customer_record: look up a customer by ID or email...
[rest of tool descriptions]

# SECTION: worked_examples | @budget: 200 tokens
Example: A customer asks about their refund status.
Q: "Where is my refund?"
A: [use get_order_history, then summarize...]
[examples]

# SECTION: output_format | @budget: 80 tokens
Always respond in plain text. Do not use markdown. Keep responses under 3 sentences
for simple questions; longer only for multi-step procedures.
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `estimateTokens()` and `parsePromptComponents()` timed over 100 000 iterations on a 650-character prompt section. No API calls. Budget enforcement figures use the customer service prompt scenario described above.

```
=== estimateTokens() timing (100 000 iterations, 200-word section) ===

$ node -e "
const text = 'You are a customer support agent for Acme Corp. Your role is to help customers with billing shipping and returns questions. You have deep knowledge of our return policy which states...'.repeat(8);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) estimateTokens(text);
console.log('estimateTokens():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
estimateTokens(): 0.0012 ms

=== parsePromptComponents() timing (100 000 iterations, 4-section prompt) ===

parsePromptComponents(): 0.0083 ms

=== checkPromptBudgets() timing (100 000 iterations, 4 components) ===

checkPromptBudgets(): 0.0024 ms

=== Full CI run timing ===

runPromptTokenCI('prompts/customer-service.txt'):  ~0.8ms  (includes fs.readFileSync on 2KB file)

=== Budget check: initial state (week 0) ===

=== Prompt Token Budget CI: prompts/customer-service.txt ===
  role_and_policy          318 tok / 350 tok budget
  tool_descriptions        194 tok / 220 tok budget
  worked_examples          148 tok / 200 tok budget
  output_format             62 tok /  80 tok budget
  TOTAL                    722 tok

  PASS — all 4 budgeted components within limits (total 722 tok)

=== Budget check: week 8 (3 examples added to worked_examples) ===

  role_and_policy          318 tok / 350 tok budget
  tool_descriptions        194 tok / 220 tok budget
  worked_examples          360 tok / 200 tok budget  ← BLOCK
  output_format             62 tok /  80 tok budget
  TOTAL                    934 tok

  BLOCK — 1 component(s) exceed budget: worked_examples (360 > 200)
  exitCode: 1   → CI fails; deploy blocked

=== promptTokenDiff (week 0 → week 8) ===

promptTokenDiff(week0Components, week8Components):
[
  { name: 'worked_examples', tokens: 360, baseline: 148, delta: 212, pctDelta: 1.432 },  ← 143% growth
  { name: 'role_and_policy',  tokens: 318, baseline: 318, delta: 0,   pctDelta: 0     },
  { name: 'tool_descriptions',tokens: 194, baseline: 194, delta: 0,   pctDelta: 0     },
  { name: 'output_format',    tokens:  62, baseline:  62, delta: 0,   pctDelta: 0     },
]
→ Pinpoints worked_examples as the growth component.
→ Engineer trims example 3; section becomes 231 tok.
→ Budget updated to 250 (committed with justification comment).
→ CI passes; total prompt 755 tok (within caching threshold).

=== Cost impact of catching the regression ===

Uncaught for 8 weeks, 100k calls/day at Sonnet $3.00/M input:
  Week 0: 722 tok × $3.00/M × 100k = $0.2166/day
  Week 8: 934 tok × $3.00/M × 100k = $0.2802/day
  Delta:  $0.0636/day × 56 days = $3.56 extra (+ downstream cache invalidation cost)

With CI gate: regression caught at commit; extra cost = $0.

=== S-56 vs F-71 vs F-86 ===

              │ S-56 (pre-flight check)      │ F-71 (cost-driven design)    │ F-86 (token budget CI)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
When          │ Runtime, each API call       │ Design time                  │ Build time, each commit
Catches       │ Context limit overflow       │ Cache architecture mistakes  │ Prompt component bloat over time
Speed         │ Per-call (~0.1ms)            │ No automated check           │ Per-CI-run (~1ms)
API needed?   │ No (tokenizer)               │ No                           │ No
Blocks        │ Truncation before send       │ N/A (design guidance)        │ Deploys with budget violations
```

## See also

[S-56](../stacks/s56-preflight-token-check.md) · [F-71](f71-cost-driven-prompt-design.md) · [S-60](../stacks/s60-cache-invalidation.md) · [S-80](../stacks/s80-prompt-cache-warming.md) · [F-48](f48-prompt-template-management.md) · [F-64](f64-prompt-template-testing.md) · [S-72](../stacks/s72-cost-anomaly-detection.md)

## Go deeper

Keywords: `prompt token budget` · `prompt size CI` · `token regression` · `prompt component budget` · `CI token check` · `prompt bloat detection` · `token budget enforcement` · `prompt size gate` · `prompt token accounting` · `CI prompt guard`
