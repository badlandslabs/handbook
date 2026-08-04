# S-2116 · The Orchestration Stack

When you reach for a multi-agent framework and the prototype works — but production reveals that 40% of agentic pilots fail within six months, and the teams that shipped successfully did it with fewer agents, not more.

The instinct to reach for orchestration is usually wrong, or at least premature. The field has consolidated around a few patterns, and the teams winning are the ones who picked the right pattern for the right reason — not the flashiest one.

## Forces

- **The complexity tax compounds with agent count.** Every additional agent multiplies coordination overhead, state management, failure modes, and observibility gaps. "Multi-agent" sounds sophisticated; in practice, it often means "distributed system with a new category of bugs."
- **Simple chains dominate production by a wide margin.** LangChain's 2025 production survey found 73% of deployed systems use chains; only 12% use full agents. The median production agentic workload is not an army of bots — it's one LLM call chained to the next.
- **Princeton NLP put a number on it.** On 64% of benchmarked tasks, a single agent matched or outperformed multi-agent systems given identical tools and context. The multi-agent premium — 2.1 percentage points of accuracy — came at roughly double the cost.
- **The 40% pilot failure rate has a consistent cause.** GitHub's 2026 analysis found multi-agent workflow failures trace to missing structure, not model capability. Agents make implicit assumptions about state, ordering, and validation that break in production unless everything is explicit.
- **Context windows are still the binding constraint.** Single-agent systems hit ceilings on long tasks. Multi-agent systems escape this by distributing context across parallel agents — the lead agent delegates to workers who each hold their own context window, then condense results back.

## The Move

Start with chains. Escalate to orchestration only when you've hit a concrete ceiling.

**The orchestration maturity ladder:**

1. **Chain** — Sequential LLM calls with fixed steps. Use for: summarization, translation, structured extraction, any task where the path is known.
2. **Router** — A classifier or heuristic routes the input to the right handler. Use for: routing user requests to specialized paths, dynamic tool selection.
3. **Parallel (map-reduce)** — Fan out identical work to multiple agents, merge results. Use for: gathering diverse perspectives on a topic, parallel web searches.
4. **Supervisor + Specialists** — One lead agent decomposes a task and dispatches subtasks to specialized workers, then integrates. This is the most common production multi-agent pattern and accounts for roughly 70% of production deployments. The supervisor pattern is simple, debuggable, and maps cleanly to LangGraph's state machine model.
5. **Hierarchical / Crew** — Multiple supervisors at different levels. Reserve for genuinely complex domains where a second-level coordinator earns its overhead.

**The ReAct loop vs. Plan-and-Execute distinction:**
- **ReAct** (think → act → observe → repeat): Good when the search tree is small and the next step genuinely depends on the previous result. Think: refund flows, coding agents, anything interactive. Expensive — every step is an LLM call.
- **Plan-and-Execute** (plan first, then execute steps without re-planning): Good for complex multi-step goals where the plan is stable. Planner decides what to do; executors run the steps. Saves tokens — executors use cheaper models and don't re-think.
- **Reflection** (act → evaluate → revise): The agent evaluates its own output against criteria and loops to fix it. Best for tasks with verifiable outcomes: code that should pass tests, content that should meet a rubric.

**On frameworks:**
- CrewAI: Fast to prototype. Role-based agents with clear intent. But it treats orchestration as a chat transcript, not a state machine — branching, approvals, and crash-safe resume become painful.
- LangGraph: Explicit state machine. Every node is a step, every edge is a transition. Verbose to write, but resumable after deploys, auditable step-by-step, and it scales to real production complexity.
- AutoGen: Conversational agent model. Best for agent-to-agent dialogue patterns. Weaker for structured pipelines with approval gates.
- The right answer for most teams: direct LLM API calls + Python. Anthropic's engineering team ships agents this way. Frameworks add abstraction tax; for simple chains and routers, the tax is not worth it.

## Evidence

- **Anthropic engineering post:** "The most successful implementations use simple, composable patterns rather than complex frameworks." Their own Research feature — a multi-agent system with a lead agent and parallel workers — emerged from the finding that distributed context windows solve the single-agent ceiling problem, not from framework enthusiasm. Token usage explained 80% of performance variance on BrowseComp benchmarks; parallel execution enabled breadth-first exploration. — [Anthropic · "How we built our multi-agent research system"](https://www.anthropic.com/engineering/multi-agent-research-system) (Jun 2025)

- **GitHub Blog analysis:** Multi-agent workflow failures stem from missing structure. Three engineering patterns make agent systems reliable: (1) explicit interfaces between agents, (2) structured data formats for agent communication, and (3) validation at each handoff. Appropriate use cases: codebase maintenance and dependency updates, automated code quality checks and refactors, spec-driven feature implementation, issue and PR triage. — [GitHub Blog · "Multi-agent workflows often fail. Here's how to engineer ones that don't"](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/) (Feb 2026)

- **LangChain production survey + Turion.ai field note:** Simple chains handle 80% of production use cases. Agent-based systems cost 3–5x more in token usage than equivalent chains. The supervisor + specialists pattern — one agent decomposes and routes, specialists execute — is the most common production pattern and the most debuggable. 40% of multi-agent pilots fail within six months of production deployment, not because the systems don't work but because teams pick the wrong orchestration pattern or the right pattern without understanding how it breaks. — [Agentika · "LLM Orchestration Patterns That Actually Work"](https://agentika.uk/blog/llm-orchestration-patterns.html); [TURION.AI · "Multi-Agent Orchestration Infrastructure: Lessons from Production"](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production) (Mar 2026)

- **Community migration pattern:** Builders who shipped with CrewAI for speed are posting migration stories to LangGraph once they hit branching, approval gates, or the need for crash-safe resume. "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." — [Idea to MVP · "Agent Orchestration with LangGraph: Patterns, Production Gotchas"](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026) (Jun 2026)

## Gotchas

- **Starting with a framework is the wrong default.** Anthropic's own engineers recommend starting with direct API calls. Add orchestration infrastructure only when you've identified a concrete constraint chains can't solve.
- **The fan-out fan-in trap.** Sending 10 subagents in parallel feels efficient. In practice, you need a merge strategy, a timeout policy, and a partial-failure plan. Parallelism without structure is just concurrent chaos.
- **"We need more agents" is usually a symptom, not a solution.** When a system fails, the reflex is to add a reviewer agent, a validator agent, a coordinator. This compounds cost and makes debugging harder. Fix the existing agent before adding another.
- **The supervisor can become the bottleneck.** If the lead agent in an orchestrator pattern is doing too much reasoning about what to route where, you've built a fragile router. Make task decomposition deterministic where possible — use rules or classifiers for routing, save LLM judgment for the actual task.
- **Token budget management across agents is an unsolved ops problem.** When subagents run in parallel with different context windows, you need explicit token budgets per agent and a strategy for what happens when a result is too large to fit back in the lead agent's context.
