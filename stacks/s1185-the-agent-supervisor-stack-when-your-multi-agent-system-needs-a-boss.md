# S-1185 · The Agent Supervisor Stack — When Your Multi-Agent System Needs a Boss

You have three specialized agents: a researcher, a writer, and a code reviewer. Each does its job well. The problem is nobody decides which one goes first, what they pass between them, or what happens when the researcher's output is too verbose for the writer to use. You get a system that technically works but produces unpredictable handoffs, redundant work, and output nobody can audit. This is not a prompting problem. It is a governance problem — and the standard fix is a supervisor agent that sits above the workers and routes everything.

## Forces

- **More agents mean more coordination surface area.** Each additional agent doubles the number of potential handoffs and failure points. Without a governing layer, a system of N agents degrades into N×(N-1)/2 unmanaged connections.
- **The supervisor itself becomes a bottleneck.** Every task routes through it, consuming its context window and adding latency. The cure can become as painful as the disease if the supervisor isn't scoped carefully.
- **Scope creep kills supervisors.** A supervisor given too many responsibilities (routing + verification + recovery + escalation) becomes the most fragile component in the system.
- **Not every system needs a supervisor.** A well-scoped single agent with the right tools often outperforms a multi-agent system with a supervisor. The supervisor pattern is a governance solution, not a capability solution.

## The move

**Use a supervisor agent to own routing, handoff contracts, and escalation — nothing else.**

The supervisor pattern (also called the "orchestrator-worker" or "router" pattern) places one agent in charge of dispatching tasks to specialized workers and assembling results. Workers never talk to each other directly; they report back to the supervisor, which decides the next step.

- **One supervisor, 3–7 workers maximum.** Research on human supervisory teams maps to agents: beyond ~7 workers, the supervisor's routing accuracy degrades. If you need more, cluster workers into teams with sub-supervisors.
- **Workers report structured output, not freeform text.** Define a strict schema for worker responses (status, findings, confidence, next_needed). Freeform text forces the supervisor to parse and extract, which is slow and error-prone.
- **Summarize worker outputs before supervisor re-injects them.** Long worker outputs drain the supervisor's context window fast. A one-paragraph summary of findings is far more useful than the full transcript.
- **The supervisor routes; it does not execute.** If the supervisor also runs tools, it becomes a single-point-of-contention. Keep it as a pure routing and decision-making layer.
- **Hardcode escalation triggers, don't trust the supervisor to self-flag.** Define explicit conditions: "if confidence < 0.7, escalate to human review" or "if task exceeds 5 sub-steps, pause and report." Don't rely on the supervisor to recognize its own limits.
- **Two-level hierarchy for complex domains.** When more than 5-7 workers are needed, create sub-supervisors. Each sub-supervisor owns a domain cluster and reports to the top-level supervisor. This mirrors how large engineering organizations are structured.

## Evidence

- **Hacker News discussion on Anthropic's "Building Effective AI Agents":** Anthropic recommends starting with the simplest solution (single LLM + retrieval) and only escalating to agents + orchestration when simpler approaches fail. Their own engineering guide distinguishes "workflows" (predefined code paths) from true "agents" (dynamically self-directing). HN commenters debate this, with simonw noting that "agents = augmented LLM running in a loop" — a definition that highlights the loop's dependency on external state management. — [HN Thread](https://news.ycombinator.com/item?id=44301809) | [Anthropic Engineering](https://www.anthropic.com/engineering/building-effective-agents)
- **Langfuse framework comparison (July 2026):** Maps ecosystem-specific frameworks to their orchestration models: LangGraph (graph-based stateful workflows), OpenAI Agents SDK (supervisor/handoff primitives), CrewAI (role-based multi-agent teams), Claude Agent SDK, Google ADK. Each framework encodes a specific opinion about how supervisors and workers should interact. The comparison notes LangGraph's strength is explicit control and durable execution via checkpointing. — [Langfuse Blog](https://langfuse.com/blog/2025-03-19-ai-agent-comparison)
- **Tamas Piros, "Multi-Agent Systems and Task Handoff" (June 2025):** Frames the supervisor pattern through the hotel concierge analogy: a concierge who also cooks dinner and makes beds is a bottleneck. Multi-agent systems enable specialization, context separation, and controlled handoffs. Piros outlines the three handoff primitives: sequential (A→B→C), parallel (A||B→C), and conditional (if X then A else B). — [tpiros.dev](https://tpiros.dev/blog/multi-agent-systems-and-task-handoff/)
- **AI Agent Glossary (Jahanzaib):** Documents the two core supervisor gotchas: supervisor bottleneck (mitigated by stateless design + output summarization) and supervisor confusion with >7 workers (mitigated by hierarchical sub-supervisor clustering). Notes this pattern is natively supported in LangGraph and OpenAI Agents SDK. — [jahanzaib.ai](https://www.jahanzaib.ai/glossary/supervisor-pattern)
- **Solutelabs CTO post on multi-agent architecture (April 2026):** Reports from production: "agents got stuck in loops. In another, they overwrote each other's work." Key rule: add agents only when you need clear specialization, context separation, parallel execution, permission boundaries, or maker-checker validation. Common mistake is splitting agents without a coordination contract. — [Solutelabs](https://www.solutelabs.com/blog/multi-agent-ai-system)

## Gotchas

- **A supervisor with a verbose system prompt will route slowly.** Keep the supervisor's own context lean — it needs to hold the routing logic and task state, not the domain knowledge. Push knowledge into workers.
- **Structured output sounds simple but requires schema discipline.** If workers return inconsistent schemas, the supervisor spends more time handling format errors than routing. Invest in schema validation at the worker level.
- **The supervisor's routing accuracy degrades silently.** Unlike a crashed service, a confused supervisor doesn't fail loudly — it makes subtly wrong routing decisions that compound. Log every routing decision and audit them periodically.
- **Parallel workers can race to write shared state.** If two workers write to the same memory or document, the last-write-wins behavior will silently corrupt results. Use lock mechanisms or dedicated output slots per worker.
- **Human escalation is a UX problem as much as a technical one.** If the escalation path requires a human to re-read the entire agent context, nobody will actually review it. Build concise escalation briefs that fit in a single screen.
