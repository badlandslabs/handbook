# S-1294 · The Orchestration Tax — When Your Multi-Agent System Is Slower and Pricier Than Your Single Agent

You've split one agent into four specialists. The routing is elegant. The topology looks like the diagram Google published. But your p95 latency jumped from 3s to 18s, and a single task now costs $6.40 instead of $0.80. This is the orchestration tax: the overhead of coordinating multiple agents that cancels out the parallelism gains you were chasing.

## Forces

- **More agents → more LLM calls → compounding cost.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. The per-token price drops don't offset the multiplication of calls. Teams that naively parallelize without modeling economics end up paying the tax on every invocation.
- **Routing and handoff overhead dwarfs execution time for simple tasks.** The coordinator's classification step, the structured-prompt handoffs, and the result aggregation add 2–5 LLM round-trips. For tasks a single agent could handle in one pass, the overhead is pure loss.
- **Topology matters more than model choice.** The AdaptOrch (2026) research showed orchestration topology delivers 12–23% gains on SWE-bench — independent of which model powers the agents. But most teams pick a framework first and let it dictate topology, which inverts the decision.
- **89% of teams have observability; 52% have evals.** The gap between monitoring what's running and measuring whether it's correct is widest in multi-agent systems, because failures cascade across agent boundaries in ways single-agent dashboards can't trace.
- **The semantic router tradeoff.** A lightweight NLU/SLM router (fast, cheap) followed by LLM fallback (expensive, accurate) saves 60–80% on routing costs. But it adds a new failure mode: misrouted requests that reach the wrong agent and produce confident wrong answers.

## The Move

Model the economics before you design the topology. Then use a minimal state machine, not a framework.

**1. Count the handoffs, not the agents.** Each agent-to-agent boundary is an LLM call, a serialization/deserialization, and a potential failure mode. Three agents in a chain beats four agents that each need to call each other. The question is how many hops are genuinely necessary, not how many specialists you can name.

**2. Route with a lightweight classifier, not an LLM.** Use an SLU/SLM (50–500M params) for intent classification before deciding whether to invoke a specialized agent or handle it in the orchestrator. Escalate to an LLM only when classifier confidence drops below threshold. Microsoft validates this as the Semantic Router with LLM Fallback pattern — it consistently reduces routing cost by 60–80% on high-volume workloads.

**3. Define schema contracts at every handoff, version them, and validate.** Untyped handoffs between agents are the leading cause of multi-agent failure in production, not model quality or tool selection. Each agent-to-agent output should be a JSON schema with a version field. Validation should fail the workflow, not fall through to the next agent.

**4. Parallelize where it breaks even, chain where it compounds.** Independent sub-tasks (scraping three sources, analyzing three datasets) can run concurrently — latency gains are real (Google's internal experiments cut processing from 1h to 10min). But sequential dependencies (analysis → decision → action) have a minimum chain depth; parallelizing them just adds handoff overhead.

**5. Instrument handoff fidelity, not just agent outputs.** Measure: does agent B receive what agent A actually produced, or what agent A said it produced? The gap between those two is where action hallucination (S-1293) lives. Log both the tool result and the agent's interpretation of it.

**6. Keep the orchestrator dumb.** The orchestrator's job is routing and state management — not reasoning. If your orchestrator needs a frontier model to decide what to do, you've created an N+1th agent problem. Use rules, thresholds, and lightweight classifiers to keep orchestration decisions fast and auditable.

## Evidence

- **Engineering blog (RaftLabs, March 2026):** "Untyped handoffs between agents kill multi-agent workflows faster than any other issue. Every agent-to-agent boundary needs a validated schema with version numbering." — [Multi-Agent Systems: Architecture Patterns for Production AI](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Ask HN thread, 11 production practitioners (~3 months ago):** Multiple experienced engineers (segmondy, hirewilliam, pablovarela) independently said they rolled their own orchestration rather than using a framework. One said: "There's absolute 0 framework out there that's good enough for serious work." — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **Research paper (AdaptOrch, 2026):** Orchestration topology delivers 12–23% gains on SWE-bench independent of model choice — topology is a first-class engineering variable, not an emergent property. Cited in [Multi-Agent AI Architecture in Production Guide](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)
- **GitHub reference (Microsoft, May 2025):** The Semantic Router with LLM Fallback pattern — lightweight NLU/SLM classifier routes high-confidence cases; LLM handles low-confidence escalation. Reduces routing LLM usage 60–80% while maintaining accuracy. — [microsoft/multi-agent-reference-architecture/Patterns.md](https://github.com/microsoft/multi-agent-reference-architecture/blob/main/docs/reference-architecture/Patterns.md)
- **Engineering benchmark (Google, ~2025):** Internal multi-agent experiments cut complex task processing from 1 hour to 10 minutes — 6× speedup from distributing work across specialized agents with coordinated orchestration. Cited in [macgpu.com production guide](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)

## Gotchas

- **A framework is not an architecture.** LangGraph, CrewAI, and AutoGen are implementation tools, not design patterns. Teams that pick a framework first and let it dictate their topology end up with whoever the framework's creator's assumptions about what a good topology looks like.
- **Serial handoffs have a minimum latency that no parallelism overcomes.** If agent B needs agent A's output, and agent A needs 5s, your pipeline takes at least 10s even with perfect parallelization of everything else. Profile the actual critical path, not just the total.
- **Schema versioning at handoffs is invisible until it breaks.** Agent A changes its output format. Agent B silently starts failing or producing wrong output. Without schema validation at every boundary, this can run for hours before it surfaces.
- **Multi-agent eval is not agent eval.** Evaluating each agent in isolation doesn't catch the failure modes that arise from handoff chains — incorrect routing, format drift, cascading hallucinations. You need end-to-end eval with realistic multi-turn traces, not unit tests per agent.
