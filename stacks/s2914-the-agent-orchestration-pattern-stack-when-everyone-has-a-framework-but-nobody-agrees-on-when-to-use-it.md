# S-2914 · The Agent Orchestration Pattern Stack

When your agent does three things and you need five, and every framework author claims their pattern is canonical — but the teams shipping to production have converged on something simpler, and quietly.

## Forces

- **Fixed pipelines are safe but fragile.** Sequential chains are predictable and testable, but break the moment the input shape drifts from what the designer anticipated. Research tasks are inherently dynamic and path-dependent — you can't predeclare the steps.
- **Full agentic loops are powerful but opaque.** A model driving its own tool loop can handle novel situations, but you lose determinism, debugging becomes archaeology, and costs scale unpredictably with task complexity.
- **Multi-agent sounds great until something goes wrong.** Microsoft ISE documented it precisely: each additional agent multiplies operational complexity. Most production "multi-agent" systems are really one supervisor + 2-4 specialists — not the swarm of 50 concurrent agents the demos show.
- **The framework landscape fragmented hard.** AutoGen is in maintenance mode as of 2026. The real choice narrowed to LangGraph (graph-based state, most verifiable production deployments) and CrewAI (fastest prototype path, hits a ceiling at scale). ODSEA's CTO wrote it plainly: "prototype in CrewAI, harden in LangGraph."
- **Parallelism is the underrated pattern.** Anthropic's Research feature runs parallel subagents with separate context windows to compress information simultaneously. The lead agent synthesizes. This solves context-window pressure on long research tasks — a concrete, repeatable win.

## The move

Three patterns dominate real production deployments — not as a consensus from theory, but from teams having to actually ship:

**1. Supervisor + Specialists (hierarchical)**
One supervisor agent decomposes the incoming task and routes subtasks to specialists. Each specialist executes and returns results. The supervisor integrates. This is the most common "multi-agent" production pattern because it is debuggable — you can trace which specialist was called and why. Databricks + BASF Coatings shipped this to production (Oct 2025) for cross-team enterprise AI. Microsoft ISE documented the same migration path from modular monolith to supervisor microservices.

**2. Sequential Pipeline (fan-in chain)**
Tasks flow through a fixed sequence: researcher → writer → editor. Each agent has a clear input/output contract. When the task structure is known upfront, this is cheaper to run, easier to test, and far easier to debug than any dynamic pattern. Start here before adding complexity.

**3. Parallel Fan-Out / Fan-In**
A lead agent dispatches multiple specialist agents simultaneously, then synthesizes their results. Anthropic's Research system uses this: parallel subagents explore different facets of a topic in their own context windows, distilling findings before the lead agent synthesizes. The payoff is real when tasks are compressible — different search paths, different document reviews, different code components.

**The decision ladder:**
- Task steps known upfront, latency sensitive? → Sequential pipeline
- Task has unpredictable branches, needs specialist judgment? → Supervisor + specialists
- Task has independent subtasks that can run simultaneously? → Parallel fan-out
- Open-ended, path-dependent, no known structure? → Agentic loop (with strict cost/steps guardrails)
- None of the above clearly applies? → Start with sequential; add complexity only when measured need appears

**On tool count:** Shopify Sidekick's production experience surfaces a sharp threshold: 0-20 tools, clear boundaries, easy debugging. Above 20, capability overlaps and routing ambiguity grow fast. The fix is not more prompts — it is explicit tool grouping, hierarchy, or specialization.

## Evidence

- **Engineering blog (Anthropic, Jun 2025):** Anthropic's Research feature uses orchestrator-worker pattern — lead agent plans and spawns parallel subagents with separate context windows, distilling information before synthesis. Key design decisions: subagents as intelligent filters, iterative refinement, and autonomous multi-turn operation with decision checkpoints. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Engineering blog (Microsoft ISE, Jun 2026):** Documented migration of a large retail customer's chatbot from modular monolith + deterministic router to microservices-based coordinator pattern. Key finding: transitioning from "one query → one agent" to "one query → multiple collaborating agents" with a coordinator service that orchestrates, validates, and synthesizes. Original bottleneck was tight coupling between agent modules and the chatbot application — architectural duplication across teams. — [URL](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Company engineering (Shopify, Aug 2025):** Sidekick's production journey: agentic loop (Anthropic's model) with a predictable pain threshold at 20+ tools where agent performance degrades without explicit boundaries. Described the architecture evolution as "continuous cycle: human input → LLM processing → action decision → execution → feedback → repeat." — [URL](https://shopify.engineering/building-production-ready-agentic-systems)

- **Engineering blog (Turion.ai, Mar 2026):** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Practical patterns from a dozen production deployments: supervisor + specialists, pipeline specialists, and parallel research. Notes that most production failures come from state management and inter-agent communication breakdown, not the model itself. — [URL](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production/)

- **Framework comparison (ODSEA CTO, May 2026):** After evaluating LangGraph, CrewAI, and AutoGen in production: LangGraph chosen for Agent Platform v2 based on verifiable production deployments, native HITL support, and durable state management. AutoGen effectively in maintenance mode. Key production finding: "AutoGen burns tokens at 5x the rate of LangGraph." — [URL](https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production)

- **Case study (Databricks, Oct 2025):** BASF Coatings deployment using supervisor agent pattern for enterprise-scale AI — connecting specialized teams' data domains through a single supervisor interface. Reduced cross-team friction, enabled compliance controls per data domain, faster decision-making. — [URL](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

- **Show HN (Mar 2025):** "Evolving Agents Framework" — 139 points on HN. Novel approach to dynamic agent management: reuse, evolve, or create agents based on semantic similarity; agents can delegate to specialists; YAML workflow definitions. Real signal of what practitioners are building toward beyond static agent definitions. — [URL](https://news.ycombinator.com/item?id=43310963)

## Gotchas

- **Don't reach for the agentic loop first.** It is the right answer for a minority of workflows. Most business tasks have a known structure — sequential or supervisor is cheaper, faster, and more debuggable.
- **Every agent you add multiplies failure modes.** State management between agents is the real unsolved problem in production — not the model. Plan for explicit, serializable state passing, not implicit context sharing.
- **Framework choice is load-bearing for production.** CrewAI gets you running fast but hits walls around state durability, HITL, and observability. LangGraph's graph-based state model is verbose but production-hard. Pick the framework that matches where you'll end up, not where you're starting.
- **Context window pressure breaks parallelism.** When parallel subagents return, their combined outputs can exceed context. Design distillation or summarization into the subagent output contract before running parallel at scale.
- **The observability gap is real.** Multi-agent runs produce interleaved logs across agent boundaries. Build trace IDs, structured logging, and per-agent span tracking before you need to debug a production failure — you will need it.
