# F-18 · Architecture Sets the Cost Floor

The biggest cost decision an agent will ever make is made before it runs a single token: its topology. One call, a tool loop, or a fan-out of sub-agents — for the *same task* these differ by multiples, not percentages. [F-08](f08-agent-cost-control.md) is the runtime discipline of capping and attributing spend inside a system you've already built. This is the design-time decision that sets the floor that discipline operates above. Pick the topology by its unit economics first; tune within it second.

## Situation

You're architecting an agent, or explaining why a feature that worked in a prototype costs 4× what finance modeled. The prototype was a single call; production grew it into a multi-agent pipeline because that demoed better — and nobody priced the topology. Routing, caching, and context trimming were all on the table, but they were optimizing inside a structure whose floor was already 3–4× too high.

## Forces

- Topology multiplies cost structurally: each extra agent re-reads the shared context, each tool turn re-sends it. The multiplier is a function of *how many calls see the context*, which is a property of the design, not the prompt.
- The runtime levers in F-08 (routing, caching, context trim) move you *within* a topology's floor; they cannot move you below it. Caching a multi-agent fan-out makes the fan-out cheaper — not cheaper than the single call it replaced.
- The cheapest sufficient topology is usually less agentic than it's fun to build. A single well-prompted call beats a pipeline on most tasks; multi-agent earns its ≥2× token cost only with genuine parallel specialization ([S-05](../stacks/s05-multi-agent-patterns.md), [S-23](../stacks/s23-workflows-vs-agents.md)).
- Cost floor and capability are in tension, but not as much as intuition says: the more-expensive topology is frequently *also* worse (more surface for error propagation), so the floor and the quality argument often point the same way.
- You can only choose topology by cost if you can see the cost of each option *before* shipping — which means modeling the unit economics at design time, on real token counts, not after the invoice.

## The move

**Price the topology before you build it.** Estimate `context_tokens × calls-that-read-context` for each candidate structure on a representative task. That number, not the per-token rate, is the floor. Do this on measured token counts (run your real context through a tokenizer), not vibes.

**Default to the least agentic topology that clears the quality bar.** Start at one call. Add a tool loop only when the task genuinely needs iteration ([S-19](../stacks/s19-agent-loop.md)); add sub-agents only when subtasks are independent and parallel ([S-05](../stacks/s05-multi-agent-patterns.md)). Every step up the ladder multiplies the floor — make the task prove it needs the rung.

**Apply F-08 levers within the chosen floor, in order.** Once topology is fixed: route easy calls to small models ([S-06](../stacks/s06-model-routing.md)), cache the static context ([S-08](../stacks/s08-prompt-caching.md)), trim history ([S-13](../stacks/s13-context-engineering.md)). These are large wins — but they optimize the floor you chose, they don't change which floor you're on.

**Re-derive the floor when context grows.** A topology that was cheap at 700 context tokens is not cheap at 70,000 — the multiplier rides on context size. When the shared context inflates, the gap between topologies widens, and a structure that was fine becomes the overspend. Reprice on context changes, not just on traffic changes.

## Receipt

> Verified 2026-06-26 — Node, `gpt-tokenizer` (cl100k; counts approximate Claude within ~10–20%, and the topology *ratio* is what the argument rests on). Context is a real handbook file ([S-13](../stacks/s13-context-engineering.md), measured 741 tokens); answer text measured (74 tokens). Priced at the blended $6.07/M from the [F-08](f08-agent-cost-control.md) receipt (Q1'26). Token-per-stage structure (loop turns T=4, sub-agents N=3) is stated as the design assumption; the multiplier it produces is the result.

Same task — answer a question against a ~740-token doc — under four structures:

```
measured: context C=741 tok, question Q=15, answer A=74 tok
price: $6.07/M blended (F-08, Q1'26)

1 single call               in=  756 out= 74   $0.00504   1.00x   <- the floor
2 tool loop x4 (no cache)   in= 3024 out= 74   $0.01880   3.73x
2c tool loop x4 +cache      in= 1023 out= 74   $0.00666   1.32x
3 multi-agent x3            in= 2379 out=185   $0.01556   3.09x
```

**What the receipt shows:**

- Topology, not tuning, sets the order of magnitude. The single call and the multi-agent fan-out run the *identical task*; the fan-out costs **3.09×** because three agents each read the 741-token context.
- Caching — a within-floor F-08 lever — pulls the tool loop from **3.73× → 1.32×**. That's a real, large win. But it makes the *loop* cheaper; it never beats the 1.00× floor that choosing a single call would have given you for free.
- The multiplier is driven by the measured context size. At 70k tokens of context instead of 740, the 3.09× gap becomes a much larger absolute bill — same structure, repriced. The design decision compounds with scale.

The lesson: optimize *which* topology before you optimize *within* one. The cheapest tuned version of the wrong structure loses to the untuned version of the right one.

## See also

[F-08](f08-agent-cost-control.md) · [S-05](../stacks/s05-multi-agent-patterns.md) · [S-23](../stacks/s23-workflows-vs-agents.md) · [S-06](../stacks/s06-model-routing.md) · [S-08](../stacks/s08-prompt-caching.md)

## Go deeper

Keywords: `unit economics` · `agent topology` · `cost floor` · `multi-agent cost` · `tokens per task` · `design-time cost modeling` · `single-agent default` · `prompt caching` · `context multiplier` · `FinOps for AI`
