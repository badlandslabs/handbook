# S-1034 · The Role Fence Stack — When Your Multi-Agent System Keeps Tripping Over Itself

You built a multi-agent pipeline. Each agent can call any other agent. Every agent has full system context. The agents deadlock, duplicate work, step on each other's outputs, and you spend more time watching them argue than getting anything done.

The failure isn't that you added agents. The failure is that you gave them no fences.

## Forces

- **Collaboration feels like a feature.** Giving agents shared context and open call graphs feels natural — it mirrors how humans work. In practice, it creates tight coupling, circular dependencies, and output pollution.
- **Single-agent ceilings are brutal.** A single LLM agent produces vague, unusable recommendations 98.3% of the time in complex tasks (MyAntFarm.ai, 348 trials). But naively adding agents without structure doesn't fix it — it just multiplies the vagueness.
- **Role fidelity beats role flexibility.** Agents that stick to a narrow, well-defined role outperform agents with open-ended access to the full problem space. The constraint is the feature.
- **Coordination overhead is real.** The moment you add a second agent, you inherit a new class of failure modes: circular calls, split-brain outputs, and context bleed between agents. These don't show up in demos.

## The move

Structure multi-agent systems as **role-fenced pipelines** — tight role boundaries, explicit handoff protocols, and isolation by default. Three patterns that work in production:

- **Static role assignment with exclusive workspaces.** Give each agent a dedicated file tree, a narrow toolset, and zero access to other agents' output directories. The Claude Code 3-agent setup (HN, growity.ai) uses this: backend agent gets `/workspace/back/` + read-only `/workspace/docs/`, frontend gets `/workspace/front/` + read-only docs, CEO gets docs only. No agent overwrites another. The HN author notes: "I accidentally gave it the full workspace and it created engineering debt that slows them at the worst moment." One week of isolation > six months of cleanup.
- **Sequential handoff with output gates.** Chain agents so each one completes its stage and produces a structured output (Pydantic model or markdown spec) before the next agent starts. The Agent Swarm approach (desplega.ai) adds a propagation step: the lead agent writes a summary to shared memory after each task, so downstream agents don't re-derive context. CrewAI production guidance recommends `Process.sequential` as the default flow and `output_pydantic` for critical outputs to validate stage boundaries before handoff.
- **Explicit collaboration only via orchestration layer.** The orchestrator decides who calls whom, in what order, and with what context. Agents never call each other directly. The Agent Swarm uses a lead/worker architecture where workers claim tasks, report through task comments, and the lead reviews results. The MyAntFarm.ai study's multi-agent condition used dedicated analyst and evaluator agents with separate prompts and no direct inter-agent calls — achieving 100% actionable recommendations versus 1.7% for the single-agent condition.

## Evidence

- **arXiv paper (348-trial controlled study):** MyAntFarm.ai tested single-agent vs 3-agent incident response. Single-agent produced vague actions ("investigate the issue") 98.3% of the time. Multi-agent with role-fenced analyst/evaluator agents achieved 100% actionable rate, 80× specificity improvement, 140× correctness improvement. Deterministic execution (fixed seed, temperature, model). — [https://arxiv.org/abs/2511.15755](https://arxiv.org/abs/2511.15755) | [https://github.com/Phildram1/myantfarm-ai](https://github.com/Phildram1/myantfarm-ai)
- **HN discussion (production scaling thread):** Engineers evaluating LangGraph for production converge on: keep the graph small, prompts concise, nodes and tools atomic in function. One user reports: "I used n8n with one of the exact setups shown — costs $3 and at least 3 minutes for a simple question." Simplest architecture wins. — [https://news.ycombinator.com/item?id=44909029](https://news.ycombinator.com/item?id=44909029)
- **HN Show: Multi-agent Claude Code:** A solo founder built a SaaS with 3 Claude Code agents (backend/frontend/CEO). After months of open-workspace chaos, they restricted each agent to its own directory. "I accidentally gave it the full workspace and it created engineering debt that slows them at the worst moment." Result: working production SaaS (growity.ai) with clean separation. — [https://news.ycombinator.com/item?id=47245373](https://news.ycombinator.com/item?id=47245373)
- **LangChain blog — Top 5 LangGraph agents in production (2024):** LinkedIn SQL Bot, Replit agent, Klarna (80% faster query resolution, 70% support automation), Lyft customer support, Realm-X. Pattern: narrow, vertical, highly controllable agents with custom cognitive architectures — not general-purpose autonomous agents. — [https://www.langchain.com/blog/top-5-langgraph-agents-in-production-2024](https://www.langchain.com/blog/top-5-langgraph-agents-in-production-2024)
- **CrewAI production best practices:** Version and freeze workflow, validate outputs before writing to storage, define token guardrails per run, log which step is slow or fails, design fallback paths for model failure. — [https://benxhub.com/en/blog/crewai/09-production-best-practices](https://benxhub.com/en/blog/crewai/09-production-best-practices)
- **HN Show: Agent Swarm:** OSS multi-agent system using personal/shared SQLite memory, SOUL.md identity files, and a lead agent that propagates learnings across workers. ~95% of closed PRs in their repo done by the swarm. — [https://news.ycombinator.com/item?id=47165046](https://news.ycombinator.com/item?id=47165046)

## Gotchas

- **The "full context" trap.** Giving agents full workspace or full conversation history feels helpful. It isn't. It creates context bleed and output pollution. Restrict access by default, expand only when isolation causes a specific, observed failure.
- **Direct inter-agent calling creates circular dependencies.** Agents calling each other on demand sounds flexible but produces deadlocks and output races. Route all handoffs through an orchestrator.
- **Evaluation doesn't transfer across architectures.** An eval that works for a single-agent system will give misleading results for a multi-agent pipeline. The MyAntFarm.ai study used separate validity, specificity, and correctness dimensions — single-agent systems pass validity (technically feasible actions) but fail specificity (concrete next steps) and correctness (right solution).
- **More agents ≠ more capability.** Two well-fenced agents beat five loosely coupled ones. The failure mode isn't under-automation — it's mis-automation: spreading vague agents across a pipeline just propagates vagueness faster.
- **Version the workflow, not just the code.** CrewAI's production guidance and the behavioral versioning problem (S-1033) converge here: agent + task + prompt must be traceable together. A prompt change can break a multi-agent handoff that neither unit test nor integration test catches.
