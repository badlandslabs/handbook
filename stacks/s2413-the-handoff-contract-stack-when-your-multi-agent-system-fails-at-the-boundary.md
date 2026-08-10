# S-2413 · The Handoff Contract Stack — When Your Multi-Agent System Fails at the Boundary

Your multi-agent pipeline looks correct on paper. The supervisor decomposes tasks, specialists execute, outputs flow between agents. But at 3am you discover: the researcher and writer have subtly different interpretations of what "findings" means; the handoff between agents silently drops half the context; an agent confidently produces wrong output that the verifier doesn't catch because the contract never specified what "validated" meant. The failure is never inside an agent — it's always at the boundary between them.

## Forces

- **Every inter-agent handoff is an implicit API call.** Most teams build multi-agent systems with loosely shaped calls — free-form text plans, charitable interpretation of natural language outputs. This works in dev, collapses in production.
- **Reliability degrades multiplicatively, not additively.** At 95% reliability per step: 10 steps → 60% success; 20 steps → 36%; 100 steps → 0.6%. The UC Berkeley MAST study found multi-agent systems fail at 41–86.7% in production — and "obvious" interventions only close ~14% of that gap.
- **Debugging inter-agent failures requires tracing across boundaries.** Individual agent prompts look fine. The bug lives in what crosses the boundary — a dropped field, a misinterpreted role, an unstated assumption about what "done" means.
- **Adding more agents doesn't add reliability.** The MAST paper found that most multi-agent frameworks often perform no better than single-agent systems on benchmarks like ChatDev (~33%).

## The Move

The fix is treating inter-agent boundaries as first-class engineering contracts — explicit, typed, validated, versioned. The pattern:

- **Name the handoff explicitly.** Instead of "Agent A produces output, Agent B consumes it," define a schema: what fields, what types, what required vs. optional, what the receiver needs to trust vs. re-verify. Document it in code, not just a system prompt.
- **Validate at the boundary, not inside agents.** A schema validator at each handoff catches bad outputs before they propagate. This is cheaper than an agent catching it downstream — errors compound once they enter a new agent's context.
- **Make handoff failures loud and recoverable.** A failed handoff contract should: (a) surface immediately (structured error, not silent drop), (b) retry with reduced context, (c) escalate to human-in-the-loop after N retries rather than continuing with corrupted state.
- **Separate handoff state from agent state.** Pass structured handoff objects (JSON/dict with typed fields) rather than appending to chat history. Chat history is for conversation; handoff objects are for workflow state. Mixing them makes replay and debugging nearly impossible.
- **Use a supervisor to own handoff routing.** The supervisor's job isn't just decomposing tasks — it's owning the handoff contracts: routing to the right specialist, validating the output against the contract, and deciding retry/escalate. This concentrates the coordination logic in one place instead of scattering it across agents.
- **Test the handoff in isolation.** Before testing the full pipeline, write unit tests that: (a) pass valid inputs through each handoff, (b) pass malformed inputs and verify rejection, (c) simulate one agent returning bad output and verify the downstream behavior is defined.

## Evidence

- **arXiv paper (UC Berkeley, NeurIPS 2025):** MAST study analyzed 1,600+ annotated execution traces across 7 multi-agent frameworks and identified 14 failure modes in 3 categories: specification ambiguity, coordination breakdowns, and verification gaps. Found multi-agent systems often perform no better than single-agent; best-effort interventions yielded only +14% improvement for ChatDev. — [arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)
- **Engineering blog (EskiLab, July 2026):** "Most multi-agent failures don't happen inside an individual agent's reasoning — they happen at the handoff, the moment one agent passes control, context, or a partial result to another." Empirically identifies handoff contracts as the single highest-leverage improvement. — [eskilab.com](https://eskilab.com/multi-agent-handoff-design-coordination-patterns-for-production-ai-systems/)
- **Engineering blog (xlabs, 2026):** Six production failure modes, with "implicit hand-off contracts" as #1. Quote: "Multi-agent orchestration is not a model problem — it is an engineering problem." Documents explicit schema validation, structured handoff objects, and supervisor-owned routing as the engineering response. — [xlabs.co.za](https://www.xlabs.co.za/blog/multi-agent-orchestration-what-breaks)
- **arXiv incident response paper (Philip Drammeh, 2511.15755, Nov 2025):** 348 controlled trials comparing single vs. multi-agent LLM orchestration for incident response. Single-agent actionable recommendations: 1.7%. Multi-agent: 100%. Demonstrates that structured multi-agent coordination with explicit role contracts produces 80× more actionable outputs in mission-critical domains. — [arxiv.org/abs/2511.15755](https://arxiv.org/abs/2511.15755)
- **Ask HN practitioner thread (HN, 2025):** Practitioners sharing real stacks — Swrl described a "swarm" pattern with agent/swirL/scoped memory layers; others use LangGraph supervisor + structured state objects; the consensus from 11 HN commenters was that the hardest part is state management across handoffs, not model selection. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **Don't use chat history as your handoff mechanism.** Append-and-pass is the most common pattern in tutorials. In production, it's the fastest path to context window bloat, silent drops, and unreproducible traces. Structured objects with typed fields survive longer than prose in a context window.
- **Don't assume the receiver will re-validate.** Agents trust their inputs. A supervisor that says "I'm the synthesizer, I'll catch errors" will often synthesize the error instead of catching it. Validate at the source, not at the sink.
- **Don't scale agents to fix reliability.** Adding a second researcher to catch the first researcher's mistakes sounds logical. In practice, it creates coordination overhead, shared-nothing drift, and doubled cost with sublinear reliability gains. The MAST paper's data supports this: framework topology changes (more agents) don't close the failure gap — better handoff contracts do.
- **Don't skip replayability.** If a pipeline fails at step 7 of 20, can you replay from step 7 with the same state? Without checkpointing at handoff boundaries, you restart from scratch. With structured handoff objects persisted to a store, you can replay any slice.
