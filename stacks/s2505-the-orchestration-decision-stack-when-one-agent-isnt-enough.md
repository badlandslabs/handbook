# S-2505 · The Orchestration Decision Stack — When One Agent Isn't Enough

You've got a working single-agent system. It calls a model, uses a few tools, gets things done. Then a new requirement lands: this task needs to explore three things simultaneously, or route based on output type, or run until a condition is met. Now you need multiple agents cooperating. But adding agents doesn't automatically add capability — it adds complexity, cost, and failure surface. The orchestration decision is when to go multi-agent, and how.

## Forces

- **Multi-agent overhead is real.** Anthropic's internal multi-agent research system consumed ~15× more tokens than a single-agent chat interaction. The cost is the price of admission — and you only pay it back if the task actually benefits from parallel decomposition.
- **Two-agent patterns dominate production.** ~60% of production AutoGen deployments use a single assistant + user proxy pair. Multi-agent group chats account for <15%. The industry defaulted to simple before it defaulted to complex.
- **Frameworks vs. raw APIs.** The most upvoted take from the HN discussion of Anthropic's building-effective-agents post: *"It's insane that people use whole frameworks to send what is essentially an array of strings to a webservice."* But the counterpoint: when you need state machines, branching, and crash-safe resume, frameworks earn their keep.
- **The graph becomes the liability.** The same community that celebrated LangGraph's expressiveness warns about the "unmaintainable graph" failure mode — prompts and edges that no one fully understands after six months.

## The Move

**Know the four patterns. Pick the simplest one that fits. Treat orchestration complexity as a cost, not a feature.**

### The four orchestration patterns (Anthropic's taxonomy, Dec 2024)

1. **Prompt chaining** — sequence of LLM calls where each output feeds the next. Use when: the task is inherently serial and each step depends on the prior result. Lowest overhead. Example: extract → transform → validate.
2. **Routing** — a classifier or intent model directs the request to a specialized handler. Use when: input types are distinct and require different logic paths. Example: classify a customer message into billing / technical / feedback, then dispatch.
3. **Parallelization** — multiple LLM calls run simultaneously on the same input. Use when: sub-tasks are independent and can be merged. Example: run three search queries in parallel, then synthesize results.
4. **Orchestrator-workers** — a lead agent decomposes a task, spawns specialized subagents for each sub-task, then synthesizes their results. Use when: the task has unpredictable structure requiring dynamic decomposition. Highest overhead. Example: open-ended research.

### Framework selection heuristic

| Scenario | Recommended approach |
|----------|--------------------|
| <5 tools, linear flow | Direct API calls, no framework |
| Need state persistence across steps | LangGraph (state machine with checkpointing) |
| Multiple role-based agents that talk | CrewAI (fast to prototype) → LangGraph (when you need production resilience) |
| Enterprise / Windows team | AutoGen 0.4 (Jan 2025, .NET support, no-code Studio) |
| Long-running coding agents across repos | Custom orchestration (Optio-style: K8s pods + git worktrees + LLM code execution) |

### Production guardrails for multi-agent systems

- **Token budget per agent turn.** Set a hard cap. Anthropic's research system found that subagents naturally compress findings when they know context windows are finite — it forces discipline.
- **Max-turn limits with escalation.** Every agent loop needs a circuit breaker. Most failure modes (looping, hallucinations, dead-ends) manifest as excessive turns before they manifest as errors.
- **Separate context per subagent.** Anthropic's research system gives each worker a fresh context — they don't inherit the full conversation. This prevents context pollution and lets parallelism actually work.
- **Cost monitoring at the orchestration layer.** Multi-agent AutoGen workflows can run 3–5× more expensive than single-call LLM workflows if agent loops aren't capped. Track cost per task, not per call.

## Evidence

- **Engineering blog:** Anthropic published their four-pattern taxonomy and multi-agent research system architecture — including the 90.2% performance gain vs. single-agent on internal evaluation, and the 15× token multiplier — on their engineering blog, June 2025. — [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Engineering blog:** The same team published the canonical decision framework (workflows vs. agents, when to use each pattern) in December 2024, which became the most-upvoted HN post on AI agents in 2025 (543 points, 88 comments). — [Anthropic: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents) | [HN Discussion](https://news.ycombinator.com/item?id=44301809)
- **Industry analysis:** AutoGen 0.4 (Jan 2025) drove enterprise adoption with event-driven architecture, AgentChat high-level API, and AutoGen Studio. Two-agent patterns cover ~60% of production deployments; top ROI use cases are code review, document extraction, support triage, and data analysis. — [Second Talent: How Enterprises Are Using AutoGen in 2026](https://www.secondtalent.com/resources/how-enterprises-are-using-autogen)
- **Community synthesis:** Reddit/r/LangChain consensus (2026): "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." LangGraph's value is state machine expressiveness and checkpointing — not ease of use. — [Idea to MVP: LangGraph Agent Orchestration Patterns 2026](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)
- **Open-source:** DoorDash's Optio orchestrates Claude Code and Codex agents across Kubernetes, using git worktrees for isolation and managing the full ticket→PR lifecycle. 88 points on HN, validated the pattern of agent-as-worker in a production-grade system. — [Show HN: Optio – Orchestrate AI coding agents in K8s](https://news.ycombinator.com/item?id=47520220)

## Gotchas

- **Multi-agent doesn't mean better.** If the task doesn't decompose into parallel, independent directions, you're paying the 15× token cost without the performance gain. Anthropic's own system only activates subagents when research breadth is needed.
- **The framework trap.** Teams adopt LangChain/LangGraph/CrewAI for prototyping, then find the abstraction layer fights them when they need custom error handling, observability, or specific tool integrations. Simon Willison's takeaway: *"It's essentially an array of strings to a web service"* — the overhead may not be worth it for simple flows.
- **Context window pressure.** As more agents run, context windows fill with intermediate outputs. Without deliberate compression and per-agent context boundaries, performance degrades and costs compound.
- **Evaluation is the bottleneck.** Across AutoGen enterprise deployments, the limiting factor wasn't the framework — it was hiring engineers who could build reliable evaluation pipelines for agent behavior. Orchestration without eval is guesswork at scale.
