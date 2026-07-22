# S-1494 · The Orchestration Topology Stack — When the Pattern You Picked Destroys Your Latency Budget

You reach for a multi-agent system because the task is complex. You wire up a swarm or hierarchical topology because it feels structured. Six months later your P99 latency is 47 seconds, your token bill is $1.80 per conversation, and two agents are looping forever in a handoff cycle. The individual agents work fine. The orchestration topology is wrong for the workflow type. The fix is not better agents — it is picking the right topology.

## Forces

- **Pattern choice is irreversible.** Once your agents are wired into a topology, changing it is a rewrite. Most teams pick the pattern that feels most "agentic" rather than the one that fits their actual workflow characteristics.
- **Complexity compounds non-linearly.** A swarm of 5 agents has 20 possible interaction paths. A supervisor chain of 5 has 5. The complexity of governance, observability, and failure handling scales with topology complexity, not agent count.
- **Framework choice constrains topology.** LangGraph makes graph-based (sequential/router/evaluator-optimizer) patterns natural. CrewAI makes role-based team topologies natural. AutoGen makes conversational patterns natural. Picking the wrong framework forces you into awkward workarounds.
- **Agents exploit available authority.** Given organizational scope, agents will spawn sub-agents, create meetings, and generate work — not out of malice, but because they optimize for the goal you gave them. Hierarchical authority without hard boundaries produces agent proliferation.

## The Move

Match your orchestration topology to your workflow's structural characteristics. The evidence from 200+ enterprise deployments points to six core topologies with distinct cost, latency, and complexity profiles. The critical insight: start with the simplest topology that fits your workflow, and upgrade only when concrete metrics demand it.

**Topology selection guide:**

- **Sequential pipeline** — tasks with a strict dependency chain (analyze → draft → review → deliver). Lowest latency variance. Easy to debug. Scales poorly with long chains.
- **Parallel fan-out** — tasks where the same input needs independent processing by multiple specialists (extract entity A + extract entity B + extract entity C, then aggregate). Latency is bounded by the slowest branch. Good for embarrassingly parallel work.
- **Supervisor** — one central agent routes subtasks to specialized workers and synthesizes results. Best when task routing logic is stable and the synthesis step is the core value. Single point of failure; add retry budgets.
- **Router (tagging/classification-first)** — a fast classifier determines which agent or pipeline handles the request. Cuts cost 30–60% by avoiding expensive agents on simple queries. Classification accuracy is the critical quality gate. Production teams report this as the single highest-leverage optimization.
- **Hierarchical (boss/worker)** — a supervisor delegates to multiple tiers of specialized workers. Scales to 20+ agents. Introduces coordination overhead and context-passing complexity between tiers. Right for genuinely multi-domain problems, not just "more agents."
- **Evaluator-optimizer loop** — an agent produces output, a reviewer evaluates it against criteria, the original agent iterates. Best for quality-critical outputs (code, legal text, creative) where one-shot generation is insufficient.

**The production hybrid:** Most real systems combine 2–3 topologies. A common pattern: Router (classify intent) → Sequential or Parallel (process) → Evaluator (validate quality). Each boundary is a natural checkpoint for human-in-the-loop or circuit breakers.

**Tool choice and topology co-evolve.** MCP (Model Context Protocol) standardizes tool access for agents. A2A (Agent-to-Agent Protocol) handles peer coordination. These are complementary, not alternatives. Use MCP for tool calls within a topology; use A2A for cross-agent negotiation in peer-to-peer or hierarchical topologies.

## Evidence

- **Enterprise study:** Analysis of 200+ enterprise agent deployments found 57% of failed projects had root causes in orchestration design rather than individual agent capability. 40% of multi-agent pilots fail within 6 months, primarily due to topology misfits. — *[AnhTu.dev, "AI Agent Orchestration — 6 Patterns for Production," April 2026](https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121)*

- **Retail case study:** A company built a 7-agent swarm that demoed well but failed in production with 47-second response times and $1.80/conversation token cost. Root cause: agents trapped in a handoff loop (tone-checker → escalation → policy → tone-checker). The swarm topology was wrong for a workflow with a clear authority hierarchy. Switching to a supervisor pattern resolved it. — *[Metacto, "AI Agent Orchestration Patterns: A Production Guide," 2026](https://www.metacto.com/blogs/ai-agent-orchestration-patterns)*

- **HN production report:** A developer building growity.ai (Telegram Ads automation SaaS) created a "CEO agent" with broad organizational authority. Within hours it spawned 20 sub-roles (CTO, DevOps Lead, QA Engineer, etc.), which then created meetings, memos, and brainstorming sessions — work stoppage from coordination overhead. Lesson: agents given organizational scope will exploit it. Fixed by constraining the orchestration to exactly 3 roles (Architect, Builder, Reviewer) with a thin Markdown-based handoff protocol. — *[HN Show HN, "Multi-agent Claude Code setup – 3 roles, Markdown coordination, Docker," 2026](https://news.ycombinator.com/item?id=47245373)*

- **Production HN thread:** Multiple engineers building real systems reported that the pattern holding up in production is bounded task ownership (agents own clearly-scoped tasks end-to-end: research → draft → send → parse reply) with a thin orchestration layer routing based on reply classification. Classification accuracy is both the hardest and most important quality gate. — *[HN Ask HN, "How are you orchestrating multi-agent AI workflows in production?" 2025](https://news.ycombinator.com/item?id=47660705)*

- **Anthropic guidance:** The most successful implementations across dozens of industries used simple, composable patterns implementable in a few lines of code. Frameworks create abstraction layers that obscure prompts and responses, making debugging harder. Only add framework complexity when truly needed. — *[Anthropic Engineering, "Building Effective Agents," December 2024](https://www.anthropic.com/engineering/building-effective-agents)* — discussed at *[HN, 543 points, 88 comments, June 2025](https://news.ycombinator.com/item?id=44301809)*

- **Framework comparison (2026):** LangGraph for fine-grained control and production; CrewAI for fastest prototyping with role-based teams; AutoGen moved to maintenance mode October 2025. A common migration path: prototype in CrewAI, migrate to LangGraph for production. — *[Gheware DevOps Blog, "LangGraph vs CrewAI vs AutoGen: Complete AI Agent Framework Comparison 2026," January 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)*

## Gotchas

- **Don't reach for multi-agent when single-agent + tools suffices.** Anthropic's data shows most successful deployments are single-agent with tool access. Multi-agent introduces coordination overhead that most problems don't justify.
- **Don't pick a topology before understanding your failure modes.** Each topology fails differently: supervisor has a single point of failure; hierarchical has coordination overhead; swarm has emergence complexity. Design for the failure mode, not just the happy path.
- **Classification (router pattern) is the hardest part, not the easiest.** Teams underestimate how much the quality of their router determines overall system quality. Invest in eval data for your classifier proportional to its decision stakes.
- **Context passing between agents is a design decision, not an implementation detail.** Every handoff is an opportunity for information loss or distortion. Define explicitly what state travels across each boundary.
- **AutoGen is in maintenance mode.** As of October 2025, AutoGen is no longer actively developed. Factor this into long-term architecture decisions.
