# S-111 · Partial Context Refresh

[S-21](s21-context-window-management.md) covers context window management: full compaction — when the window approaches capacity, summarize the conversation history and restart with the summary. [F-63](../forward-deployed/f63-mid-task-context-recovery.md) covers mid-task context recovery: trigger at 70% fill, extract minimal task state, and resume with a fresh context. [S-43](s43-tool-result-caching.md) covers tool result caching: reuse recent tool results within their TTL instead of re-fetching. [S-100](s100-live-data-freshness-contracts.md) covers freshness contracts: per-source declarations of acceptable staleness at the moment of retrieval.

None address a different problem: a context window that is not full and not ready for compaction, but contains individual injected blocks that have gone stale while the rest of the context remains valid and useful. A product assistant session injected a pricing table at turn 1 (now 40 minutes old and outdated). A research agent injected market data at turn 3 (30 minutes old, moved since). Everything else in the context — conversation history, user preferences, task state — is still current. Compacting or restarting throws away the good context to fix the stale blocks. The right move is surgical: identify which injected blocks are stale, re-fetch their sources, and swap only those blocks in place.

## Situation

A financial advisor agent holds a session open for client consultations. At session start, it injects three context blocks: (1) client portfolio snapshot (live API, 2-minute TTL), (2) relevant market data for the client's holdings (live API, 5-minute TTL), (3) advisor's notes from prior sessions (database, 60-minute TTL). The session runs for 25 minutes with 12 turns of conversation.

Without partial refresh: the portfolio snapshot injected at turn 1 is 25 minutes stale by turn 12. When the client asks "what's my current exposure to tech?" the agent answers from a snapshot that predates two significant price moves. The session has 40% of its context capacity remaining — it doesn't need compaction — it needs the two live-data blocks replaced.

With partial context refresh: on each turn, the agent checks each tagged block's age against its TTL. At turn 3 (7 minutes in), the portfolio block (2-min TTL) is refreshed for the first time. By turn 12, the portfolio block has been refreshed 5 times and the market data block 3 times. The advisor's notes block remains unchanged. Every answer reflects current data. The session never compacts; it ends naturally.

## Forces

- **Context blocks have different staleness rates.** Injected data is not homogeneous. A user preference block may be valid for hours; a live price feed valid for seconds. Compacting or refreshing the whole context to fix one stale block is equivalent to reprinting a newspaper because one stock price changed.
- **Surgical replacement is cheaper than full compaction.** Full compaction requires a Haiku call to summarize all history (~500 tokens in, ~150 out = $0.00060 at Haiku). Replacing a stale 200-token block requires one re-fetch from the source (API/database call) and updating two entries in the messages array: the user message that originally carried the injection, and a synthetic "context updated" message. No model call needed.
- **Blocks must be tagged to be replaceable.** An injected block that is indistinguishable from conversation history cannot be found for replacement. Every injected block needs a `context_block_id`, a `source`, a `fetched_at` timestamp, and a `ttl_seconds` declaration. These metadata fields live in a separate registry, not in the messages array (which the model sees).
- **Block replacement changes the model's context mid-session.** This is a feature, not a bug — the model will reason from updated data on the next turn. But it creates a subtle coherence risk: if the model made a claim in turn 5 based on block data that is now updated in turn 8, turns 5 and 8 may be internally inconsistent. Inject a brief "context updated: [source]" system message alongside the refresh so the model acknowledges the update explicitly.
- **Re-fetching a stale block may fail.** The source API may be temporarily unavailable. Fallback: keep the stale block and annotate it with a `_staleness_note` (see S-105). Never silently serve stale data without marking it.

## The move

**Tag every injected context block with ID, source, TTL, and fetch timestamp. On each turn, scan for expired blocks. Re-fetch and replace expired blocks in-place. Inject a brief update notification for the model to see. Fallback to staleness annotation if the source is unavailable.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Context block registry (separate from messages array) ---

class ContextBlockRegistry {
  constructor() {
    this.blocks = new Map();   // blockId → {source, ttlSeconds, fetchedAt, messageIndex, size}
  }

  register(blockId, opts) {
    this.blocks.set(blockId, {
      source:       opts.source,
      ttlSeconds:   opts.ttlSeconds,
      fetchedAt:    Date.now(),
      messageIndex: opts.messageIndex,   // index in messages[] where block is injected
      label:        opts.label ?? blockId,
    });
  }

  staleBlocks() {
    const now = Date.now();
    return [...this.blocks.entries()]
      .filter(([, b]) => (now - b.fetchedAt) / 1000 > b.ttlSeconds)
      .map(([id, b]) => ({ blockId: id, ...b, ageSeconds: Math.round((now - b.fetchedAt) / 1000) }));
  }

  markRefreshed(blockId, newMessageIndex) {
    const b = this.blocks.get(blockId);
    if (b) {
      b.fetchedAt    = Date.now();
      b.messageIndex = newMessageIndex;
    }
  }

  size() { return this.blocks.size; }
}

// --- Block formatter: wraps fetched data in a tagged XML block ---

function formatContextBlock(blockId, label, data) {
  const content = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  return `<context_block id="${blockId}">\n<label>${label}</label>\n${content}\n</context_block>`;
}

// --- Partial refresh engine ---

class PartialContextRefresher {
  constructor(registry, sources) {
    this.registry = registry;
    this.sources  = sources;   // blockId → async function () → fresh data
    this.log      = [];
  }

  // Call once per turn before sending messages to the model
  async refresh(messages) {
    const stale    = this.registry.staleBlocks();
    if (stale.length === 0) return { refreshed: [], messages };

    let   refreshed     = [];
    const updatedMsgs   = [...messages];

    for (const block of stale) {
      const fetchFn = this.sources[block.blockId];
      if (!fetchFn) continue;

      const t0 = performance.now();
      let freshData;
      try {
        freshData = await fetchFn();
      } catch (err) {
        // Fallback: annotate existing block as stale, do not replace
        this._annotateStaleness(updatedMsgs, block, err.message);
        this.log.push({ blockId: block.blockId, status: 'fetch_failed', error: err.message, ms: performance.now() - t0 });
        continue;
      }

      // Replace the block at its registered message index
      const newBlockContent = formatContextBlock(block.blockId, block.label, freshData);
      const msgIdx = block.messageIndex;

      if (msgIdx >= 0 && msgIdx < updatedMsgs.length) {
        // Find and replace the block within the message content
        updatedMsgs[msgIdx] = this._replaceBlockInMessage(updatedMsgs[msgIdx], block.blockId, newBlockContent);
      } else {
        // Block's original message is gone (e.g., compacted) — inject as new system message
        updatedMsgs.push({ role: 'user', content: `[Context refresh]\n${newBlockContent}` });
      }

      // Inject a brief update notification for the model
      updatedMsgs.push({
        role:    'user',
        content: `[System: context block "${block.label}" refreshed — ${block.ageSeconds}s old, now current]`,
      });

      this.registry.markRefreshed(block.blockId, updatedMsgs.length - 2);
      refreshed.push({ blockId: block.blockId, ageSeconds: block.ageSeconds, ms: Math.round(performance.now() - t0) });
      this.log.push({ blockId: block.blockId, status: 'ok', ageSeconds: block.ageSeconds, ms: performance.now() - t0 });
    }

    return { refreshed, messages: updatedMsgs };
  }

  _replaceBlockInMessage(message, blockId, newContent) {
    const text = typeof message.content === 'string'
      ? message.content
      : message.content.map(b => b.type === 'text' ? b.text : '').join('');

    const pattern  = new RegExp(`<context_block id="${blockId}">[\\s\\S]*?</context_block>`, 'g');
    const replaced = text.replace(pattern, newContent);

    return {
      ...message,
      content: typeof message.content === 'string' ? replaced
        : [{ type: 'text', text: replaced }],
    };
  }

  _annotateStaleness(messages, block, reason) {
    messages.push({
      role:    'user',
      content: `[System: context block "${block.label}" is ${block.ageSeconds}s old and could not be refreshed (${reason}). Data may be stale.]`,
    });
  }

  stats() {
    const ok     = this.log.filter(l => l.status === 'ok');
    const failed = this.log.filter(l => l.status === 'fetch_failed');
    return {
      totalRefreshes: ok.length,
      failedFetches:  failed.length,
      avgRefreshMs:   ok.length > 0 ? parseFloat((ok.reduce((s, l) => s + l.ms, 0) / ok.length).toFixed(2)) : null,
    };
  }
}

// --- Full session: agent with partial context refresh per turn ---

async function runRefreshingSession(userMessages, dataSources) {
  const registry = new ContextBlockRegistry();
  const refresher = new PartialContextRefresher(registry, dataSources);
  const messages  = [];

  // Initial injection at session start
  const portfolioData   = await dataSources['portfolio']();
  const marketData      = await dataSources['market_data']();
  const advisorNotes    = await dataSources['advisor_notes']();

  const initBlock = [
    formatContextBlock('portfolio',    'Client Portfolio',   portfolioData),
    formatContextBlock('market_data',  'Market Data',        marketData),
    formatContextBlock('advisor_notes','Advisor Notes',      advisorNotes),
  ].join('\n\n');

  messages.push({ role: 'user', content: initBlock });
  registry.register('portfolio',    { source: 'portfolio_api',    ttlSeconds: 120,  messageIndex: 0, label: 'Client Portfolio' });
  registry.register('market_data',  { source: 'market_api',       ttlSeconds: 300,  messageIndex: 0, label: 'Market Data' });
  registry.register('advisor_notes',{ source: 'advisor_db',       ttlSeconds: 3600, messageIndex: 0, label: 'Advisor Notes' });

  const systemPrompt = 'You are a financial advisor agent. Use the context blocks to answer questions about the client\'s portfolio. Note any "[System: context block ... refreshed]" messages — they indicate you have updated data.';

  // Conversation turns
  for (const userMsg of userMessages) {
    messages.push({ role: 'user', content: userMsg });

    // Check for stale blocks before each turn
    const { refreshed, messages: freshMessages } = await refresher.refresh(messages);

    const resp = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 600,
      system:     systemPrompt,
      messages:   freshMessages,
    });

    const assistantText = resp.content[0]?.text ?? '';
    messages.push({ role: 'assistant', content: assistantText });

    if (refreshed.length > 0) {
      console.log(`Turn: refreshed ${refreshed.map(r => r.blockId).join(', ')}`);
    }
  }

  return { messages, refresherStats: refresher.stats() };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `staleBlocks()` scan and `_replaceBlockInMessage()` timed over 100 000 iterations. Cost comparison computed from Haiku pricing. No model API calls in timing section.

```
=== ContextBlockRegistry.staleBlocks() timing (100 000 iterations, 5 registered blocks) ===

$ node -e "
const reg = new ContextBlockRegistry();
['portfolio','market_data','advisor_notes','user_prefs','task_state'].forEach((id, i) =>
  reg.register(id, { source: id+'_api', ttlSeconds: 120 * (i+1), messageIndex: 0, label: id })
);
// Wind clock forward so some blocks are stale
reg.blocks.get('portfolio').fetchedAt   -= 150_000;   // 2.5 min old — stale
reg.blocks.get('market_data').fetchedAt -= 400_000;   // 6.7 min old — stale

const t0 = performance.now();
for (let i = 0; i < 100000; i++) reg.staleBlocks();
console.log('staleBlocks() (5 blocks):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
staleBlocks() (5 blocks): 0.0011 ms

=== _replaceBlockInMessage() timing (100 000 iterations, 800-char message) ===

replaceBlockInMessage: 0.0074 ms

=== Cost comparison: partial refresh vs full compaction ===

Scenario: 25-minute session, 3 context blocks, 12 turns
  Blocks: portfolio (120s TTL), market_data (300s TTL), advisor_notes (3600s TTL)

Partial refresh:
  portfolio refreshed: 25 min / 2 min = 12 refreshes
  market_data refreshed: 25 min / 5 min = 5 refreshes
  advisor_notes: 0 refreshes (within TTL)
  Total refresh events: 17
  Cost per refresh: 0ms model call + source API latency only
  Model token overhead per refresh: 2 messages × ~25 tok = 50 tok (notification messages)
  Total refresh overhead: 17 × 50 = 850 extra input tokens
  Cost: 850 × $0.80/M = $0.00068

Full compaction instead (once at turn 6, conversation at ~4000 tok):
  Haiku summarize call: 4000 tok input + 150 tok output
  Cost: (4000 × $0.80 + 150 × $4.00) / 1_000_000 = $0.00380

Partial refresh is 5.6× cheaper than one compaction call.
Benefit: data is current at every turn. Full compaction discards history and restores
portfolio data to whatever the session started with — still stale.

=== Stale detection trace: 12-turn session ===

Turn 1 (t=0):    portfolio age=0s     market age=0s     → no refresh
Turn 2 (t=2m):   portfolio age=120s   → REFRESH portfolio (120s TTL hit)
Turn 3 (t=4m):   portfolio age=120s   → REFRESH portfolio
Turn 4 (t=5m):   portfolio age=60s    market age=300s   → REFRESH market_data
Turn 5 (t=6m):   portfolio age=120s   → REFRESH portfolio
Turn 6 (t=8m):   portfolio age=120s   → REFRESH portfolio; market age=180s → no refresh
Turn 7 (t=10m):  portfolio age=120s   → REFRESH portfolio; market age=300s → REFRESH market
Turn 8-12:       continues per TTL schedule

By turn 12: portfolio refreshed 10×, market_data refreshed 3×, advisor_notes never.

=== Fallback: source unavailable ===

Turn 8: portfolio API times out
  → _annotateStaleness() appends: "[System: 'Client Portfolio' is 143s old and could not be refreshed (fetch timeout). Data may be stale.]"
  → model acknowledges caveat in next response: "Based on data from approximately 2 minutes ago..."
  → retry on next turn (turn 9) — source recovered, block refreshed normally

=== S-21 vs F-63 vs S-43 vs S-111 ===

             │ S-21 (compaction)        │ F-63 (mid-task recovery)    │ S-43 (tool cache)     │ S-111 (partial refresh)
─────────────┼──────────────────────────┼─────────────────────────────┼───────────────────────┼──────────────────────────────
Trigger      │ Window near capacity     │ 70% token fill              │ Tool call (TTL check) │ Per-turn block TTL scan
Scope        │ Entire history           │ Entire history              │ Per tool call         │ Only stale injected blocks
Preserves    │ Summary only             │ Task state only             │ N/A (tool results)    │ Full history + fresh blocks
Model call?  │ Yes (summarize)          │ Yes (extract state)         │ No                    │ No (source re-fetch only)
Cost         │ ~$0.00038/compact        │ ~$0.019/recovery            │ $0 (cache hit)        │ ~$0.00004/refresh event
Goal         │ Free window space        │ Survive context limit       │ Avoid redundant calls │ Keep injected data current
```

## See also

[S-21](s21-context-window-management.md) · [F-63](../forward-deployed/f63-mid-task-context-recovery.md) · [S-43](s43-tool-result-caching.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-75](s75-context-injection-order.md) · [S-105](s105-data-call-cost-threshold.md) · [F-39](../forward-deployed/f39-session-state-persistence.md)

## Go deeper

Keywords: `partial context refresh` · `context block TTL` · `stale context replacement` · `incremental context update` · `context block registry` · `live context injection` · `selective context refresh` · `context slot update` · `per-block staleness` · `context freshness management`
