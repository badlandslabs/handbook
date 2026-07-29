# S-1816 · The Orchestration Complexity Stack — When You're Not Sure If You Need More Agents

Adding agents seems like the answer to every agentic problem. Slow? Add a parallel agent. Wrong output? Add a reviewer agent. Confused? Add a planner. Six months later you have 14 agents talking to each other and no one can debug why the output is occasionally catastrophic. The question is not "how many agents" — it is what kind of coordination complexity you are actually trading for.

## Forces

- **Multi-agent adds coordination overhead that compounds with scale.** Every new agent introduces a communication protocol, a failure mode, and a consistency problem. A 5-agent system is not 5x harder than a 1-agent system — it is a graph of failure modes.
- **The single-agent vs. multi-agent distinction is blurry and misused.** A manager agent invoking subagents via tool calls is a single-agent system with subagents, not a multi-agent system. True multi-agent means peer coordination with shared state. Most teams building "multi-agent" are building the former.
- **Orchestration frameworks are implementation details, not architecture.** LangGraph, CrewAI, AutoGen, and custom solutions all implement variations of the same 4-5 patterns. Choosing a framework before choosing a pattern is like picking a database before knowing your query shape.
- **Context window pressure drives the architectural decision more than capability.** The reason to split across agents is usually that one context cannot hold the working state for a long task — not that you need distinct capabilities.
- **Parallelism is the main valid reason for multi-agent.** If steps can run concurrently, splitting them across agents pays off. If steps are sequential, you are adding latency and cost for no capability gain.

## The Move

Map your actual coordination pattern before adding agents. Four patterns, from simplest to most complex:

- **Single agent + tools:** One agent loops through its own tool calls. Suits most use cases. Add agents only when this genuinely cannot scale.
- **Single agent + subagent-tools (manager pattern):** A manager agent spawns bounded subagents as tools, collects results, synthesizes. The manager owns the state. This is NOT multi-agent coordination — it is a single-agent with delegation. For most production systems, this is as complex as you need.
- **True multi-agent (peer coordination):** Multiple agents with shared state, explicit message passing, and mutual dependency. Appropriate when specialists genuinely need to negotiate, vote, or revise each other's outputs. Higher cost, harder to debug.
- **DAG / workflow (explicit orchestration):** Predefined graph of steps, deterministic execution order. Use when the process is known upfront and adaptability is not required. LangGraph, Temporal, Airflow handle this well.

Choose the simplest pattern that fits your actual requirement. Increment complexity only when the simpler pattern demonstrably fails.

## Evidence

- **Anthropic Engineering Blog (Jun 2025):** Claude's Research feature uses a lead agent that plans and spawns parallel subagents searching simultaneously. The key lesson: parallelism drives the architectural decision — they used multi-agent because research paths are inherently concurrent and path-dependent, not because multiple capability types were needed. Subagents search in parallel; the manager synthesizes. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Presenc AI Framework Comparison (May 2026):** Surveying LangGraph, CrewAI, AutoGen, OpenAI Swarm, and Google ADK, the key finding: "For most enterprise deployments, framework choice is less consequential than model selection, evaluation infrastructure, and human-checkpoint design." LangGraph has the largest production footprint; CrewAI the easiest prototype ramp; AutoGen leads in research. — [presenc.ai/research/multi-agent-orchestration-frameworks-2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)
- **Harsh Rastogi (Mar 2026) — Modelia.ai / Asynq.ai field report:** Production failures from over-engineered multi-agent stacks: a candidate evaluation agent produced contradictory evaluations across its own reasoning chain; an image generation agent optimized for workflow completion over quality. Both failures were structural (misaligned objectives, not tool errors). The fix was not more agents — it was better objective specification and human checkpoints. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **NIST Tool Use Consortium (Jan 2025):** ~140 experts identified that agent tool taxonomy and interface design is a prerequisite for multi-agent coordination — you cannot reliably coordinate agents that cannot reliably call tools. Tool standardization (MCP, A2A protocols) is the infrastructure layer that makes multi-agent feasible. — [nist.gov/news-events/news/2025/08/lessons-learned-consortium-tool-use-agent-systems](https://www.nist.gov/news-events/news/2025/08/lessons-learned-consortium-tool-use-agent-agent-systems)
- **Azure Architecture Center (2026):** Clear complexity spectrum: direct model call → single agent + tools → multi-agent orchestration. The guidance: "Use if prompt engineering suffices" for level 1; "use when varied queries within a single domain require dynamic tool use" for level 2; "use when tasks require cross-domain coordination, distinct security boundaries, or benefit from parallel specialization" for level 3. — [learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

## Gotchas

- **"We need multi-agent" is usually a red flag in the design phase.** Most teams say this before they have exhausted single-agent + tools. Prove the simpler pattern fails before escalating.
- **Orchestration framework comparisons are nearly useless in isolation.** LangGraph vs. CrewAI vs. AutoGen differences matter at the margins — what matters is whether your process is a DAG (LangGraph), a team (CrewAI), or a research debate (AutoGen). Pick the pattern first.
- **Peer-to-peer multi-agent introduces non-determinism at the coordination layer.** Two agents disagreeing is not an exception to handle — it is the expected state. You need explicit consensus, voting, or human escalation paths. Without this, the system will pick one agent's confident-but-wrong answer.
- **Context window is a physical constraint, not a design preference.** If you hit context limits, split the work across agents. If you do not hit context limits but want parallelism for speed, measure whether the parallelism cost exceeds the sequential latency savings before adding agents.
- **Agent count does not equal capability.** A system of 8 general-purpose agents is less capable than a system of 3 highly specialized ones with tight, well-defined interfaces. Invest in specialization and interface quality, not agent count.
