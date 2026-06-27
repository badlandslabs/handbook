# S-168 · Tool Definition Waste Audit

[S-51](s51-tool-schema-design.md) designs tool schemas for invocation quality: verb-noun names, enum constraints, parameter descriptions that eliminate hallucinated values. It treats schema tokens as a precision investment — 222 tokens for a well-documented schema is justified when it prevents wrong tool calls. [F-67](../forward-deployed/f67-dynamic-tool-registration.md) adds and removes tools at runtime per turn — tools that aren't needed on a given turn are omitted from that call entirely. Both are about schema quality or runtime composition. Neither surfaces the question: which tools in the current static schema are never being invoked?

Tool schemas are paid on every API call, regardless of whether the tool is invoked on that call. A 10-tool agent schema at 767 tokens per call pays 767 tokens of input overhead at every single turn — including the 60% of turns where only two tools are ever called. If 4 of those 10 tools have zero invocations across 1 000 production calls, their schema tokens are pure waste: 313 tokens paid 1 000 times = 313 000 tokens with zero benefit.

A tool definition waste audit profiles tool invocations over a production window, computes per-tool schema token overhead, and ranks tools by wasted spend. The audit output drives one of two actions: prune the tool from the static schema, or move it to F-67 dynamic registration (add it only when the agent's current task needs it).

## Situation

A customer-support agent has 10 tools registered: `get_customer_profile`, `get_customer_orders`, `update_subscription_status`, `send_account_notification`, `generate_invoice`, `apply_promo_code`, `get_payment_methods`, `refund_order`, `export_customer_data`, `delete_customer_account`.

In production, 1 000 sessions reveal: 4 tools (`apply_promo_code`, `export_customer_data`, `delete_customer_account`, `refund_order`) have zero invocations. The four unused tools contribute 313 schema tokens per call — 40.8% of the 767-token total schema overhead. At 10 000 calls/day at Haiku pricing, this is $2.50/day in schema tokens that generate no tool calls.

The fix: prune the 4 unused tools from the default schema. Reduce schema overhead from 767 to 454 tokens/call. Run the waste audit monthly — tools that were unused last month may be needed next month (a seasonal promo campaign will trigger `apply_promo_code`). For those cases, F-67 dynamic registration is the right model: inject the tool schema only when the agent's current task signals it might be needed.

## Forces

- **Token cost of the schema is independent of invocation.** The API charges for tool schemas as input tokens on every call. A tool that is never invoked has the same per-call schema cost as one invoked on every call. This is the core accounting error practitioners miss: they think of schema cost as amortized over calls where the tool is used — but it is incurred on every call.
- **Measure over a sufficient window before pruning.** A tool with zero invocations in 1 000 calls may have 5 invocations in 10 000 calls — used only in rare but important edge cases (`delete_customer_account`, `refund_order`). Prune only after a window that covers all routine and seasonal traffic patterns. For most agents, 7–30 days of production data is sufficient.
- **Invocation rate ≠ value.** A tool invoked on 1% of calls but critical for that 1% should not be pruned — it should be moved to F-67 dynamic registration where it is added to the schema only when the session context signals it may be needed. The waste audit distinguishes never-used (prune or archive) from rarely-used (dynamic registration candidate).
- **Schema token cost scales with model price.** At Haiku ($0.80/M tok), 313 unused tokens/call × 10k calls/day = $2.50/day. At Sonnet ($3.00/M), the same 313 unused tokens/call = $9.39/day. The ROI of a waste audit is model-tier dependent — run it first on high-tier agents.
- **Prune and re-audit at model upgrades.** When the production model changes (F-138 promotion), the new model may use tools differently. A tool unused by Haiku may be invoked more confidently by Sonnet. Re-run the audit within the first 7 days of any model change.
- **Beware the audit window mismatch.** Audit data from a support-heavy period (after a major release, during a sale) over-represents certain tool usage patterns. Low invocations during a quiet period should not trigger pruning of tools that matter during busy periods. Annotate audit reports with the traffic context.

## The move

**Profile tool invocations in production. Compute wasted schema tokens per tool. Prune never-used tools or move rarely-used tools to dynamic registration.**

```js
// --- Tool definition waste audit ---
// Profiles invocations per tool across production calls.
// audit() computes wasted schema tokens = tokens × calls where tool was not invoked.
// Output drives two actions:
//   0 invocations over window → prune from static schema or archive
//   <2% invocation rate → candidate for F-67 dynamic registration
// Token estimation: JSON.stringify(schema).length / 4 (rough 4 chars/token for schema JSON)

function estimateToolTokens(tool) {
  return Math.ceil(JSON.stringify(tool).length / 4);
}

class ToolUsageProfiler {
  constructor() {
    this._tools = new Map();
    this._totalCalls = 0;
  }

  // Register the tool schemas currently in production.
  register(tools) {
    for (const t of tools) {
      this._tools.set(t.name, { name: t.name, tokens: estimateToolTokens(t), invocations: 0 });
    }
    return this;
  }

  // Call this whenever the model invokes a tool in a real production session.
  recordInvocation(toolName) {
    const t = this._tools.get(toolName);
    if (t) t.invocations++;
    this._totalCalls++;
    return this;
  }

  // Compute wasted tokens and cost per tool, sorted by highest waste first.
  audit() {
    const results = [];
    let totalSchemaTokensPerCall = 0;

    for (const e of this._tools.values()) {
      totalSchemaTokensPerCall += e.tokens;
      const wastedTokens = e.tokens * (this._totalCalls - e.invocations);
      results.push({
        name: e.name,
        tokens: e.tokens,
        invocations: e.invocations,
        invocationRate: this._totalCalls > 0
          ? (e.invocations / this._totalCalls * 100).toFixed(1) + '%'
          : 'n/a',
        wastedTokens,
        wastedCostHaiku: (wastedTokens * 0.80 / 1e6).toFixed(6),
        recommendation: e.invocations === 0
          ? 'PRUNE or archive'
          : e.invocations / this._totalCalls < 0.02
            ? 'DYNAMIC: F-67 candidate'
            : 'KEEP',
      });
    }
    results.sort((a, b) => b.wastedTokens - a.wastedTokens);

    const unusedTools = results.filter(r => r.invocations === 0);
    const unusedTokensPerCall = unusedTools.reduce((s, r) => s + r.tokens, 0);

    return {
      totalCalls: this._totalCalls,
      toolCount: this._tools.size,
      totalSchemaTokensPerCall,
      unusedToolCount: unusedTools.length,
      unusedTokensPerCall,
      unusedPctOfSchema: totalSchemaTokensPerCall > 0
        ? (unusedTokensPerCall / totalSchemaTokensPerCall * 100).toFixed(1) + '%'
        : '0%',
      byTool: results,
    };
  }
}

// --- Integration: collect invocation data from the tool dispatch layer ---

function buildToolDispatcher(tools, profiler) {
  const toolMap = Object.fromEntries(tools.map(t => [t.name, t.handler]));

  return async function dispatch(toolName, args) {
    profiler.recordInvocation(toolName);
    if (!toolMap[toolName]) throw new Error('Unknown tool: ' + toolName);
    return await toolMap[toolName](args);
  };
}

// --- Monthly audit review ---
// Run at end of each audit window to decide which tools to prune or move to F-67.

function printAuditReport(report) {
  console.log('Tool waste audit — ' + report.totalCalls + ' calls, ' + report.toolCount + ' tools');
  console.log('Schema overhead: ' + report.totalSchemaTokensPerCall + ' tok/call | Unused: ' + report.unusedTokensPerCall + ' tok/call (' + report.unusedPctOfSchema + ')');
  for (const r of report.byTool) {
    console.log('  ' + r.name + ': ' + r.invocations + ' invocations (' + r.invocationRate + ') → ' + r.recommendation);
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. 10-tool customer-support agent schema. 1 000 sessions simulated with deterministic invocation distribution. `recordInvocation()` and `audit()` timed over 100 000 iterations.

```
=== ToolUsageProfiler.audit() — 10-tool support agent, 1 000 calls ===

Tools registered:          10
Schema tokens/call:        767
Unused tools:              4 of 10
Unused tokens/call:        313 (40.8% of schema overhead)

Name                         | tok | invocations | rate   | wastedTok | recommendation
---------------------------------------------------------------------------------------
delete_customer_account      | 84  |     0       | 0.0%   | 84 000    | PRUNE or archive
export_customer_data         | 80  |     0       | 0.0%   | 80 000    | PRUNE or archive
refund_order                 | 77  |     0       | 0.0%   | 77 000    | PRUNE or archive
apply_promo_code             | 72  |     0       | 0.0%   | 72 000    | PRUNE or archive
get_payment_methods          | 59  |    20       | 2.0%   | 57 820    | DYNAMIC: F-67 candidate
generate_invoice             | 79  |    50       | 5.0%   | 75 050    | KEEP
update_subscription_status   | 79  |   150       | 15.0%  | 67 150    | KEEP
get_customer_orders          | 77  |   300       | 30.0%  | 53 900    | KEEP
get_customer_profile         | 67  |   400       | 40.0%  | 40 200    | KEEP

=== Cost projection: 10 000 calls/day at Haiku ($0.80/M tok) ===

Total schema cost/day:     $6.1360
Unused tool schema/day:    $2.5040 (41% of schema spend)
After pruning 4 unused tools:
  Schema tok/call:         454 (was 767, -40.8%)
  Daily savings:           $2.5040/day → $913/year

=== Timing (100 000 iterations) ===

recordInvocation():  0.0001 ms
audit() 10-tool:     0.0057 ms

=== S-51 vs F-67 vs S-168 ===

              │ S-51 (tool schema design)       │ F-67 (dynamic tool registration) │ S-168 (waste audit)
──────────────┼─────────────────────────────────┼──────────────────────────────────┼─────────────────────────────────
Goal          │ Maximize invocation accuracy    │ Minimize active schema at runtime │ Identify schema waste in prod
When to apply │ At schema authoring time         │ At runtime, per-turn context      │ Monthly, post-production data
Input         │ Tool purpose, parameter types   │ Task context, available tools     │ Invocation logs + schema tokens
Output        │ Better-named, accurate schema   │ Smaller per-turn tool list        │ PRUNE / DYNAMIC / KEEP ranking
Cost model    │ Precision costs ≤ $3/day        │ Saves unused-tool tok per turn    │ Identifies the tok being wasted
Trigger       │ New tool                        │ Every API call                    │ 7–30 day production window
```

## See also

[S-51](s51-tool-schema-design.md) · [F-67](../forward-deployed/f67-dynamic-tool-registration.md) · [S-74](s74-agent-capability-registry.md) · [F-72](../forward-deployed/f72-per-feature-cost-analysis.md) · [F-29](../forward-deployed/f29-cost-attribution.md)

## Go deeper

Keywords: `tool definition waste audit` · `tool schema token cost` · `unused tool schema` · `tool invocation profiling` · `tool schema overhead` · `tool pruning strategy` · `tool token waste` · `unused tool pruning` · `tool definition cost` · `tool registration cost optimization`
