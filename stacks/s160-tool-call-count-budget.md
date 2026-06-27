# S-160 · Tool Call Count Budget

[S-158](s158-agent-turn-early-exit.md) exits the tool loop when the required fields are satisfied — it is a sufficiency signal. [F-88](../forward-deployed/f88-session-cost-ceiling.md) monitors cumulative dollar cost and closes the session when the dollar ceiling is reached. [F-35](../forward-deployed/f35-workflow-token-budget.md) allocates token budgets across the predefined stages of a workflow.

None of these enforce a plain count on how many tool calls an agent session may make, independent of what fields are gathered or how many tokens are spent. A count budget is the right abstraction for two specific failure modes that dollar and token ceilings catch too slowly: the agent stuck in a repetitive search loop (calling the same retrieval tool 30 times because each result fails to satisfy the model's internal quality check), and the single-turn expansion storm (the model emitting 20 parallel tool calls in one response because the problem looked broad).

A count budget requires no pricing model and no token counting. Non-technical operators understand "max 10 tool calls per session" without needing to know the model's price per million tokens. When the session budget is exhausted, the agent synthesizes an answer from whatever it has gathered. When the per-turn budget is exhausted on the current turn, the model proceeds to the answer with what it has from this turn; the remaining session budget carries to the next turn.

## Situation

A legal research agent runs on a session budget of 10 tool calls. In normal operation, it calls `search_clauses`, `get_document`, and `summarize_references` — 3–4 calls per session. It synthesizes the answer on turn 1.

A user submits an unusually broad query: "Find all dispute resolution clauses that reference the UNCITRAL rules across our entire portfolio." The model plans calls to `search_clauses` repeatedly with different query reformulations, trying to find more coverage. Without a budget, it makes 34 tool calls across 6 turns before the user gives up and closes the session. Each call injects 200–600 tokens of results into the context. Total cost: $0.51 in input tokens alone.

With a session budget of 10:
- Calls 1–10 execute.
- Before call 11, `check()` returns `allowed: false, reason: SESSION_BUDGET_EXHAUSTED`.
- The agent loop injects a system notice: `"Tool call budget reached (10/10). Synthesizing from gathered results."`
- The model produces a partial-coverage answer: "Found 18 UNCITRAL clauses across 10 documents. Portfolio coverage may be incomplete — budget limited to 10 retrieval calls."
- Total cost: under $0.15.

## Forces

- **Count budget ≠ sufficiency.** S-158 exits when the required fields are filled — it is an optimization. Count budget is a hard ceiling — it fires even if the agent is not satisfied. They compose: S-158 may exit after 2 calls; the count budget caps at 10. If S-158 never fires (the agent never gathers all required fields), the count budget catches the session at 10 calls anyway.
- **Per-turn limit prevents expansion storms.** With parallel tool calling (S-55), a single model response can emit many tool calls at once. A per-turn budget caps how many calls any single response can trigger. Set `turnBudget` to 3–5 for interactive sessions; omit it for batch workflows where the model orchestrates a planned sequence.
- **Count budget is model-agnostic.** F-88's dollar ceiling changes value when the model escalates from Haiku to Sonnet. A count budget stays constant regardless of which model is active, what the current pricing is, or how large the tool results are.
- **The partial result must be acknowledged.** When the budget fires, the agent must not return a silent empty result. Inject a system message explaining the budget and asking the model to synthesize from what it has. The model can then return a partial answer with explicit coverage caveats — far more useful than a timeout or error.
- **Budget sizes are workload-specific.** A Q&A support agent needs 2–5 calls. A research agent needs 10–20. A document processing pipeline with known tool sequences needs no count budget (just the predefined sequence). Set the budget from observed P95 call counts in production, not from first principles.
- **Pair with F-88 for full coverage.** A count budget catches runaway loops cheaply. A dollar ceiling catches edge cases where one tool call returns a 4 000-token blob and is extremely expensive. Run both: count budget as the first line of defense, dollar ceiling as the backstop.

## The move

**Set a session budget (and optionally a per-turn budget). Check before every tool call. When exhausted, inject a notice and let the model synthesize from gathered results.**

```js
// --- Tool call count budget ---
// Enforces a ceiling on tool calls per session and optionally per turn.
// Model-agnostic: no pricing knowledge required.
// check(): call before every tool invocation.
// record(): call when the tool call is approved and dispatched.
// When SESSION_BUDGET_EXHAUSTED: inject notice, route to synthesis.
// When TURN_BUDGET_EXHAUSTED: end this turn's tool loop; allow next turn.

class ToolCallBudget {
  constructor(opts = {}) {
    this._sessionBudget = opts.sessionBudget ?? 10;   // max tool calls per session
    this._turnBudget    = opts.turnBudget    ?? null;  // max tool calls per turn; null = no limit
    this._sessions      = new Map();  // sessionId → { total, turnCalls, turn }
  }

  _state(sessionId) {
    if (!this._sessions.has(sessionId)) {
      this._sessions.set(sessionId, { total: 0, turnCalls: 0, turn: null });
    }
    return this._sessions.get(sessionId);
  }

  _maybeResetTurn(state, turn) {
    if (turn !== null && turn !== state.turn) {
      state.turnCalls = 0;
      state.turn = turn;
    }
  }

  // Check whether the agent may make another tool call.
  // turn: optional turn number for per-turn enforcement.
  // Returns { allowed, reason?, sessionRemaining, turnRemaining? }
  check(sessionId, turn = null) {
    const s = this._state(sessionId);
    this._maybeResetTurn(s, turn);

    const sessionRemaining = this._sessionBudget - s.total;
    if (sessionRemaining <= 0) {
      return { allowed: false, reason: 'SESSION_BUDGET_EXHAUSTED',
               sessionRemaining: 0, totalCalls: s.total };
    }

    if (this._turnBudget !== null) {
      const turnRemaining = this._turnBudget - s.turnCalls;
      if (turnRemaining <= 0) {
        return { allowed: false, reason: 'TURN_BUDGET_EXHAUSTED',
                 sessionRemaining, turnRemaining: 0, turnCalls: s.turnCalls };
      }
      return { allowed: true, sessionRemaining, turnRemaining, totalCalls: s.total };
    }

    return { allowed: true, sessionRemaining, totalCalls: s.total };
  }

  // Record a dispatched tool call. Call after check() returns allowed: true.
  record(sessionId, turn = null) {
    const s = this._state(sessionId);
    this._maybeResetTurn(s, turn);
    s.total++;
    s.turnCalls++;
    return { totalCalls: s.total, turnCalls: s.turnCalls };
  }

  // Full status for a session.
  status(sessionId) {
    const s = this._state(sessionId);
    return {
      totalCalls:       s.total,
      sessionBudget:    this._sessionBudget,
      sessionRemaining: this._sessionBudget - s.total,
      budgetExhausted:  s.total >= this._sessionBudget,
    };
  }

  // Clear state on session end.
  clear(sessionId) { this._sessions.delete(sessionId); }
}

// --- Integration: agent tool call loop with count budget ---

const CALL_BUDGET = new ToolCallBudget({ sessionBudget: 10, turnBudget: 3 });

async function executeToolCall(sessionId, turn, toolName, toolArgs) {
  const { allowed, reason, sessionRemaining } = CALL_BUDGET.check(sessionId, turn);

  if (!allowed) {
    if (reason === 'SESSION_BUDGET_EXHAUSTED') {
      // Inject notice and route to synthesis — do not execute tool
      return {
        type: 'budget_exhausted',
        notice: 'Tool call budget reached. Synthesizing from gathered results.',
        totalCalls: CALL_BUDGET.status(sessionId).totalCalls,
      };
    }
    if (reason === 'TURN_BUDGET_EXHAUSTED') {
      // End this turn's tool loop; remaining session budget carries forward
      return { type: 'turn_budget_exhausted', sessionRemaining };
    }
  }

  CALL_BUDGET.record(sessionId, turn);
  return await dispatchToolCall(toolName, toolArgs);
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `check()` and `record()` timed over 100 000 iterations.

```
=== ToolCallBudget timing (100 000 iterations) ===

check() — within budget:   0.0003 ms
record():                  0.0004 ms

=== Scenario A: sessionBudget=10, first call ===

check('session-A'):
{ allowed: true, sessionRemaining: 10, totalCalls: 0 }

record('session-A') → status:
{ totalCalls: 1, sessionBudget: 10, sessionRemaining: 9, budgetExhausted: false }

=== Scenario B: call 10 (last allowed) ===

check('session-A'):
{ allowed: true, sessionRemaining: 1, totalCalls: 9 }

=== Scenario C: call 11 — SESSION_BUDGET_EXHAUSTED ===

check('session-A'):
{
  allowed: false,
  reason: 'SESSION_BUDGET_EXHAUSTED',
  sessionRemaining: 0,
  totalCalls: 10
}

→ Inject notice. Model synthesizes partial answer with coverage caveats.

=== Scenario D: per-turn budget=3, sessionBudget=20 ===

Turn 1: 3 calls made.
check('session-B', turn=1) — call 4:
{ allowed: false, reason: 'TURN_BUDGET_EXHAUSTED', sessionRemaining: 17, turnRemaining: 0, turnCalls: 3 }
→ End turn 1 tool loop. Proceed to synthesis for this turn.

check('session-B', turn=2) — call 1 of turn 2:
{ allowed: true, sessionRemaining: 17, turnRemaining: 3, totalCalls: 3 }
→ Turn counter reset. New turn may make up to 3 more calls.

=== Budget vs sufficiency vs dollar ceiling ===

              │ S-158 (early exit)          │ S-160 (count budget)          │ F-88 (dollar ceiling)
──────────────┼─────────────────────────────┼───────────────────────────────┼──────────────────────────────
When fires    │ Required fields gathered    │ Count ceiling reached         │ Dollar ceiling reached
Configures as │ Required field list         │ Integer (max calls)           │ Dollar amount
Model tier    │ Agnostic (fields, not cost) │ Agnostic (counts, not cost)   │ Sensitive (escalation changes $)
Catches loops │ No (loop may gather fields) │ Yes (ceiling regardless)      │ Eventually (per-dollar, slow)
Per-turn      │ No                          │ Yes (optional turnBudget)     │ No
```

## See also

[S-158](s158-agent-turn-early-exit.md) · [F-88](../forward-deployed/f88-session-cost-ceiling.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [S-55](s55-parallel-tool-calls.md) · [S-70](s70-agent-loop-termination.md) · [S-109](s109-agent-idle-cost.md)

## Go deeper

Keywords: `tool call count budget` · `agent tool call ceiling` · `per-session tool call limit` · `agent loop call cap` · `tool invocation budget` · `max tool calls per session` · `per-turn tool call limit` · `agent budget enforcement` · `tool call count ceiling` · `agent loop call count guard`
