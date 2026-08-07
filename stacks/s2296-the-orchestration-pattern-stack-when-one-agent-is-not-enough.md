# S-2296 · The Orchestration Pattern Stack — When One Agent Is Not Enough

When a single LLM call can't handle your problem, but spinning up five agents makes debugging impossible.

## Forces

- **Sequential chains are too rigid** — real tasks branch, retry, and depend on partial results, but a linear pipeline treats every step as a done deal
- **Agents are too chatty** — multi-agent systems that let agents freely negotiate add latency, cost, and non-determinism, and their reasoning paths become unobservable
- **Frameworks sell simplicity, then demand depth** — CrewAI's `crew.kickoff()` is easy until you need branching, approvals, or crash-safe resume; LangGraph's graph model is powerful but verbose from day one
- **60% of enterprise agentic pilots fail** — not from bad models, but from architectural choices made before the first line of agent code (linesncircles.com, March 2026)
- **The step budget is the one line that separates a working agent from a $47K bill** — November 2025: four LangChain agents ran for 11 days before anyone noticed (dev.to, waxell)
- **Context collapse kills pipelines** — an agent loses task context across multi-step pipelines; 22% of enterprise failures cite this (linesncircles.com)
- **Tool overload is a silent killer** — 13% of failures involve a single agent given 30+ tools with no priority routing (linesncircles.com)

## The Move

Pick the orchestration pattern that matches your actual control requirements, not the one that sounds most impressive. Start simple; escalate only when forced.

**Pattern 1 — Sequential Chain (lowest complexity):**
- Output of Model A feeds into Model B
- Use when tasks have clear linear dependencies; each step transforms data for the next
- Strength: simple, predictable, easy to debug
- Weakness: creates bottlenecks; no parallelism; one failure halts the entire pipeline
- Guard: always wrap with `max_steps`/`max_iterations` and `timeout` (eastondev.com)

**Pattern 2 — Router / Conditional Branching (escalate when branching is needed):**
- A classifier LLM or heuristic determines which downstream agent or tool receives the task
- LangGraph conditional edges are the idiomatic implementation: `should_approve` → `"human_review"` or `"auto_approve"`
- Enables fan-out (parallel sub-agents) + fan-in (merge results)
- Guard: set a per-branch step budget; otherwise the router can ping-pong between branches indefinitely

**Pattern 3 — ReAct Loop (the default for single agents with tools):**
- Think → Call tool → Observe result → Repeat until done
- "Most teams over-engineer this. They reach for Tree-of-Thoughts when a 30-line ReAct loop would have shipped on Tuesday." (Claudexia/Gist, 2026)
- Always implement `max_steps` as a hard global cap — not a soft alert
- **Critical gotcha**: the verifier stall. ReAct agents happily call a `verify_result` tool 20 times with slightly different arguments. Guard with a per-tool call cap, not only a global step cap. (dev.to, gabrielanhaia)
- SWE-agent (Princeton, 2024) is a canonical ReAct implementation: reads files, runs shell commands, edits code.

**Pattern 4 — Plan-and-Execute (escalate when steps must be stable across runs):**
- Generate the full plan up front, then execute steps sequentially (or in parallel if independent)
- Better for auditability and reproducibility than ReAct
- Separates planning LLM from execution LLM — reduces context overload per call
- InterviewLM case study: 8 specialized LangGraph agents, 100+ concurrent sessions, <2s p99 latency, 40% cost reduction via prompt caching (devstarsj.github.io, January 2026)

**Pattern 5 — Multi-Agent with Explicit Roles (escalate for complex workflows):**
- Each agent has a defined role, scoped tools, and a communication protocol
- Five real sub-patterns: Sequential Pipeline, Concurrent Parallel Analysis, Group Chat, Handoff (dynamic), Magentic/intelligent scheduling (eastondev.com)
- CrewAI idiomatic approach: `Process.sequential` for ordered handoffs, `Process.hierarchical` for manager-delegate
- For production requiring determinism and auditability: LangGraph as the orchestration backbone, with CrewAI crews inside individual nodes (myengineeringpath.dev)

**When to reach for a full framework vs. rolling your own:**
- Use LangGraph when: execution order matters, every transition must be auditable, or you need checkpointing (financial compliance, medical triage, KYC/AML — JPMorgan pattern)
- Use CrewAI when: coordination logic is straightforward and speed of development beats determinism (content pipelines, internal research automation)
- Use AutoGen when: multi-agent collaborative discussion is the core interaction (group chat patterns, negotiation scenarios)
- Roll your own (simple ReAct loop) when: you need <5 tools and no branching — a 30-line loop beats a 300-line graph definition (ideatomvp.ai, June 2026)

## Evidence

- **Blog post (Zylos Research, April 2026):** Three architectural schools for coordinating agents — DAG-based (explicit dependencies, deterministic), Event-driven (async pub/sub), Actor model (isolated state, message-passing). By 2025, naive LLM call chaining had "collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs." — https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns

- **Case study (InterviewLM via devstarsj.github.io, January 2026):** 8 specialized LangGraph agents deployed for 12 weeks, supporting 100+ concurrent sessions. Results: <2s p99 latency, 40% cost reduction via prompt caching, 4D evaluation scoring with evidence, $1.50 cost per session. — https://devstarsj.github.io/2026/03/28/multi-agent-ai-langgraph-crewai-production-guide-2026

- **Enterprise analysis (Gheware DevOps, April 2026):** JPMorgan-style LangGraph deployment pattern for banking (KYC/AML automation). Production Kubernetes requires Redis or PostgreSQL checkpointing, FastAPI agent endpoints, HPA, and governance boundaries baked into graph structure. — https://devops.gheware.com/blog/posts/langgraph-multi-agent-orchestration-enterprise-2026.html

- **Multi-framework comparison (Imperialis Tech, March 2026):** Framework choice drives determinism vs. flexibility tradeoff. "Gartner projects that by 2028, 70% of organizations building multi-LLM applications will use integration platforms to orchestrate agents." — https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production

- **HN-adjacent incident (dev.to, waxell, November 2025):** Four LangChain agents ran an unbounded loop for 11 days, billing $47,000. Root cause: step budget was instrumented as an alert, not enforced. — https://dev.to/waxell/the-47000-agent-loop-why-token-budget-alerts-arent-budget-enforcement-389i

## Gotchas

- **Most teams reach for multi-agent too early.** A single agent with 3–5 well-scoped tools beats a three-node graph that re-implements the same loop with extra latency (ideatomvp.ai)
- **Chains are DAGs; agents need cycles.** Orchestration earns its keep only when you need branching, parallelism, durability (resume after crash), or step-by-step auditability (ideatomvp.ai)
- **Orchestration ≠ prompt chaining.** The orchestration layer handles: task decomposition, inter-agent communication, state/context sharing, error handling, and resource allocation. These are distinct concerns that shouldn't be conflated into a single system prompt (odeaworks.com)
- **Per-tool call caps prevent verifier stalls.** Global step caps don't stop a ReAct agent from calling the same tool 20 times with reworded arguments. Add per-tool call limits in your state schema (dev.to)
- **Multi-agent group chat adds non-determinism.** When agents freely negotiate outcomes, reproducibility becomes nearly impossible. Use handoff patterns (explicit role → role handover) instead of open group chat for production systems (eastondev.com)
