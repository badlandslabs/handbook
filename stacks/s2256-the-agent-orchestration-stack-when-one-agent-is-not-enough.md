# S-2256 · The Agent Orchestration Stack: When One Agent Is Not Enough

You built a single-agent system. It works. Then the task grows: branching logic, parallel workstreams, specialized subdomains, or the need to resume after a crash. The naive response is to add more agents. The real question is whether that complexity is justified — and if so, which orchestration pattern actually fits your problem.

## Forces

- **Agents accumulate context debt.** A single agent handling research, writing, and code execution degrades over long sessions. Irrelevant context from one domain pollutes outputs in another. The fix (specialization) introduces the coordination problem.
- **Framework hype vs. production reality.** Every orchestration framework has a demo that works and a production story that's more complicated. The HN consensus from real deployments: start with the LLM API directly, reach for a framework only when the graph earns its keep.
- **Multi-agent complexity is multiplicative, not additive.** Two agents means twice the failure modes, twice the cost, and twice the observability surface. The 60% pilot failure rate (Gartner, 2026) for enterprise agentic projects stems largely from teams automating existing workflows instead of redesigning them for an autonomous executor.
- **The patterns converged.** Frontier systems — Claude Code, OpenAI Codex, Gemini CLI, LangGraph, CrewAI, Google ADK, Amazon Bedrock — built by different companies under different constraints, arrived at the same five composable patterns. Not by copying each other. Because the constraints are physics.

## The Move

Start with the simplest solution: one optimized LLM call with retrieval and in-context examples. Introduce orchestration complexity only when you have a specific, demonstrated need.

### The five composable patterns (Anthropic's taxonomy, Dec 2024)

1. **Prompt chaining** — Linear sequence of LLM calls, each feeding the next. Use when a task decomposes cleanly into ordered steps. Bottleneck: one step fails, the chain breaks.
2. **Routing** — A classifier (LLM or deterministic) directs the input to the right handler. Use when input types are distinct and you can dispatch without waiting for downstream results. Bottleneck: classifier accuracy gates everything.
3. **Parallelization** — Fan out to multiple agents working simultaneously, then aggregate. Use for independent subtasks (search N sources, classify N items). Bottleneck: no shared state between workers without explicit plumbing.
4. **Orchestrator-worker** — A central agent decomposes a complex task dynamically, delegates to specialists, synthesizes results. Use for multi-dimensional problems (like Anthropic's own Research system: lead agent + 3–5 subagents in parallel). Bottleneck: orchestrator becomes a single point of failure and cost concentration.
5. **Evaluator-optimizer** — A generate-and-revise loop with a critic agent. Use for content refinement (writing, code, analyses) where quality improves through iteration. Bottleneck: indefinite loops without a stopping condition.

### When to actually go multi-agent

LangGraph's Reddit community (r/LangChain, 2026) is blunt: **most teams reach for multi-agent too early.** LangGraph earns its keep when at least one of these is true:

- **Branching** — Different next steps based on classification, confidence, or tool output
- **Parallelism** — Fan-out to multiple independent workers
- **Crash-safe resume** — Need to checkpoint mid-workflow and resume
- **Human-in-the-loop** — Approval gates, review steps, or mid-workflow intervention
- **Complex state** — Typed state that evolves across multiple turns

If none of those apply, a single `create_agent` with 3–5 well-scoped tools beats a three-node graph with extra latency and opacity.

### Framework choice by mental model

| Framework | Mental Model | Best For |
|-----------|-------------|---------|
| LangGraph | Finite-state machine | Complex workflows, branching, checkpointing, human-in-the-loop |
| CrewAI | Small team of specialists | Fast prototyping, role-based agents, sequential/parallel task execution |
| AutoGen | Async group chat | Multi-agent conversation, code execution |
| OpenAI Agents SDK | Minimal orchestrator | Lightweight internal tools, low overhead |
| Custom (LLM API direct) | Your design | Simple workflows, full control, minimal dependencies |

LangGraph is the consensus choice when you need the graph — it treats orchestration as a first-class state machine with typed state, conditional branching, and built-in checkpointing. CrewAI is the fast path for demos; the migration cost comes when you need branching, approvals, or crash-safe resume.

### Operational patterns that work in production

- **Supervisor + Specialists** — One "supervisor" agent decomposes tasks and routes subtasks. Specialists execute and return results. Supervisor integrates. Simple, debuggable, effective. LangGraph's supervisor pattern, CrewAI's hierarchical mode, and custom orchestrators all implement this.
- **Confidence calibration** — Multi-agent systems need calibrated confidence: spawn a second agent to verify high-stakes outputs before committing to them. Expensive but catches semantic failures.
- **Structured inter-agent contracts** — Pass typed schemas between agents, not raw text. LangGraph's typed state and MCP's structured tool schemas both serve this purpose. Avoid agent-to-agent communication that depends on parsing natural language outputs.

## Evidence

- **Anthropic Engineering Blog:** "Building Effective Agents" (Dec 2024) — After working with dozens of teams, the finding: "The most successful implementations use simple, composable patterns rather than complex frameworks." The five-pattern taxonomy is the canonical reference. — [URL](https://www.anthropic.com/research/building-effective-agents)
- **Veso Research:** "Agentic Patterns" (May 2026) — Documents that Claude Code, OpenAI Codex, Gemini CLI, LangGraph, CrewAI, Google ADK, and Amazon Bedrock converged on the same design. States: "Not because they copied each other. Because the constraints are physics. Finite context windows. Tools that need a protocol. Safety that can't depend on the model obeying." — [URL](https://veso.ai/research/agentic-patterns/)
- **TURION.AI Field Note:** "Multi-Agent Orchestration Infrastructure: Lessons from Production" (Mar 2026) — Field report from real deployments: "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. In 2023, demos looked great. In 2024, production deployments mostly looked cursed. In 2025–2026, a handful of patterns emerged that actually work." — [URL](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **HN Ask Thread:** "How are you orchestrating multi-agent AI workflows in production?" (8 pts, ~4 months ago) — Practitioner responses document real patterns: state management across long conversations, confidence calibration, structured data passing, and observability needs. — [URL](https://news.ycombinator.com/item?id=47660705)
- **Microsoft ISE Developer Blog:** "Orchestration Patterns for Multi-Agent Systems" (Jun 2026) — Documents a real retail deployment transitioning from a modular monolith router to microservices-based coordinator pattern. — [URL](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **hjLabs AI Engineering Notes:** "CrewAI vs LangGraph vs AutoGen: Production Comparison" (18 months of field experience) — CrewAI for fast demos and role-based agents; LangGraph for complex workflows; AutoGen for multi-agent chat. Notes: "Benchmarks on toy tasks tell you almost nothing about how a framework behaves when a retrieval call times out at 2 a.m." — [URL](https://github.com/hemangjoshi37a/hjLabs-AI-Engineering-Notes/blob/main/04-crewai-vs-langgraph-vs-autogen-production-comparison.md)
- **Idea to MVP:** "Agent Orchestration with LangGraph: Patterns, Production Gotchas" (Jun 2026) — Reddit r/LangChain community consensus: most teams reach for multi-agent too early; LangGraph earns its keep for branching, parallelism, checkpointing, and human-in-the-loop. — [URL](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)

## Gotchas

- **Don't automate an existing process — redesign it.** The "automation illusion" (accounts payable agent mimicking a human clerk) produces agents that are slower and more brittle than the humans they replace. Redesign around API-first triggers and structured data handoffs.
- **Every agent you add multiplies operational burden.** More agents means more failure modes, more cost, and more observability debt. The exit cost from a multi-agent architecture is non-trivial.
- **Structured outputs between agents are not optional.** Agents communicating via raw text is a maintenance nightmare. Use typed schemas (Pydantic, JSON Schema) for inter-agent contracts — it makes debugging tractable.
- **Checkpointing is not optional for long-running workflows.** Without it, a crash mid-workflow loses all progress. LangGraph's checkpointing, CrewAI's memory, and custom solutions all address this — but you must implement it deliberately.
- **LLM APIs are not reliable in the infrastructure sense.** They have latency variance, rate limits, and occasional failures. Any orchestration pattern needs retry logic, timeouts, and graceful degradation — not just the happy path.
