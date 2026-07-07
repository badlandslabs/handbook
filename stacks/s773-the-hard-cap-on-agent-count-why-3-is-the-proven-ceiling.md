# S-773 · The Hard Cap on Agent Count: Why 3 Is the Proven Ceiling

Every team that gives an agent authority to create sub-agents hits the same wall: the agent fills the quota. Not because it is malicious, but because it rationally optimizes for coverage — and coverage looks like more roles.

## Forces

- **Delegation provokes proliferation.** Give an agent broad organizational authority and it will create a CTO, DevOps Lead, QA Engineer, Documentation Specialist, and a Helper Tester. This is not a bug — it is rational behavior given the task. The problem is the coordination overhead that follows.
- **Coordination scales super-linearly.** Three agents with defined boundaries need one handshake protocol. Twenty agents need N×(N-1)/2 relationship definitions. The productivity gain from specialization is eaten by the coordination graph.
- **Roles need non-overlapping mandates.** Agent productivity correlates with clarity of scope, not size of scope. The moment two agents can both answer the same question, you have priority conflicts and duplicated work.
- **Human review is the bottleneck.** More agents produce more outputs requiring human review. Beyond three parallel agents, the review queue overwhelms the speed advantage of parallelism.

## The Move

**Hard-cap at 3 roles. Design those 3 first. Treat any request to add a 4th as a refactor trigger, not a feature request.**

Three proven role archetypes that appear across documented production stacks:

- **Architect / Planner** — decomposes the task, decides what needs to happen, sequences the work. Do not let this role also execute.
- **Specialist / Executor** — does the thing. One specialist per domain. If you need a second specialist, the task is too broad — split it.
- **Validator / Reviewer** — checks output against requirements, catches hallucination, enforces format contracts. This role should never generate content, only evaluate it.

Coordination via **shared Markdown artifacts** (task files, decision logs) instead of inter-agent messaging. Artifacts are asynchronous, auditable, and human-readable — agents write to disk, other agents poll, humans can inspect.

## Evidence

- **HN Post:** A solo founder built a production SaaS using multiple Claude Code agents. Their first attempt: a "CEO agent" with broad authority to organize the project. Within hours it created 20 roles — CTO, DevOps Lead, QA Engineer, Documentation Specialist, Helper Tester — wrote memos, scheduled "alignment meetings," and caused a complete work stoppage. Lesson: "Agents will happily create organizational structures... you have to set hard constraints before delegating." — [Hacker News, yego, 2026](https://news.ycombinator.com/item?id=47245373)
- **Framework comparison:** LangGraph uses state machines, CrewAI uses roles, AutoGen uses conversations. All three frameworks achieve production results with 2–4 agents. CrewAI's role-based API was built for this constraint — but teams "may hit scalability limits within 6–12 months" when they try to scale beyond 3–4 roles without architectural redesign. — [Gheware DevOps AI Blog, 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Production lessons (2025):** The four categories that shipped from pilot to production — developer tooling, internal operations, research/analysis, and customer-facing support — all converged on tight, task-specific agent scopes. "Agents work where software engineering discipline works" — including discipline around scope boundaries. — [Technspire, December 2025](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **The "just one more role" trap.** After adding 3 roles, the next feature request always seems to need a 4th. It rarely does — it needs clearer boundaries on an existing role.
- **Hard-coding the cap is not enough.** The Architect/Planner role will try to create sub-agents if given task-decomposition authority. Either restrict tool access or inject the cap into the system prompt as an explicit constraint.
- **Artifact-based coordination sounds slow.** It is slower than in-memory messaging. It is also the only approach that survives agent crashes, enables human audit, and works without a shared runtime context.
- **Role overlap is worse than too many roles.** Three roles with clear mandates beat four roles with fuzzy mandates. The 3-cap only helps if mandates are non-overlapping.
