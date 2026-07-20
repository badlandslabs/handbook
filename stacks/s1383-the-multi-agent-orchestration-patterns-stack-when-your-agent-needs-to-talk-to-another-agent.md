# S-1383 · The Multi-Agent Orchestration Patterns Stack — When Your Agent Needs to Talk to Another Agent

You have a research task that needs a web searcher, a code executor, and a synthesizer. You could put it all in one agent. It will hallucinate, time out, and leave you with half an answer. The alternative is multiple agents with explicit coordination — but choosing the wrong coordination pattern is equally destructive.

## Forces

- **One agent can't specialize at every task.** Context windows fill up, prompts bloat, and quality drops when the same model tries to be retriever, coder, reviewer, and writer simultaneously.
- **Coordination has real costs.** Every handoff adds latency, token burn, and failure surface. Over-orchestrating creates worse problems than under-orchestrating.
- **57% of failed AI projects root-cause in orchestration design** — not the individual agents, but how they talk to each other (Anthropic, 200+ enterprise deployments analyzed).
- **The protocol landscape is fragmenting.** MCP, A2A, ACP, and ANP all solve different layers. Picking the wrong abstraction means rewriting it later.
- **There is no universal pattern.** A pipeline fits one class of problem; a swarm fits another. The mistake is using the pattern you know instead of the one the problem demands.

## The Move

Know the six foundational patterns and their actual trade-offs. Then match the pattern to the task topology — not the other way around.

### Pattern 1: Single Agent
One agent, one job. No coordination overhead. Use this as the starting point before reaching for anything more complex.
- Best for: bounded tasks that fit inside a single context window and have no need for external tools beyond what one model can handle
- Avoid when: the task exceeds context, requires fundamentally different skill sets, or has a single point of failure you can't tolerate

### Pattern 2: Supervisor (Orchestrator-Worker)
A lead agent routes tasks to specialized subagents and synthesizes their outputs.
- Best for: multi-domain tasks requiring synthesis — e.g., a research task that needs web search, code analysis, and report writing
- Implementation: Anthropic's Research feature uses this pattern — a Claude Opus 4 lead agent delegates to Sonnet 4 subagents that run in parallel; the lead synthesizes
- Key mechanism: structured output schemas for handoffs so the supervisor gets consistent, parseable results from each worker

### Pattern 3: Router
An LLM-based classifier routes incoming requests to the correct specialist agent.
- Best for: high-volume, heterogeneous inputs where a triage step saves downstream cost and latency
- Claims: 30–60% cost reduction achievable with the Router pattern (AnhTu.dev, analysis of 200+ enterprise deployments)
- Avoid when: inputs are homogeneous or the routing logic is simpler than the classifier overhead

### Pattern 4: Pipeline (Sequential)
Agents process tasks in a defined order, each passing output to the next.
- Best for: tasks with a strict dependency chain — validate → transform → format → deliver
- Limitation: no concurrency; total latency equals sum of all steps
- The AccelateAI/multi-agent-orchestration repo provides production-grade Python patterns for this with explicit error recovery at each stage

### Pattern 5: Parallel Fan-Out / Fan-In
A task is split and dispatched to multiple agents simultaneously, results are collected and merged.
- Best for: tasks where parallel execution provides a clear speed or quality advantage — e.g., researching multiple subtopics at once
- Google's internal experiments: distributed multi-agent processing cut task time from 1 hour to 10 minutes — a 6× speedup
- Watch for: result merging complexity; divergent outputs need a reconciliation step

### Pattern 6: Swarm (Autonomous Negotiation)
Agents communicate and negotiate without a central coordinator — emergent task distribution.
- Best for: open-ended, creative, or adversarial tasks where no single agent has the full picture
- Emerging pattern in 2025–2026; tooling is immature and failure modes are poorly understood
- CrewAI and similar frameworks provide the closest production implementation via process classes

### Protocol Layer: MCP + A2A
These aren't orchestration patterns — they're the plumbing that makes patterns 1–6 work across system boundaries.

| Protocol | Layer | What it connects | Governance |
|---|---|---|---|
| **MCP** (Model Context Protocol) | Agent → Tools/Resources | Anthropic, Linux Foundation | SDKs: 97M+ downloads |
| **A2A** (Agent-to-Agent) | Agent → Agent | Google, Linux Foundation | 150+ partner orgs |
| **ACP** (Agent Communication Protocol) | Multi-framework messaging | IBM, Linux Foundation | — |
| **ANP** (Agent Network Protocol) | Decentralized marketplaces | Community | — |

MCP and A2A are the dominant pair in 2025–2026. Think of them as analogous to TCP/IP and HTTP: they solve different layers of the communication problem.

## Evidence

- **Anthropic Engineering Blog:** Anthropic's own Research feature uses an orchestrator-worker pattern. Lead agent: Claude Opus 4. Subagents: Claude Sonnet 4, running in parallel. Key lessons: structured output schemas for handoffs prevent quality degradation; context management at the supervisor level is the hardest engineering problem.
  — https://www.anthropic.com/engineering/multi-agent-research-system

- **AnhTu.dev (2026):** Analysis of 200+ enterprise multi-agent deployments finds 57% of failures root-caused in orchestration design (not individual agents). The Router pattern delivers 30–60% cost reduction. 40% of multi-agent pilots fail within 6 months — most due to handoff quality, not model quality.
  — https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121

- **Google internal experiments (cited in MACGPU 2026 guide):** Distributed multi-agent architecture reduced processing time from 1 hour to 10 minutes — a 6× improvement over serial single-agent execution.
  — https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html

- **MMC Ventures (2025):** Surveyed 30+ European agentic AI startup founders and 40+ enterprise practitioners. Finding: most companies have "some agents" in production with strong human oversight; fully autonomous multi-agent deployments remain rare outside narrow verticals.
  — https://mmc.vc/research/state-of-agentic-ai-founders-edition/

- **LushBinary (2026):** Four production-proven patterns tested in enterprise deployments: Supervisor, Swarm, Pipeline, and Router. Key lesson: make orchestration deterministic (state machines for flow control); keep judgment bounded in the agent.
  — https://lushbinary.com/blog/multi-agent-orchestration-patterns-supervisor-swarm-pipeline-router-guide

- **GitHub: AccelateAI/multi-agent-orchestration:** Production-grade Python patterns for supervisor routing, sequential pipelines, parallel fan-out, error recovery, and state persistence. Explicit focus on failure handling at each orchestration boundary.
  — https://github.com/AccelateAI/multi-agent-orchestration

- **AI University (2026):** Runs 15 agents in production. Documents six patterns with honest tradeoffs. Key warning: most teams treat architecture as an afterthought and pay for it in debugging time.
  — https://theaiuniversity.com/docs/building-agents/architecture-patterns

## Gotchas

- **The supervisor becomes the bottleneck.** A lead agent coordinating 8 subagents is only as good as its synthesis step. If the supervisor prompt degrades, everything downstream degrades. Test synthesis quality explicitly.

- **Structured output is non-negotiable for handoffs.** Without explicit schemas (Pydantic, JSON Schema), agents pass free-text between each other and hallucination compounds at each hop. Anthropic's engineering post calls this out as their primary lesson.

- **Parallel doesn't always mean faster.** Fan-out only helps when subagents are genuinely I/O-bound (waiting on external tools, APIs, or searches). CPU-bound agent work gets no speedup and burns more tokens.

- **Overhead scales with agent count.** Above ~6 agents in a single workflow, coordination overhead (token counts, latency, failure probability) often exceeds the specialization benefit. Break large problems into smaller crews.

- **Swarm patterns sound elegant but are operationally opaque.** When something goes wrong in an autonomous negotiation, you have limited ability to reconstruct what happened. Most production systems use swarm patterns only in bounded, sandboxed contexts.
