# S-864 · The Orchestration Pattern Stack — When Your Agent Chain Becomes a Black Box

You have two LLM calls chained together. Then three. Then a router. Then a parallel branch. Three engineers later, nobody can trace a single user request through the system, debug a failure, or predict the cost. The orchestration is real — but the visibility is gone. This is the orchestration pattern problem, and it has nothing to do with which framework you chose.

## Forces

- **Frameworks sell, primitives pay.** Every orchestration framework (LangChain, CrewAI, Microsoft Agent Framework, OpenAI Agents SDK) advertises ease of use. But teams with real production systems consistently report that framework abstractions obscure the one thing that matters: understanding what your LLM is actually doing and why. — [Anthropic Engineering: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **The pattern determines the ceiling, not the framework.** The Microsoft Agent Framework supports four graph-based patterns (sequential, concurrent, handoff, group collaboration) and Google ADK supports the same four. But the pattern you choose — which is an architectural decision, not a code decision — determines whether your system scales to 50 agents or breaks at five. — [Markaicode: Agent Architecture with Anthropic](https://markaicode.com/architecture/agent-architecture-with-anthropic/)
- **Memory and tool design are invisible until they fail.** Across engineering teams, the pattern holds without exception: model and framework choices get debated. Memory architecture, RAG design, and tool API design decide the outcome — and they are where production systems diverge from demos. — [Azumo: AI Agent Architecture Patterns](https://azumo.com/artificial-intelligence/ai-insights/ai-agent-architecture)
- **Custom stacks win in production.** On HN's multi-agent orchestration thread, multiple production teams reported rolling their own orchestration layers rather than using frameworks. One said it plainly: "There's absolute 0 framework out there that's good enough for serious work." — [HN: Multi-Agent AI Workflow Orchestration in Production](https://news.ycombinator.com/item?id=47660705)

## The Move

Pick an orchestration pattern based on the task shape, not the framework's feature list. Then implement it with the minimum viable abstraction.

**Anthropic's four-pattern taxonomy (December 2024) is the most widely-cited framework-independent reference:**

- **Prompt chaining** — sequential steps where each LLM call feeds the next. Use when a task decomposes into fixed subtasks that must run in order. Lowest latency overhead. Highest brittleness if any step fails.
- **Routing** — a classifier or LLM decides which specialized path handles the request. Use when a single model handles multiple task types that need different tools or instructions. Model routing (fast-small model for classification → capable model for execution) cuts cost significantly.
- **Parallelization** — multiple LLM calls execute simultaneously on subtasks that don't depend on each other. Use for tasks that genuinely decompose into independent branches. The wins are real but bounded by Amdahl's law.
- **Orchestrator-evaluator** — a central LLM coordinates subtasks, decides what to call, and evaluates results before proceeding. Use when task decomposition is non-deterministic and depends on intermediate results. This is where "agents" actually begin per Anthropic's definition.

**Three concrete implementation patterns from production systems:**

- **Git worktree isolation + shared SQLite** — each agent runs in an isolated git worktree with its own venv and hooks, coordinated through a shared SQLite WAL database. No framework. Works for up to ~10 parallel agents. Beyond that, coordination overhead dominates. — [HN Ask: Multi-Agent Orchestration Setup](https://news.ycombinator.com/item?id=48559933)
- **Pipeline with explicit roles** — Worker → Reviewer → Test → Documenter, each as a separate LLM instance with a narrow tool set. A coordinator agent routes issues and escalates to a more capable model on repeated failures. — [OpenSwarm: Multi-Agent Claude CLI Orchestrator](https://github.com/Intrect-io/OpenSwarm)
- **Model escalation with semantic caching** — a small fast model handles routing and early steps; a capable model is invoked only when confidence is low or a hard step is reached. Tool results are cached semantically so repeated questions don't re-call the LLM. — [Microsoft Agent Framework docs](https://github.com/microsoft/agent-framework)

**The rule that keeps teams out of trouble:**

Start with a single LLM call. Only add complexity when you have evidence that the simpler approach fails. If you reach for orchestrator-evaluator when a router would do, you have added latency, cost, and debugging complexity with no corresponding gain.

## Evidence

- **Anthropic Engineering (Dec 2024):** After working with "dozens of teams building LLM agents across industries," Anthropic concluded that the most successful implementations use "simple, composable patterns rather than complex frameworks." Their cookbook shows all four patterns implemented in under 50 lines of code each. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents), [https://platform.claude.com/cookbook/patterns-agents-basic-workflows](https://platform.claude.com/cookbook/patterns-agents-basic-workflows)
- **OpenSwarm (Apr 2025, 816 GitHub stars):** An autonomous AI dev team orchestrator using Worker/Reviewer/Test/Documenter pipeline with Claude Code CLI, LanceDB for long-term memory, model escalation (Haiku → Sonnet on repeated failures), and Discord for status updates. Real integration with Linear and GitHub — not a toy. — [https://github.com/Intrect-io/OpenSwarm](https://github.com/Intrect-io/OpenSwarm)
- **HN production thread (early 2026):** Teams reporting custom Node.js + Express + V8 isolates, LangGraph with custom routing layers, and git worktree-based agent isolation. Consensus: "agent orchestration is the future, but it's not there yet" — meaning the tooling is still immature and operational discipline matters more than tooling choice. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705), [https://news.ycombinator.com/item?id=48559933](https://news.ycombinator.com/item?id=48559933)

## Gotchas

- **Framework lock-in hides failure modes.** LangChain, CrewAI, and similar frameworks simplify initial prototyping but add abstraction layers that make LLM prompts, tool calls, and response parsing opaque. When a production system fails at 2am, debugging through a framework's internal abstractions costs hours.
- **Orchestrator-evaluator is not the default pattern.** Anthropic explicitly states that agents (as they define them — dynamic, self-directed) are appropriate when "tasks cannot be usefully decomposed into fixed paths" and "the agent spends non-trivial time acting autonomously." Most tasks don't meet this bar. Teams reach for it too early.
- **Token budgets prevent runaway loops.** A single user request can trigger 10+ LLM calls in an orchestrator pattern. Hard-code a maximum iteration count and terminate with a human-in-the-loop signal when it's reached. Without this, a looping agent can exhaust a day's API budget in seconds.
