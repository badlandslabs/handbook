# S-1055 · The Pattern Ladder Stack — When You're About to Build a Swarm and a Pipeline Would've Done

You built a three-agent swarm with dynamic handoffs and peer-to-peer negotiation. It works beautifully in the demo. Six months later you can't trace a bug across the system, an agent looped 200 times on a simple task, and the new engineer on the team spent three weeks just reading the orchestration layer. The problem isn't the agents — it's the pattern. Six orchestration patterns cover 90% of production use cases, and most teams jump to multi-agent before exhausting what a sequential chain can do.

## Forces

- **Multi-agent complexity compounds super-linearly, not linearly.** Five agents create ten pairwise interaction channels; ten agents create forty-five. Debugging, monitoring, and testing grow faster than the number of agents, and coordination failures — agents contradicting each other, duplicating work, or producing inconsistent shared state — become the dominant failure mode, distinct from individual agent quality.
- **Framework abstractions hide the coordination surface.** LangGraph, CrewAI, and AutoGen all make agent instantiation easy. None make coordination obvious. The debugging surface is the prompt-response pipeline, and if the framework buries that, you're flying blind.
- **The gap between "orchestration pattern" and "framework" is where most projects stall.** A framework is an implementation choice. A pattern is an architectural one. Most teams pick a framework before understanding which pattern their problem actually needs.

## The move

**Use the six-pattern ladder. Start at the bottom; move up only when the current level genuinely can't handle the problem.**

### Pattern 01: Sequential Chain

The agent calls run one after another, each feeding its output into the next. Think: summarize → classify → route → respond.

- **When to use:** Each step has a single, well-defined purpose and the output of one step is the complete input of the next.
- **Why it beats multi-agent here:** Zero coordination overhead. Full trace. Every step is independently testable.
- **Failure mode:** Latency compounds. An error in step 1 cascades. No parallelism.

### Pattern 02: Router / Classifier Dispatch

A lightweight model or heuristic inspects the input and routes it to one of several specialized processing paths.

- **When to use:** Different input types need fundamentally different handling (technical support vs. billing vs. escalation; triage → specialized agent).
- **Why it beats multi-agent here:** Keeps single-agent simplicity per path while handling heterogeneous input.
- **Implementation:** Route by domain, intent, or content type. Keep routing deterministic; save the LLM for the routed path, not the routing decision.

### Pattern 03: Parallel Fan-Out / Fan-In

One agent decomposes a task into N independent sub-tasks, they run concurrently, and a aggregator agent synthesizes results.

- **When to use:** The sub-tasks are truly independent — e.g., analyzing multiple documents, running the same analysis from different angles, gathering data from multiple sources.
- **Why it beats sequential:** Nx speedup on parallelizable work. Critical for time-sensitive workflows.
- **Failure mode:** Sub-task outputs that are semantically inconsistent (one agent calls a price "high," another calls it "moderate") make aggregation painful. Add an explicit normalization step before aggregation.

### Pattern 04: Supervisor / Hierarchical

A central supervisor agent decomposes tasks and delegates to worker agents. The supervisor retains control and can course-correct.

- **When to use:** You need central oversight and the ability to reject or redirect sub-agent outputs before they propagate.
- **How LangGraph implements it:** Conditional edges from a supervisor node to worker nodes based on the supervisor's output. The state graph is explicit and inspectable.
- **Why production teams prefer this over swarm:** The control flow is deterministic. You can visualize the graph. You can replay any state.
- **Failure mode:** Supervisor becomes a bottleneck — if the supervisor LLM is weak, it makes poor routing decisions that cascade to all workers.

### Pattern 05: Handoff / Transfer

An agent explicitly transfers control and context to another agent, including the conversation history and any relevant state.

- **When to use:** Real-world handoffs — e.g., a sales agent qualifying a lead hands off to a closing agent; a triage nurse hands off to a specialist. The next agent needs full context to take ownership.
- **How OpenAI Swarm implements it:** Explicit handoff functions that carry state between agents. Simple and readable.
- **Critical gotcha:** The handoff must carry not just data but intent. "User wants to cancel" is data. "User wants to cancel because the product broke and they're frustrated" is intent — and it's what the next agent needs to avoid re-opening a resolved complaint.
- **Failure mode:** Without explicit handoff contracts, agents pass vague context that forces the receiving agent to re-ask questions the sending agent already answered.

### Pattern 06: Swarm / Emergent

Agents self-organize without predefined roles, negotiating responsibilities dynamically. No central control.

- **When to use:** Exploratory research, complex adaptive problems where no single agent can see the whole solution space. Research and creative tasks.
- **Why most teams shouldn't start here:** Emergent behavior is by definition unpredicable and unauditable. Loop detection is hard. Debugging is near-impossible. You lose deterministic replay.
- **What works in practice:** Use swarm as a bounded sub-system within a hierarchical wrapper. Let the swarm explore within a constrained state space; supervisor agents validate and gate the results.

## Evidence

- **MDPI Survey (2026):** Zhu et al. document that coordination failures — agents contradicting one another, duplicating effort, producing inconsistent shared state — are the dominant cause of system-level degradation in multi-agent setups, distinct from individual agent quality. The survey covers orchestration frameworks from 2023–2026 and proposes a two-dimensional taxonomy (coordination topology × runtime adaptivity). — [MDPI Future Internet, Vol 18(6)326](https://www.mdpi.com/1999-5903/18/6/326)
- **Hacker News practitioner thread (2026):** Practitioners report rolling custom orchestration because "there's absolute 0 framework out there that's good enough for serious work," using LangGraph as a state machine substrate while building custom routing logic on top. Observability and trace-level debugging emerge as the top pain points across all frameworks. — [HN: Multi-Agent Workflow Orchestration in Production](https://news.ycombinator.com/item?id=47660705)
- **Framework comparison (Presenc AI, May 2026):** LangGraph has the largest production deployment footprint in 2026; CrewAI leads on demo-to-prototype speed but trails on observability and error recovery; 65% of teams hit an architectural ceiling within 12 months and have to rewrite. For most enterprise deployments, framework choice matters less than underlying model selection and state management design. — [Presenc AI: Multi-Agent Orchestration Frameworks 2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)

## Gotchas

- **Don't split into multiple agents until a single agent with multiple tools genuinely fails you.** The failure mode of premature multi-agent is worse than the failure mode of a complex single agent — because with multiple agents you now have coordination failures on top of reasoning failures.
- **State management is the hardest part, not agent logic.** How you pass state between agents (shared memory, message queues, shared context window, vector DB lookups) is the architectural decision that determines whether your system scales or collapses under complexity. Choose before choosing a framework.
- **Framework stability is underrated.** LangGraph, CrewAI, and AutoGen all changed their APIs significantly between 2024 and 2026. If you're building on a framework, pin your version and treat major framework upgrades as production migrations.
- **Loop detection is non-negotiable in any pattern above sequential.** Without a hard max-turns or a termination signal, agents in loops with tools or each other will burn tokens until the budget runs out. Build this before the demo.
