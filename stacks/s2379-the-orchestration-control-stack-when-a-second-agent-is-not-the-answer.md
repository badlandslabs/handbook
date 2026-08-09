# S-2379 · The Orchestration Control Stack — When a Second Agent Is Not the Answer

The moment a single agent isn't cutting it, the instinct is to add another agent. Two agents. A swarm. Most teams discover too late that orchestration complexity compounds faster than capability. The real architectural decision is not which framework to use — it is where control should live.

## Forces

- **Reaching for multi-agent is the default; it shouldn't be.** A single agent with 3–5 well-scoped tools beats a three-node graph with extra latency and coordination overhead. The Reddit/r/LangChain consensus as of 2026: most teams decomposing too early.
- **37% of multi-agent failures trace to the coordination layer, not individual agents.** Specification errors, handoff confusion, and misrouted work cause more damage than any single agent falling over. The seams between agents are where systems quietly fall apart.
- **Every coordination primitive adds latency and cost.** More agents mean more LLM calls per task, more handoff overhead, and exponential growth in failure modes at each boundary.
- **The right pattern depends on where authority should live.** Sequential, router, supervisor-worker, and plan-and-execute are not interchangeable — they embody fundamentally different answers to the question: who decides what happens next?
- **Three schools have emerged.** DAG-based (LangGraph, Temporal) for explicit dependency graphs. Event-driven (Kafka + A2A + MCP) for async reactive systems. Actor model (AutoGen v0.4/MAF, Akka) for isolated state and message-passing. Each solves a different coordination problem.

## The Move

Choose an orchestration pattern by answering one question: **where does control live?**

| Pattern | Where control lives | Best when |
|---------|-------------------|-----------|
| **Sequential pipeline** | The developer (fixed order) | Task steps are fully predictable; no branching; sequential handoff adds no value |
| **Router** | The LLM at each branch point | Single classification/dispatch decision; clear routing criteria; stateless routing |
| **Supervisor-worker** | One orchestrator agent | Parallel subtasks with different tool access; centralized integration point needed; fan-out/fan-in |
| **Plan-and-execute** | Planner and executor are separate | Complex tasks needing roadmap before execution; planner can fail safely before costly execution |
| **Evaluator-optimizer** | An evaluator agent drives iteration | Quality improves with feedback cycles; writing, editing, coding tasks; no fixed end state |

**The practical decision tree:**
1. Can one agent with the right tools do this reliably? → **Sequential single-agent**. Stop.
2. Does the task need branching but no parallel work? → **Router**.
3. Does it fan out to parallel subtasks with different tool access? → **Supervisor-worker**.
4. Does it need a roadmap before committing to execution? → **Plan-and-execute**.
5. Does quality improve through iterative feedback? → **Evaluator-optimizer**.

## Evidence

- **GitHub Blog (Feb 2026):** Multi-agent workflow failures trace to missing structure — specifically, agents making implicit assumptions about state, ordering, and validation at handoff points. Their code quality system (researcher proposes changes → reviewer checks → human approves → executor ships) uses explicit handoff contracts with structured output schemas at each boundary to prevent one agent from closing an issue another just opened. — [github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/)

- **TURION.AI field note (Mar 2026):** Documented across a dozen production deployments: "Most 'multi-agent' production systems are actually supervisor + specialists." Supervisor decomposes and routes; specialists execute with targeted tools; supervisor integrates. The pattern is simple, debuggable, and effective. Teams migrating from flat multi-agent graphs to this structure consistently report reduced failure rates. — [turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)

- **Production GitHub Gist (2025):** A dual-orchestrator (Claude + Kimi) chatbot on Claude Code with 8 identified failure modes. The solution for handoff failures: persistent session memory (not context dumps), cross-model adversarial validation (one model reviewing itself is structurally insufficient), and 3-level crash recovery. Context compression at every handoff was identified as "amnesia" — losing state between agent invocations. — [gist.github.com/sigalovskinick/6cc1cef061f76b7edd198e0ebc863397](https://gist.github.com/sigalovskinick/6cc1cef061f76b7edd198e0ebc863397)

## Gotchas

- **Teams decomposing too early.** The most common mistake: reaching for multi-agent orchestration when a single agent with better-scoped tools would have been faster, cheaper, and more reliable. The coordination cost of a second agent is paid on every single task, not just hard ones.
- **Context dumps at handoffs create "Lost in the Middle."** Passing everything to the next agent buries the relevant context in the middle of the context window. Model accuracy follows a U-curve on long contexts. The fix: explicit handoff contracts with only the necessary state, not the full conversation history.
- **37% of failures are coordination-layer failures.** The seams between agents — not the agents themselves — are where to focus design effort. Every inter-agent boundary is a trust boundary that needs explicit validation, not implicit assumption.
- **Silent failures are the most dangerous failure mode.** Systems return confident, plausible answers built on broken sub-tasks. Standard monitoring misses this. The fix: evaluator/critic steps at high-stakes handoffs that fail loudly rather than proceeding on corrupted state.
