# S-1476 · The Orchestration Pattern Stack — When One Agent Is Not Enough

You built a capable single agent. Then the task grew — it needs to research, write, review, and format. You added more tools. The prompt got longer. Now it is slower, less reliable, and you cannot debug which step caused the failure. The problem isn't your agent's capability. It's that you gave it one job to do when the work has multiple distinct phases, each with different requirements.

## Forces

- **Specialized models beat generalists.** A research agent optimized for web traversal outperforms a general agent doing research as one of five tasks. But managing multiple specialized agents requires coordination logic that doesn't belong in any single agent's prompt.
- **Explicit control flow beats emergent behavior.** When five agents need to run in a specific order with conditional branching, prompt engineering produces unreliable control flow. You need graph-structured or code-defined orchestration.
- **Every orchestration pattern has a failure mode.** Sequential pipelines break on branching logic. Fan-out/aggregate loses ordering guarantees. Router patterns accumulate classification errors. Supervisor patterns create a single point of failure. No pattern wins universally — the choice is load-bearing.
- **The framework you choose shapes what you can do.** LangGraph's graph-based state machine makes checkpoints and time-travel debugging first-class. CrewAI's role-based model ships faster but obscures control flow. OpenAI Agents SDK makes handoffs explicit. The framework is an architectural decision, not a commodity.

## The Move

Choose your orchestration pattern based on the nature of the work, not the tooling preference. Six patterns cover most real production cases:

- **Router** — Classify the input and dispatch to a specialized agent. Use when the input type determines the entire execution path (e.g., support ticket routing to billing vs. technical agents). Keep the classifier small and fast; use its output as a switch, not a full LLM call.
- **Sequential Pipeline** — Run agents one after another, each feeding its output to the next. Use for fixed-step workflows: research → draft → review → publish. Each stage should have a single, narrow responsibility. Failure at any step should halt the pipeline and surface an error, not continue with corrupted state.
- **Parallel Fan-Out / Aggregate** — Dispatch the same task to multiple agents simultaneously and merge results. Use for synthesis tasks (multiple search queries, multiple code reviewers, multiple data extractors). The aggregation step is the hard part — define the merge logic explicitly, not as "let the LLM figure it out."
- **Supervisor / Hierarchical** — One coordinating agent manages specialist agents, decides when to invoke each, and owns the final response. Use when task assignment is dynamic and context-dependent. The supervisor must have enough context to route intelligently without being so verbose that it confuses the specialist agents.
- **Evaluator-Optimizer Loop** — Run an agent, evaluate its output against criteria, and iterate until a threshold is met or a max iteration count is hit. Use for creative or quality-sensitive tasks: code refactors, document drafts, response polishing. Set a hard iteration cap — without one, loops run indefinitely on inputs the agent keeps "almost" getting right.
- **Handoff Orchestration** — Agents explicitly transfer control to another agent, passing state along. Use when ownership genuinely changes: a triage agent handing off to a domain specialist. OpenAI Agents SDK treats handoffs as first-class constructs, making the transition explicit rather than implicit.

**Framework selection** (from production evidence):
- LangGraph (90M monthly downloads) for complex, stateful workflows requiring checkpointing, time-travel debugging, and human-in-the-loop at specific nodes. Deployed at Uber, LinkedIn, Replit, Klarna, Cisco, JP Morgan, BlackRock.
- CrewAI for rapid prototyping of coordinator-worker patterns where agents have clear role definitions. Ships faster but control flow is less inspectable.
- OpenAI Agents SDK when you are all-in on the OpenAI ecosystem and want first-class handoff primitives.
- Semantic Kernel when you need C#/Python parity and enterprise integration (Microsoft Copilot lineage).

**Governance layer (AxonFlow pattern)** — For teams running agents in high-stakes production: an inline control plane that governs retries, policy enforcement, and approvals per step, running alongside LangChain/CrewAI/custom systems. Addresses the problem where "retries accidentally repeat side effects" and "partial failures mid-workflow" corrupt shared state.

## Evidence

- **Microsoft Azure Architecture Center** defines five core orchestration patterns (Sequential, Concurrent, Group Chat, Handoff, Magentic) with explicit guidance on failure boundaries and when to use each. The recommendation: start with sequential, add concurrency only when parallelism is provably safe. — [learn.microsoft.com/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- **LangChain blog (Feb 2025)** documents production LangGraph deployments: LinkedIn uses a hierarchical agent system for AI-powered recruiting (sourcing → matching → messaging, freed recruiters for strategy); AppFolio built a property management copilot that saves 10+ hours/week per manager; Cisco handles 60% of ~1.8M monthly support cases through AI-driven automation via LangGraph/LangSmith. — [langchain.com/blog/is-langgraph-used-in-production](https://www.langchain.com/blog/is-langgraph-used-in-production)
- **Alphabold (March 2026)** reports LangGraph at Uber, JP Morgan, BlackRock, Cisco, LinkedIn, Klarna, Elastic, and Bertelsmann, citing 90M monthly downloads and 57% of organizations already running agents in production. Key insight: quality (not cost) is the primary barrier to deployment. — [alphabold.com/langgraph-agents-in-production](https://www.alphabold.com/langgraph-agents-in-production)
- **Imperialis Tech (March 2026)** — production challenges that benchmarks don't surface: determinism issues when the same workflow produces different outputs across runs; integration complexity when connecting agent outputs to downstream systems; cost compounding as fan-out agents each make LLM calls. — [imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production](https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production)
- **Thinking.inc (March 2026)** — six core patterns (Supervisor, Sequential Pipeline, Parallel Fan-Out, Router, Hierarchical, Evaluator-Optimizer) covering "the vast majority of enterprise use cases." Notes that production systems typically combine two or three patterns within a single workflow. — [thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns)
- **Zylos Research (2026)** — emerging patterns: difficulty-aware dynamic routing (classifier estimates query complexity, routes to shallow or deep pipeline, achieves cost reduction without accuracy loss); federated orchestration for edge-deployed agents. — [zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)
- **AxonFlow Show HN (2025)** — self-hosted governance layer for production agent workflows: governs retries (preventing side-effect repetition), enforces step-level permissions, provides inspection/intervention mid-execution. Runs alongside LangChain, CrewAI, or custom systems. — [news.ycombinator.com/item?id=46692499](https://news.ycombinator.com/item?id=46692499)

## Gotchas

- **Do not fan out without a defined aggregation strategy.** Multiple agents producing results that get "merged by LLM" is a common pattern that produces unpredictable output quality. Define the merge logic explicitly.
- **Evaluator-Optimizer loops need hard caps.** Without a max-iteration setting, loops persist indefinitely on inputs the agent keeps nearly succeeding on. Set `max_iterations=3` or similar and treat hitting the cap as a partial failure, not a success.
- **Router classification errors compound.** A mis-routed input reaches the wrong specialist and produces output that is confidently wrong. Validate router accuracy separately from specialist accuracy.
- **Framework switching cost is high.** LangGraph, CrewAI, and Semantic Kernel have fundamentally different mental models. Choose based on your team's long-term needs, not initial demo speed.
- **Checkpointing is not optional in stateful workflows.** Without LangGraph-style checkpointing (or equivalent), mid-workflow failures force a full restart. With it, you can resume from the last successful step.
