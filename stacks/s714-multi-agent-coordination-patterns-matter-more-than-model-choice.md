# S-714 · Multi-Agent Coordination: Pattern Beats Model

[When a single agent can't cut it and you split into multiple, the choice of coordination topology is the architectural decision that determines cost, debuggability, and failure modes. Most teams pick a framework before they pick a pattern — and regret it.]

## Forces

- **Coordination overhead scales non-linearly.** A peer-to-peer network of 10 agents has 45 potential communication channels; a supervisor/worker topology has 10. Pattern choice is the lever that controls this curve.
- **Pattern choice dominates outcomes more than model capability.** In logistics multi-agent systems, pattern optimization yields +27% throughput and −22% cost — gains that exceed what swapping to a better model delivers.
- **Framework constraints bake in topology assumptions.** LangGraph's state machine model makes supervisor/worker natural; AutoGen's conversation model makes peer collaboration natural. Choosing the framework first locks you into a coordination topology you may not have chosen on its own merits.
- **The decision to go multi-agent is made too early.** Coordination costs — partial failure, negotiation overhead, conflict resolution — are systematically underestimated. Most systems that split into multiple agents could have stayed monolithic with better tool design.

## The Move

The decisive move is choosing your coordination topology *before* your framework, then verifying it holds under the three failure modes: silent failure, cascade failure, and infinite loop.

**Five canonical topologies, in order of increasing coordination cost:**

- **Sequential (Pipeline):** Fixed linear order. Unix-pipe equivalent. Best when steps have hard dependencies and each agent transforms output from the previous. Failure is localized and traceable. Lowest overhead. Suitable for report generation, data extraction pipelines.
- **Supervisor/Worker (Hierarchical):** One orchestrator decomposes tasks and dispatches to specialists. LangGraph's natural model. Best for planner-executor patterns. Coordinator is the bottleneck and single point of failure. Failure domain is isolated to the failing worker.
- **Sequential + Supervisor Hybrid:** Supervisor dispatches to workers that run sub-agents in sequence. Best for "marketing agency" topologies where a Director coordinates specialists who each run multi-step pipelines. Opensoul uses this — Director → Strategist → Creative → Producer → Growth Marketer → Analyst.
- **Peer-to-Peer (Collaboration):** Agents negotiate shared goals without a central controller. Natural for AutoGen. Best when no agent has full task visibility and emergent coordination is desired. Has 45 channels at 10 agents — observability degrades fast.
- **Marketplace (Swarm):** Agents publish and subscribe to tasks. Most flexible, highest overhead. Best for loosely coupled ecosystems where agents join/leave dynamically.

**Verification before production:**
1. Simulate partial failure (kill one agent mid-workflow) — does the system recover or cascade?
2. Run cost tracing at agent boundaries — which agent is the token sink?
3. Inject a contradictory output from one agent — does the system detect and resolve the conflict?

## Evidence

- **Thread Transfer analysis:** Across logistics multi-agent systems, pattern optimization delivers +27% throughput and −22% cost reduction — exceeding the gains from model capability improvements alone. ChatDev (peer-to-peer dev agents) achieves 33.3% correctness on real programming tasks; AppWorld cross-app workflows fail 86.7% of the time. Pattern choice correlates strongly with outcome more than model scale. — [Thread Transfer, July 2025](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)
- **Amazon internal lessons:** HITL (Human-in-the-Loop) becomes critical for multi-agent evaluation because of "increased complexity and potential for unexpected emergent behaviors that automated metrics might fail to capture." Key evaluation dimensions: inter-agent communication coordination failure, agent specialization appropriateness, conflict resolution strategy quality, and logical consistency across agent contributions. — [AWS Machine Learning Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **RockB production guide:** Peer-to-peer of 10 agents = 45 communication channels vs. supervisor/worker = 10. Observability tooling (LangSmith) assumes hierarchical tree structures and struggles with peer-to-peer meshes. LangSmith tracing works well with supervisor/worker but requires custom instrumentation for peer topologies. — [RockB Multi-Agent Guide 2026](https://baeseokjae.github.io/posts/multi-agent-system-design-guide-2026)
- **TURION.AI:** Coordination cost is the systemic trade-off: more agents enable specialization, parallelism, modularity, and robustness — but introduce discovery, negotiation, partial failure, and conflict resolution overhead that most teams discover only in production. — [TURION.AI, Dec 2024](https://turion.ai/blog/multi-agent-collaboration-patterns)

## Gotchas

- **You don't need multiple agents.** The default should be one agent with better tools. The decision to split is usually made too early. Split only when you have evidence that a single agent is hitting capability limits, not when the architecture "feels too simple."
- **LangGraph + MCP is the dominant enterprise combination.** Most production 2026 systems use LangGraph for orchestration and MCP for tool exposure. Don't use CrewAI for production unless you have a specific reason — its fast-to-MVP characteristic becomes a rewrite liability at scale within 6-12 months.
- **Silent failure is the default failure mode.** An agent that calls a wrong tool or hallucinates a sub-result often returns plausible-looking output. Build explicit output validation at every agent boundary — not just at the final output.
- **Observability tooling assumes topology.** LangSmith works well with hierarchical trees; peer-to-peer meshes require custom instrumentation. If you're building a swarm or marketplace topology, plan for observability from day one — you can't retrofit it.
