# S-41 · Agent Handoff Patterns

Every handoff between agents is a compression decision. What you pass determines what the next agent can do. Pass too much and you pay for noise; pass too little and rationale evaporates — and in multi-step pipelines, the loss compounds at each stage.

## Situation

A research agent completes its work and must pass findings to an execution agent. The naive approach is to forward the entire conversation history. A tighter approach is to pass only the final answer. Neither is right. The full history carries tool-call noise and exploratory detours; the answer alone drops the "why," and a downstream agent that can't explain a recommendation will either hallucinate a justification or fail silently when challenged.

## Forces

- Context is finite and costs money. Passing conversation history from one agent to the next pays full input price *twice* — for every token the next agent never needed to see. At N-hop chains this multiplies.
- Rationale is the minimum viable context for any downstream decision. An agent that only receives "use TimescaleDB" cannot respond correctly when asked why, cannot evaluate if that decision is still valid given new constraints, and cannot flag risks it wasn't told about.
- Noise amplifies errors across hops. A factual error in turn 3 of an 8-turn conversation may be corrected by turn 6. If the next agent receives only the final answer, it inherits the corrected fact. If it receives the full history, it may weight the earlier wrong turn and re-introduce the error. This is a documented failure mode: partial context creates false confidence ([S-29](s29-false-consensus.md)).
- The handoff contract is the API between agents. Unstructured prose handoffs create invisible coupling — the next agent must parse intent from language instead of reading a typed object. Structured handoffs make the contract explicit and testable ([F-19](../forward-deployed/f19-agent-testing-strategies.md)).
- Not all handoffs are equal. A pipeline where agent B takes agent A's output as input is different from one where agent A explicitly delegates mid-task to agent B (scope change) or where a long-running agent checkpoints and resumes ([F-15](../forward-deployed/f15-durable-execution.md)). Each has a different handoff shape.

## The move

**Use a structured handoff object as the default.** It is 2.5× cheaper than passing full history and preserves everything the next agent needs to act and defend.

Minimum schema:
```js
{
  task:               "string — original goal",
  status:             "complete | partial | blocked",
  result:             "...",          // the answer or artifact
  rationale:          ["why this", "not that"],
  considered_and_rejected: [
    { option: "...", reason: "..." }
  ],
  risks:              ["list of live risks next agent should know"],
  next_steps:         ["what the receiving agent should do"],
  open_questions:     []              // unresolved items, empty if none
}
```

Serialize this as the last message of the outgoing agent's turn, then inject it as the first system or user message in the receiving agent's context.

**What to drop when compressing from full history:**
- Exploratory turns where no conclusion was reached
- Tool-call raw output (keep only the extracted conclusion)
- Retry attempts and error recovery paths
- Acknowledgment turns ("Ok, proceeding…")

**What to always keep:**
- The original goal and any constraints given
- The decision *and* the rationale behind it
- Alternatives that were considered and why they were rejected
- Known risks the next agent might need to respond to
- Explicit next steps (not implicit — spell them out)

**Result-only is acceptable only when:**
- The receiving stage is formatting/delivery (it doesn't need to defend the decision)
- The pipeline has a single hop (no downstream agent will be challenged to explain)
- The result is verifiable without context (executable code, a file, a database row)

**Multi-hop chains: carry rationale forward, don't regenerate it.** In a 3-hop pipeline where hop 1 makes a decision and hop 3 must explain it, forcing hop 3 to re-derive rationale from only the result creates both cost (re-inference) and drift (different model, different reasoning path, potentially different answer). Pass the rationale forward through each hop.

**Name the handoff type.** In the `status` field, distinguish:
- `complete` — task done, result is ready, next agent should proceed
- `partial` — partial result; `next_steps` explains what remains
- `blocked` — cannot proceed without information in `open_questions`; do not continue the pipeline silently

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`, same task context passed three ways. Token counts are real; the failure mode referenced (name without context → wrong prize field) matches a result described in [S-05](s05-multi-agent-patterns.md) receipt.

```
=== Agent handoff strategy: token cost comparison ===
(8-turn research task: database selection, 3 tool calls, final synthesis)

Strategy                     tokens    $/1k-calls    info-preserved
Full history dump               673      $4.09       all context + noise + retries
Structured handoff object       264      $1.60       decision + rationale + risks + next
Result only                      23      $0.14       answer only; rationale lost

Full history vs structured:  2.5× more tokens for same decision content
Structured vs result only:  11.5× more tokens; preserves defensible rationale

Lost at result-only:
  - Next agent cannot defend recommendation under challenge
  - Next agent cannot check if risks apply to new constraints
  - Rejected alternatives may be re-proposed at downstream stages
```

The 11.5× cost gap between structured and result-only is real, but the right question is not "which is cheaper" — it is "what can the next agent do with each." Result-only is correct exactly when the next stage doesn't need to reason about the decision.

## See also

[S-05](s05-multi-agent-patterns.md) · [S-21](s21-context-compaction.md) · [S-38](s38-agent-state-design.md) · [F-15](../forward-deployed/f15-durable-execution.md) · [S-29](s29-false-consensus.md)

## Go deeper

Keywords: `agent handoff` · `context passing` · `inter-agent protocol` · `pipeline composition` · `context compression` · `handoff schema` · `multi-hop agents` · `delegation`
