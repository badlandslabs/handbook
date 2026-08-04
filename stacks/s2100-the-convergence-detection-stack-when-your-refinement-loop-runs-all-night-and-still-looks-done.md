# S-2100 · The Convergence Detection Stack — When Your Refinement Loop Runs All Night and Still Looks Done

Your agent iterated on a spec for 23 passes. Each one looked slightly different from the last. The agent never declared failure — it just kept polishing. By pass 20, adjacent drafts were 97% semantically identical. The work had converged. The agent didn't know it. This is the convergence detection problem: refinement loops have no natural stopping point, and the model won't volunteer that it's done.

## Forces

- **"It looks good enough" is not a stopping criterion.** Without a machine-checkable gate, you either over-refine (burn tokens on diminishing returns) or under-refine (ship before the work stabilizes). Neither is a good default.
- **Change detection requires more than "is the output the same."** String equality fails on reformatting. Token count fails on compression artifacts. You need a semantic signal — what's the *meaningful distance* between two drafts?
- **All three signals must converge.** A loop that stops on change velocity alone will exit early when the agent makes one big conceptual leap. One that stops on size alone will exit early when the agent rewrites verbosely. All three must agree.
- **Thresholds are domain-dependent.** Code converges at different edit-velocity than prose or design docs. The pattern is the structure; the thresholds are tuned per task type.

## The move

**Measure three signals across consecutive refinement passes. Stop only when all three have converged.**

### Signal 1 — Change Velocity

Track the rate of edits between adjacent drafts. Compute as:

```
delta = semantic_diff(draft_n, draft_n_plus_1)  # embeddings cosine distance, or LLM-judged diff fraction
velocity[n] = delta
```

Converging: velocity drops below threshold (e.g., <5% meaningful change over 3 consecutive passes).
Diverging: velocity stays high — keep going.

### Signal 2 — Output Size

Track normalized size (token or character count) across passes.

Converging: size stabilizes within ±10% across 3 consecutive passes.
Diverging: size keeps growing — scope creep, not refinement. Flag or reject.

### Signal 3 — Content Similarity

```
similarity[n] = cosine_sim(embed(draft_n), embed(draft_n_plus_1))
```

Converging: similarity > 0.95 across 3 consecutive passes (drafts are nearly identical in meaning).
Diverging: similarity stays low — the agent is still making substantive changes.

### Stop Rule

```python
def should_stop(history):
    velocity_converged = consecutive_below(velocity, threshold=0.05, n=3)
    size_converged     = consecutive_within(size, tolerance=0.10, n=3)
    similarity_converged = consecutive_above(similarity, threshold=0.95, n=3)
    return velocity_converged and size_converged and similarity_converged
```

Return `best_draft(history)` — the last convergent draft, not the last draft. On non-convergence, cap at `max_passes` (typically 10–20 for prose/specs, 5–10 for code).

### Budget Layer (belt and suspenders)

Even with convergence detection, set hard caps:
- `max_passes`: absolute ceiling (prevents pathological cases)
- `max_tokens`: token budget across all passes
- `max_time`: wall-clock time limit

```python
def refine_loop(agent, task, max_passes=15, max_tokens=100_000):
    drafts = []
    for i in range(max_passes):
        draft = agent.refine(drafts[-1] if drafts else task)
        drafts.append(draft)
        if should_stop(drafts[-3:]) or token_count(drafts) > max_tokens:
            return best_draft(drafts)
    return best_draft(drafts)
```

## Receipt

> Verified 2026-08-04 — Pattern sourced from agentpatterns.ai (Loop Engineering, Convergence Detection, updated 2026-06-14), Agent Native (Agent Loop Termination Pattern, updated 2026-07-26), and scalable-system.dev (Agentic Loops & Termination). Core stop rule logic implemented above as Python pseudocode. Three-signal thresholds (velocity <5%, size ±10%, similarity >0.95) align with published practitioner guidance. Production validation: pattern has been adopted in evaluator-optimizer workflows per agentpatterns.ai maturity tag.

## See also

- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — general scaffold infrastructure for no-progress detection and budget guards
- [S-1003 · The Agent Failure Recovery Stack](/stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — loop detection and graceful failure when convergence never arrives
- [R-18 · Why Agents Fail to Stop](/frontier/r18-why-agents-fail-to-stop-infinite-agentic-loops.md) — taxonomy of infinite agentic loop failure types and IAL-Scan detection
