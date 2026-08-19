# S-2795 · The ICL State Handover Stack — When Your Agent Restarts and Loses the Thread

Your agent was three hours into a complex financial analysis. Context overflow hit. The session restarted. The new instance had the conversation transcript — every message, every tool call, every result — and still produced a materially different conclusion. Nobody changed the model. Nobody changed the prompt. The thread was lost anyway.

The problem is not that the transcript was missing. The problem is that the transcript was the wrong thing to pass.

This is the **ICL state handover problem** (Kato & Kato, arXiv:2608.14528, Aug 2026): when a session hands off to a continuation — due to context overflow, application restart, or inter-agent transfer — the system must decide what to transfer. The naive answer is "everything." The correct answer is more nuanced, and the difference is measurable.

## Forces

- **A task's value is in its learned state, not its conversation history.** What matters for continuation is the ICL distribution the model built — the implicit weights it formed from the examples and evidence in context. A verbatim transcript preserves tokens, not learned state. The two diverge under context disruption.
- **Exact recovery is intuitive and wrong.** Passing the full conversation verbatim feels safe. But context overflow, model provider discontinuities, and prompt re-instantiation create distributional breaks. The new instance sees the same tokens but the ICL state doesn't survive intact.
- **Distribution preservation is correct but counterintuitive.** The right handover target is a task-relative predictive distribution — what the continuation model needs to reproduce the same class of reasoning, not the same surface tokens. Under the exogeneity condition, a coarser handover (preserving distribution) outperforms exact recovery (replaying verbatim).
- **Three handover triggers, one core problem.** Context overflow (hard limit hit), application restart (unexpected termination), and inter-agent handoff (another agent takes over) are operationally different but structurally identical: the ICL state must be reconstructed without the original context.

## The move

**Adopt the three-part ICL handover record.** Rather than passing a transcript, compose a structured handover document in three layers:

```
1. Decisions + Constraints (exact)
   → What the agent decided, what constraints it operated under
   → Stored verbatim. Transfer verbatim. Non-negotiable.
   
2. Task-Justified Evidence (summary)
   → Repeated reasoning patterns, statistics, evidence summaries
   → The ICL "weights" — what the model learned from the evidence
   → Summarized, not transcribed. The continuation model re-derives from summary.
   
3. Oriented Representations (abstract)
   → Concept activation patterns, learned abstractions
   → Transfer the shape of the learned state, not the examples that induced it
```

**The exogeneity principle.** When the continuation's model is trained on ICL (virtually all modern LLMs), the coarsest deterministic sufficient handover — the minimum record that preserves predictive equivalence — outperforms verbatim recovery. Less exact data, better outcomes.

**Implement the ICL-state checkpoint gate.** Before any session termination:

```
BEFORE session end:
  1. Extract ICL state from current context (decisions + summary + representations)
  2. Verify exogeneity condition: does continuation task depend on prior context?
  3. If YES: write three-part record to durable store
  4. If NO: skip handover (no predictive dependency)
  5. New session: reconstruct ICL state from record before processing

NOT: dump full conversation → continuation parses transcript
YES: structured state → continuation resumes learned distribution
```

**Distribution preservation check.** After handover, verify the continuation produces statistically equivalent outputs on a held-out slice of the task. If it diverges significantly, the handover record was too coarse — add layer 2 statistics.

## Receipt

> Verified 2026-08-17 — Kato & Kato (arXiv:2608.14528, Aug 14 2026, University of Tokyo / RIKEN AIP): formalized session handover as ICL state transfer. Key theorems: under exogeneity, coarsest deterministic sufficient handover = optimal; exact recovery ≠ distribution preservation. Three-part record concept verified against 1,200 handover scenarios. Production implication: transcript-passing is the dominant pattern but demonstrably suboptimal. The Continual Learning Bench (arXiv:2606.05661, Jun 2026) independently confirms: dedicated memory systems outperform naive ICL, and naive ICL outperforms stateless. ICL state handover is the missing protocol between them.

## See also

- [S-1909 · The Reasoning Store Becomes the Attack Surface](s1909-the-reasoning-store-becomes-the-attack-surface-when-your-agent-remembers-a-decision-it-never-made.md) — handover records are attack surfaces; provenance tagging applies here too
- [S-1020 · The Tiered Memory Stack](s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — tiered memory provides the store; this entry provides the protocol
- [S-3353 · The Context Drift Stack](s3353-the-context-drift-stack-when-your-multi-agent-system-hallucinates-but-no-model-is-broken.md) — drift is what happens without handover; ICL handover is the explicit correction
