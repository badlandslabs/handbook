# S-1937 · The Orchestration Dilemma Stack

*When simple calls can't cut it but agent frameworks collapse under production load — and you have to decide where along the complexity curve your system lives.*

## Forces

- **The hype tax** — Every framework promises agentic superpowers, but the tools that demo beautifully are the ones that fail quietly in production. 65% of teams hit a wall within 12 months and have to rewrite from scratch.
- **The abstraction trap** — High-level frameworks (CrewAI, LangChain) get new engineers productive in an afternoon, but obscure the execution model exactly when you need visibility: during partial failures, runaway loops, and cost overruns.
- **The rollout paradox** — Anthropic's own engineering team recommends starting with the simplest possible solution and only adding agentic complexity when evidence demands it. Yet the moment you need orchestration, you face a full rewrite if you chose wrong the first time.
- **Roll-your-own vs. framework** — HN practitioners are split: one camp says "there's absolute 0 framework out there that's good enough for serious work" (segmondy), the other camp says Agno's "minimalistic design for isolation, decoupling and control plane architecture" works (kathir05). Both camps are shipping.

## The move

The core insight from 18 months of production deployments across LangGraph, CrewAI, AutoGen, and Agno: **the framework is less important than the execution model you can reason about at 3 AM during an outage.**

### Layer 1 — Choose your orchestration philosophy before your framework

Three mental models, pick one:

| Philosophy | Framework | When it fits |
|---|---|---|
| **State machine** | LangGraph | Complex workflows with branching, loops, and checkpoint requirements; you need to replay execution |
| **Role-based** | CrewAI | Sequential pipelines where a clear specialist (researcher → writer → reviewer) maps to your problem |
| **Conversation-driven** | AutoGen / Agno | Async agent-to-agent delegation; agents exchange structured messages |

The mistake is using a framework for its ecosystem when your problem doesn't match its mental model.

### Layer 2 — Start at the lowest orchestration tier that solves the problem

Anthropic's tiered ladder (from simplest to most complex):

1. **Prompt chaining** — Sequential LLM calls where each output feeds the next. No agent needed. Use when: each step is deterministic and isolated.
2. **Parallelization** — Same prompt goes to multiple agents for independent work, results merged. Use when: independent subtasks can be done simultaneously.
3. **Router (LLM-directed)** — A single LLM classifies input and dispatches to the right handler. Use when: a single decision node gates different downstream paths.
4. **Orchestrator-workers** — One agent dynamically coordinates multiple specialized workers on subtasks it decomposes. Use when: the decomposition is non-trivial and context-dependent.
5. **Evaluator-optimizer** — A generator produces, an evaluator critiques, they loop until the evaluator passes. Use when: code, writing, or plans need iterative refinement.

**Rule:** If tier 1 works, don't build tier 2.

### Layer 3 — Implement state management before you need it

Production teams from HN's multi-agent discussion (2025) used:

- **MongoDB JSON documents** — each agent reads/writes shared state, pipeline ID links steps. Simple, queryable, auditable.
- **Redis scratchpads** — low-latency ephemeral state for in-flight coordination between agent turns.
- **Vector DB (Milvus + Agno)** — for retrieval-augmented agents where context window is the bottleneck.

**The anti-pattern:** passing full conversation history between agents. This causes cost to scale quadratically and hallucinations to compound. Serialize meaningful state, not raw history.

### Layer 4 — Add observability at the orchestration boundary, not inside it

AxonFlow's governance model (gateway/proxy mode) and LangSmith tracing both expose the same insight: instrument the transitions between agents, not the internals of each agent. What you need to see:

- Which agent was invoked, with what input
- Tool calls made and their outputs
- Decision points (routing, branching)
- Latency and cost per step
- Where the execution diverged from the happy path

### Layer 5 — Enforce hard bounds on execution

65% of teams that hit the wall were not enforcing:
- **Step caps** — max agent turns before hard stop (even 10 is plenty for most tasks)
- **Timeout per tool call** — per-tool SLA prevents one slow API from hanging the whole pipeline
- **Cost budgets** — token caps per pipeline run
- **Circuit breakers** — stop routing to a failing agent after N consecutive failures

## Evidence

- **Anthropic Engineering Blog:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Recommends the 5-tier ladder above and explicitly advises against building agentic systems when simpler solutions suffice. — https://www.anthropic.com/engineering/building-effective-agents

- **HN Ask (112 pts, 73 comments):** Practitioners report "AI agents are at least 90% hype" but also share real deployments: GitHub's Claude Code integration, Cursor's agent mode, and company-internal research pipelines. Key finding: the practitioners who shipped successfully either used minimal orchestration (1-2 agent types) or built custom on top of LangGraph. — https://news.ycombinator.com/item?id=42431361

- **HN Ask multi-agent orchestration (2025):** 11 production practitioners on framework choices and data passing. Majority "roll your own" with custom orchestrators. One cited Agno's isolation/decoupling as production-ready. Data passing via MongoDB + Redis combination was the most common pattern for teams that had scaled past 1000 agent runs/day. — https://news.ycombinator.com/item?id=47660705

- **Production comparison (18 months, 3 frameworks):** LangGraph leads with 90K+ GitHub stars. CrewAI fastest for prototypes. 65% of teams rewrote within 12 months — almost always because the abstraction hid a failure mode they needed to see. — https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/

- **GitHub Universe 2025 / Agent HQ:** GitHub announced Agent HQ — an open ecosystem for orchestrating any coding agent, unified around existing Git primitives (PRs, issues, git). Represents the enterprise shift from "build agents" to "orchestrate agents you've already built." — https://github.blog/news-insights/company-news/welcome-home-agents

- **AxonFlow (Show HN):** Self-hosted governance layer for LLM/agent workflows. Key insight from the team: once workflows leave demo phase, failures are rarely model issues — they're retries that accidentally repeat side effects, partial failures mid-workflow, permissions that differ per step. The answer is deterministic replay and step-level enforcement, not better prompts. — https://news.ycombinator.com/item?id=46692499

- **GitHub stars by orchestration model:** LangGraph (90K+), AutoGen (~32K), CrewAI (~26K) as of mid-2026. These are the three with enough ecosystem to staff. — https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html

## Gotchas

- **CrewAI's hierarchical manager is single-threaded** — if your manager agent becomes a bottleneck, you end up retrofitting parallelization into a system designed for sequential roles. Design for parallelism upfront.
- **LangGraph's state machine is not the same as deterministic execution** — LLM outputs at each node introduce non-determinism. "Replay" only guarantees deterministic input routing, not deterministic outputs. Budget for outputs changing between runs.
- **Agno's FastAPI runtime is a different operational model** — it assumes you want to deploy agents as HTTP services. If you want batch processing or event-driven invocation, you're fighting the defaults.
- **Roll-your-own means you own the retry logic, timeout logic, and observability** — and you'll hit every edge case the frameworks already solved. Only roll your own when you have a specific requirement the frameworks demonstrably can't meet.
- **65% rewrite rate means the first framework you pick is probably wrong** — treat your first production agent system as a prototype. Plan for the rewrite from day one: keep interfaces clean, state serializable, and agents swappable.
