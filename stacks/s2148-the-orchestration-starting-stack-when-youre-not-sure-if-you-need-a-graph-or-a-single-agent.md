# S-2148 · The Orchestration Starting Stack: When You're Not Sure If You Need a Graph or a Single Agent

You have a task that a single LLM call can't reliably finish. You reach for "an agent" and immediately face a fork: a three-node LangGraph, a CrewAI crew, an OpenAI Agents SDK handoff chain — or just a better-scoped prompt with a few tools. You have no production trace, no cost baseline, and no idea which failure mode you'll hit first. The tooling is mature enough to ship something, but not opinionated enough to tell you what to build. This is the orchestration starting problem: choosing the right control structure before you've seen the failure modes that justify it.

## Forces

- **Orchestration adds non-determinism at every fork.** Every branch point, worker spawn, and handoff is an LLM output — the same input can produce different control flows across runs. Teams that skip this cost in prototyping discover it in production debugging.
- **The simplest solution is usually a single augmented LLM, not a multi-agent system.** Anthropic's production playbook explicitly recommends defaulting to a single LLM call with retrieval and in-context examples. The community consensus on r/LangChain and X in 2026 is that most teams reach for multi-agent orchestration 6–12 months too early.
- **Framework choice shapes what you can change later.** A CrewAI demo ships fast but becomes a rewrite when you need pause/resume, branching on confidence, or crash-safe recovery. A LangGraph graph is more upfront work but survives Thursday's deploy intact.
- **Context management is the real bottleneck, not model capability.** Microsoft's Azure SRE team reduced their agent from 100+ tools and 50+ specialized agents to 5 core tools — and reliability improved. Leaky pipelines (stages forwarding accumulated context) bloat context windows and silently degrade downstream agents.
- **Tool count and tool scope are different decisions.** More tools means more options for the LLM but also more surface area for hallucinated tool calls. The question is not "how many tools" but "how tightly scoped is each tool's contract."

## The move

Start with the simplest thing that could work, then evolve to explicit orchestration only when a specific complexity force demands it. Use this decision ladder:

1. **Single augmented LLM** — One model call, retrieval, 3–5 tightly scoped tools. If this finishes the task with acceptable cost and latency, stop. Anthropic's baseline for production is this, not a graph.
2. **Prompt chaining** — Sequential steps where each LLM call's output is the next call's input. Each stage emits a clean, scoped output (not the accumulated context). Add input validation between every stage — without it, a malformed output from stage 3 produces plausible-looking garbage from stage 5.
3. **Parallel fan-out / fan-in** — Multiple agents or LLM calls run simultaneously on the same input, results merge downstream. The key discipline: each worker should receive only the minimal context it needs, not the full accumulated state. This is the anti-pattern break for "leaky pipelines."
4. **Routing** — A classifier or LLM decides which path to take (different tools, different agents, different model tiers). Routing is the first place where orchestration becomes stateful — you need to track which branch was chosen.
5. **Orchestrator-worker** — A central LLM dynamically decomposes tasks and delegates to workers. The key tradeoff: subtasks are not pre-defined, they are determined by the orchestrator at runtime, which means worker count and cost vary per run. Add a hard cap on maximum workers both in the orchestrator's prompt and programmatically in the dispatcher.
6. **Evaluator-optimizer loop** — An agent produces output, a critic evaluates it, and the agent iterates until a threshold is met. The trap: without an explicit iteration cap, degenerate reasoning loops consume budget indefinitely.

**Framework selection heuristic:**
- CrewAI for rapid prototyping with role-based agents → ships a working demo in an afternoon
- LangGraph when you need branching, pause/resume after crashes, or crash-safe graph traversal → survives production deployments
- OpenAI Agents SDK for lightweight multi-agent with built-in handoffs, guardrails, and tracing → successor to the deprecated Assistants API (sunset August 26, 2026)
- Custom orchestration only when all three frameworks are too constraining — and only after you have production traces proving the constraint

## Evidence

- **Anthropic engineering blog:** Production playbook outlines 6 orchestration patterns (augmented LLM, prompt chaining, routing, parallelization, orchestrator-worker, evaluator-optimizer) with the explicit recommendation to default to the simplest — and the observation that augmented LLMs actively generate their own search queries and select appropriate tools, making this more capable than earlier frameworks — [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Microsoft Azure SRE team:** Built an internal SRE agent, started with 100+ tools and 50+ specialized agents, collapsed to 5 core tools and a handful of generalists, saw reliability improve. Key insight: "don't fight the model's existing knowledge — lean on it" and "context windows are the agent's RAM" (citing Karpathy). The dominant insight was that disciplined context management outperformed model upgrades, orchestration changes, and prompt polishing — [Microsoft Tech Community: Context Engineering for Reliable AI Agents](https://techcommunity.microsoft.com/blog/appsonazureblog/context-engineering-lessons-from-building-azure-sre-agent/4481200/)
- **r/LangChain and X community synthesis (June 2026):** "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." LangGraph (~38M+ monthly PyPI downloads) has become the production standard for teams that shipped fast with CrewAI and hit branching, approval, or crash-safety requirements. The threshold for orchestration adoption: at least one of branching, branching, branching, or multi-agent coordination. A single `create_agent` with 3–5 well-scoped tools beats a three-node graph — [Idea to MVP: Agent Orchestration with LangGraph](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)
- **OpenAI Agents SDK patterns:** Three core orchestration patterns in production: agents-as-tools (manager stays responsible for the conversation), handoffs (explicit transfer of control to a specialist agent), and parallel execution. The SDK ships with built-in tracing and guardrails, positioning it as the direct replacement for the deprecated Assistants API — [OpenAI: Agent Orchestration Guide](https://openai.github.io/openai-agents-js/guides/multi-agent/), [APIScout: Architecture Patterns 2026](https://apiscout.dev/guides/openai-agents-sdk-architecture-patterns-2026)

## Gotchas

- **The leaky pipeline.** Stages that forward all accumulated context rather than their specific output. This is the most common context-management failure in production pipelines — it bloats context windows, degrades downstream agent performance, and produces invisible latency and cost. Each stage should emit a clean, scoped output.
- **The rigid pipeline.** A pipeline with no error handling between stages. When stage 3 produces malformed output, stage 4 attempts to process it, produces garbage, and stage 5 produces plausible-looking garbage. Every stage must validate its inputs before proceeding.
- **Non-deterministic worker counts in orchestrator-worker patterns.** The orchestrator decides how many workers to spawn at runtime. Without a hard cap enforced both in the orchestrator's prompt and in the dispatcher code, a single input can trigger dozens of parallel LLM calls. Add a `max_workers` constraint explicitly.
- **Degenerative evaluator-optimizer loops.** Without an explicit iteration cap, the evaluator-optimizer loop can run indefinitely when the model keeps "almost but not quite" improving output. Set `max_iterations` as a first-order concern, not a last resort.
- **Premature framework commitment.** Choosing LangGraph before you know you need pause/resume, or committing to a CrewAI role schema before you understand the failure modes, both create migration debt. Build with the simplest approach first and evolve the control structure when the complexity force that justifies it actually appears.
