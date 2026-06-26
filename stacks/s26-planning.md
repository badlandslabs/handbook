# S-26 · Planning

The plan-and-execute pattern: for a complex goal, **decompose it into subtasks first, then execute them** — instead of one-shotting the whole thing. The fourth of the canonical agentic patterns, beside Tool Use ([S-03](s03-tool-use.md)), Reflection ([S-25](s25-reflection.md)), and Multi-Agent ([S-05](s05-multi-agent-patterns.md)). (Least-to-most: Zhou et al., 2022; ReAct: Yao et al., 2022.)

## Forces
- One-shotting a complex goal asks a single call to plan, recall, and act at once — the highest-variance way to ship it
- A focused subtask has tighter context, a sharper prompt, and can run on a cheaper model ([S-06](s06-model-routing.md))
- Static plans break when the world shifts mid-run; fully reactive plans wander off task
- Decomposition is cheap; *over*-decomposition pays a latency and debugging tax on every step
- But a single call handles more than you'd think — planning is overhead until the task actually exceeds one call

## The move
- **Pick a flavor by horizon:**
  - **Static** — plan all steps up front, then execute. Best when steps and dependencies are known.
  - **Dynamic / incremental** — plan the next step, observe, replan (ReAct, ReWOO). Best when the world changes between steps; this is the [S-19](s19-agent-loop.md) loop with an explicit plan.
  - **Least-to-most** — order subtasks easy→hard so later steps build on earlier outputs.
- **Aim for 5–10 subtasks.** Beyond that, go *hierarchical* (a plan of plans), not 50 micro-steps — each step is a round-trip and a place to fail.
- **Every subtask ships with a checkable success criterion** (schema validates, value in range, test passes — not "looks right") **and named failure modes** (retry / skip / escalate / abort). Cheapest way to cut agent incidents ([F-05](../forward-deployed/f05-agent-failure-taxonomy.md)).
- **Plan with one model, execute with another.** Planning is reasoning-heavy; execution is often slot-filling — the split is a cost lever.
- **Don't plan what a single call already does.** Reach for decomposition when one shot demonstrably drops coverage or wanders — not by default (Law 1).

**Not the same as:** [S-25](s25-reflection.md) refines *one* output; planning splits *the task*. [S-05](s05-multi-agent-patterns.md) splits *across agents*; planning splits *across steps*, often inside one model.

## Receipt
> Verified 2026-06-25 — one-shot vs. decomposed on the same tasks, same model (llama3.2 via Ollama, localhost:11435), graded by real validators. Two shapes tested.

```
A) Batch: classify 24 reviews -> {sentiment, topic, confidence} each, schema-checked
   ONE-SHOT (all 24 in one prompt): 24/24 valid    DECOMPOSED (one per call): 24/24 valid

B) Heterogeneous: 4 different extractions from one paragraph (emails, $ amounts,
   dates->ISO, phone), each token-checked
   ONE-SHOT (4 tasks, one prompt): 4/4 correct      DECOMPOSED (4 focused calls): 4/4 correct
```

The honest result: **parity** — decomposition did not beat one-shot here, and cost more calls. That is the lesson, not a failure of the pattern: a capable model handles a well-specified, moderate task in one call, so planning is pure overhead at this scale. Plan-and-execute earns its keep when the goal genuinely exceeds one call — long-horizon work where errors compound ([F-11](../forward-deployed/f11-agent-reliability.md)), tasks needing coverage guarantees across many heterogeneous steps, or where decomposition lets you route cheap steps to cheap models. Reach for it when one shot *demonstrably* drops coverage or wanders — measure first.

## See also
[S-25](s25-reflection.md) · [S-19](s19-agent-loop.md) · [S-05](s05-multi-agent-patterns.md) · [S-23](s23-workflows-vs-agents.md) · [S-06](s06-model-routing.md)

## Go deeper
Keywords: `plan-and-execute` · `task decomposition` · `least-to-most` · `ReAct` · `ReWOO` · `hierarchical task network` · `Plan-and-Solve` · `LATS` · `subtask success criteria`
