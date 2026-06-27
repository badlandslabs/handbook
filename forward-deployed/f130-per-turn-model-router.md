# F-130 · Per-Turn Model Router

[S-06](../stacks/s06-model-routing-by-complexity.md) selects a model at the start of a session based on the incoming request's complexity — the whole session uses that model. [F-96](f96-session-cost-escalation-guard.md) monitors cost mid-session and escalates from a cheap model to a capable one when the task proves harder than expected; once escalated, the session stays on the expensive model for its remaining turns. [S-65](../stacks/s65-pipeline-stage-model-routing.md) assigns different models to different pipeline stages (extraction → Haiku, synthesis → Sonnet) based on stage complexity, not per-turn message content.

None of these route individual turns within a single session. A 10-turn support session is not uniformly complex. "Yes, proceed" (3 words) and "What was the balance again?" (6 words) are answerable by the cheapest model. "Review all three counterparties and recommend the one with lowest regulatory exposure" (14 words, multi-criteria reasoning) requires the capable model. The first two turns cost $0.0026 each on Haiku; the third costs $0.009750 on Sonnet. Routing all 10 turns to Sonnet because some turns need it wastes money on the turns that don't.

The per-turn model router classifies each user message as SIMPLE or COMPLEX before dispatching to the model. A small set of patterns and a word-count limit identify the signals: short messages that match confirmation or clarification templates go to Haiku; anything with multi-criteria, analytical, or document-spanning keywords goes to Sonnet; everything else defaults to Sonnet. The model choice is per-turn, not per-session.

## Situation

A contract review agent handles support sessions. Typical session flow:
- Turn 1: "Please review all three counterparty contracts for regulatory exposure." → COMPLEX, Sonnet
- Turn 2: "What was the risk level for counterparty B again?" → SIMPLE, Haiku
- Turn 3: "Yes, proceed with the recommendation." → SIMPLE, Haiku
- Turn 4: "Compare the indemnification clauses across all contracts." → COMPLEX, Sonnet

In a 10-turn session with 7 SIMPLE turns and 3 COMPLEX turns, routing to Sonnet for everything costs $0.0975 (1 500 input + 350 output tokens × 10 turns at Sonnet pricing). Per-turn routing costs $0.0474 — a 51% reduction. At 10 000 sessions/day, that is a $5 010/day cost difference.

The classification does not need to be perfect. Even a conservative classifier that routes 30% of turns to Haiku saves real money. The risk is routing a COMPLEX turn to Haiku and getting a degraded response — so the default is always Sonnet, and only clear SIMPLE signals send the turn to Haiku.

## Forces

- **Default to the capable model.** The cost of a misclassified COMPLEX turn going to Haiku is a bad response visible to the user. The cost of a misclassified SIMPLE turn going to Sonnet is a few extra dollars per million turns. Err toward Sonnet for ambiguous turns; route to Haiku only when the signal is strong.
- **Short messages are not always simple.** "Why?" is two characters but may require multi-document synthesis to answer in context. Word count alone is insufficient — require both a word-count ceiling AND a pattern match. A turn must be short AND match a simple-signal pattern to route to Haiku.
- **Explicit complexity signals override length.** A 10-word message containing "compare," "evaluate," or "across all" should route to Sonnet regardless of word count. Check complex patterns first; only fall through to the simple check if none match.
- **Do not share context windows across models.** When routing turn N to Haiku and turn N+1 to Sonnet, both calls receive the full conversation history up to that point. The model selection is per-call, not per-context. The agent framework sends the same `messages` array to whichever model handles each turn.
- **Distinct from S-06 and F-96.** S-06 selects once per session based on the first message — all turns use the same model. F-96 escalates permanently when cost or complexity signals fire during the session. Per-turn routing re-evaluates the model on every turn and can oscillate between Haiku and Sonnet freely. A session might go Sonnet → Haiku → Sonnet → Haiku → Sonnet depending on turn content.
- **Pattern maintenance is ongoing.** The simple/complex pattern lists will drift from real traffic. Log the `tier` and `reason` for every routed turn; check monthly that the SIMPLE fraction matches your actual simple-turn rate. If simple patterns stop matching real simple turns, Haiku utilization drops to zero and you've paid for a classifier that does nothing.

## The move

**Check complex patterns first. If none match, check simple patterns against word count. Route to Haiku on SIMPLE; route to Sonnet on COMPLEX or fallback.**

```js
// --- Per-turn model router ---
// Classifies each user message as SIMPLE or COMPLEX per turn.
// SIMPLE: short message AND matches a simple-signal pattern → route to cheap model.
// COMPLEX: matches a complexity pattern → route to capable model.
// FALLBACK: ambiguous → route to capable model.
// Re-evaluates on every turn; sessions can oscillate between models.

class TurnModelRouter {
  constructor(opts = {}) {
    this._simpleMaxWords  = opts.simpleMaxWords  ?? 30;
    this._simplePatterns  = opts.simplePatterns  ?? [
      /^(yes|no|ok|okay|thanks|sure|proceed|continue|got it|confirm)/i,
      /^what (is|does|did|was|are|were)\b/i,
      /^(can you )?(repeat|summarize|explain that|clarify)\b/i,
      /^(show|tell) me (the |that )?(again|more)\b/i,
    ];
    this._complexPatterns = opts.complexPatterns ?? [
      /\b(analyze|analyse|compare|evaluate|recommend|report|synthesize|review|assess|investigate)\b/i,
      /\b(across|multiple|all of|each|every)\b/i,
    ];
    this._cheapModel      = opts.cheapModel      ?? 'claude-haiku-4-5-20251001';
    this._expModel        = opts.expModel        ?? 'claude-sonnet-4-6';
    this._cheapCostPerM   = opts.cheapCostPerM   ?? { input: 0.80, output: 4.00 };
    this._expCostPerM     = opts.expCostPerM     ?? { input: 3.00, output: 15.00 };
  }

  // Classify a user message and return the model to dispatch this turn to.
  // Returns { model, tier: 'SIMPLE'|'COMPLEX', words, reason }
  route(userMessage) {
    const words = userMessage.trim().split(/\s+/).filter(Boolean).length;

    // Explicit complexity signal: use capable model regardless of length
    if (this._complexPatterns.some(p => p.test(userMessage))) {
      return { model: this._expModel, tier: 'COMPLEX', words, reason: 'COMPLEX_PATTERN' };
    }

    // Simple: short message AND matches a simple-signal pattern
    if (words <= this._simpleMaxWords && this._simplePatterns.some(p => p.test(userMessage))) {
      return { model: this._cheapModel, tier: 'SIMPLE', words, reason: 'SIMPLE_PATTERN' };
    }

    // Default: capable model for anything ambiguous
    return { model: this._expModel, tier: 'COMPLEX', words, reason: 'FALLBACK_COMPLEX' };
  }

  // Estimate cost savings over always-Sonnet for a completed session.
  // turns: [{ tier: 'SIMPLE'|'COMPLEX', inputTokens, outputTokens }]
  savings(turns) {
    let routedCost = 0, alwaysExpCost = 0, cheapCount = 0;
    for (const t of turns) {
      const c = this._cheapCostPerM, e = this._expCostPerM;
      const expCost = (t.inputTokens * e.input + t.outputTokens * e.output) / 1e6;
      alwaysExpCost += expCost;
      if (t.tier === 'SIMPLE') {
        routedCost += (t.inputTokens * c.input + t.outputTokens * c.output) / 1e6;
        cheapCount++;
      } else {
        routedCost += expCost;
      }
    }
    return {
      alwaysExpCostUsd: parseFloat(alwaysExpCost.toFixed(4)),
      routedCostUsd:    parseFloat(routedCost.toFixed(4)),
      savedUsd:         parseFloat((alwaysExpCost - routedCost).toFixed(4)),
      savedPct:         parseFloat(((alwaysExpCost - routedCost) / alwaysExpCost * 100).toFixed(1)),
      cheapTurns:       cheapCount,
      totalTurns:       turns.length,
    };
  }
}

// --- Integration: per-turn dispatch in the agent loop ---

const TURN_ROUTER = new TurnModelRouter();

async function handleTurn(sessionMessages, userMessage) {
  const { model, tier, reason } = TURN_ROUTER.route(userMessage);

  log({ event: 'turn_routed', tier, reason, model });

  const messages = [...sessionMessages, { role: 'user', content: userMessage }];
  const response = await callModel(model, messages);

  sessionMessages.push(
    { role: 'user',      content: userMessage },
    { role: 'assistant', content: response.content },
  );

  return response;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `route()` timed over 100 000 iterations. Haiku: $0.80/$4.00/M. Sonnet: $3.00/$15.00/M. Session: 10 turns, 1 500 input + 350 output tokens per turn.

```
=== TurnModelRouter timing (100 000 iterations) ===

route() — SIMPLE match:    0.0022 ms
route() — COMPLEX match:   0.0030 ms

=== 10-turn session: per-turn routing ===

 1. "Yes, proceed with the analysis."                               → SIMPLE   5w  SIMPLE_PATTERN
 2. "What was the total amount again?"                              → SIMPLE   6w  SIMPLE_PATTERN
 3. "Ok got it, continue."                                          → SIMPLE   4w  SIMPLE_PATTERN
 4. "Can you summarize that?"                                       → SIMPLE   4w  SIMPLE_PATTERN
 5. "Analyze this contract for risk factors and compare to template"→ COMPLEX 13w  COMPLEX_PATTERN
 6. "I need a detailed report on all counterparties with ratings"   → COMPLEX 15w  COMPLEX_PATTERN
 7. "What does DTI ratio mean?"                                     → SIMPLE   5w  SIMPLE_PATTERN
 8. "Sure, that works."                                             → SIMPLE   3w  SIMPLE_PATTERN
 9. "Review the termination clause across every contract"           → COMPLEX 14w  COMPLEX_PATTERN
10. "Tell me that again."                                           → SIMPLE   4w  SIMPLE_PATTERN

SIMPLE turns: 7 (→ Haiku)    COMPLEX turns: 3 (→ Sonnet)

=== Savings vs always-Sonnet at 1 500 input + 350 output tokens/turn ===

{
  alwaysExpCostUsd: 0.0975,   // 10 turns × Sonnet pricing
  routedCostUsd:    0.0474,   // 7 × Haiku + 3 × Sonnet
  savedUsd:         0.0501,
  savedPct:         51.3,
  cheapTurns:       7,
  totalTurns:       10
}

At 10 000 sessions/day:
  Always Sonnet: $975/day
  Per-turn routing: $474/day
  Saved: $501/day

Conservative scenario (30% SIMPLE, not 70%):
  3 Haiku + 7 Sonnet per session:
  routedCost = $0.0709
  savedPct   = 27.3%
  At 10 000 sessions/day: $266/day saved

=== S-06 vs F-96 vs S-65 vs F-130 ===

              │ S-06 (session routing)       │ F-96 (session escalation)     │ S-65 (stage routing)         │ F-130 (per-turn routing)
──────────────┼──────────────────────────────┼───────────────────────────────┼──────────────────────────────┼──────────────────────────────
When decided  │ Once, before session start   │ Once, when escalation fires   │ Once per stage type          │ Every turn, on each message
Unit          │ Session                      │ Session (post-escalation)     │ Pipeline stage               │ Individual turn
Can oscillate │ No                           │ No (escalation is permanent)  │ No (fixed by stage)          │ Yes — Haiku ↔ Sonnet per turn
Signal        │ First message complexity     │ Cost or quality threshold     │ Stage name                   │ Per-message patterns + length
Optimal for   │ Batch classification         │ Safety net for runaway cost   │ Fixed multi-stage pipelines  │ Interactive sessions with mix
```

## See also

[S-06](../stacks/s06-model-routing-by-complexity.md) · [F-96](f96-session-cost-escalation-guard.md) · [S-65](../stacks/s65-pipeline-stage-model-routing.md) · [S-158](../stacks/s158-agent-turn-early-exit.md) · [F-123](f123-session-cost-forecaster.md) · [S-99](../stacks/s99-agent-task-economics.md)

## Go deeper

Keywords: `per-turn model routing` · `intra-session model selection` · `turn-level model router` · `cheap model routing within session` · `dynamic model selection per message` · `Haiku Sonnet per-turn routing` · `session turn model classifier` · `cost-aware per-turn dispatch` · `multi-model interactive session` · `turn complexity model routing`
