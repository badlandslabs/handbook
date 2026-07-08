# S-831 · The Five Primitives Stack — When the Agent Stack Stopped Fragmenting

Three independent sources — Anthropic's engineering team, the OpenAI Agents SDK (March 2025), and practitioner benchmarks from hjLabs.in — all converge on the same five core building blocks for agentic systems. The fragmentation era is ending. Teams that felt compelled to pick a full framework (LangChain, AutoGen, CrewAI, or roll their own) are discovering that the real production-ready surface is five primitives you compose freely.

## Forces

- **Framework lock-in tax.** The 70% of regulated enterprises rebuilding their stack every 3 months weren't doing it for fun — they were paying for the abstraction layers that a full framework adds. HN commenters consistently report that migrating to a framework delayed products more than it accelerated them.
- **The primitives convergence.** Anthropic's "building effective agents" guide (December 2024, still cited as canonical in June 2025 HN thread with 543 points) describes agents, tools, loops, and memory. OpenAI's Agents SDK ships exactly five primitives: agents, tools, handoffs, guardrails, and tracing. The functional overlap is deliberate, not coincidental.
- **The 5% wall.** Out of 1,837 engineering/AI leaders surveyed (Cleanlab, August 2025), only 95 had agents live in production. The barrier wasn't model capability — it was everything around it: observability, guardrails, failure recovery, and stack stability. The five primitives directly address each.
- **Multi-agent overhead is real.** Princeton NLP found single agents match or outperform multi-agent systems on 64% of benchmarked tasks with the same tools and context. Multi-agent adds ~2.1 percentage points of accuracy at roughly double the cost. The impulse to add agents must be justified.

## The Move

Build agentic systems from five composable primitives, not a framework. Reach for a framework only when the coordination complexity genuinely exceeds what you can maintain in plain code.

- **Agents** — LLM plus system prompt plus available tools. Stateless by default; session state is the caller's concern. Prefer a capable base model (Claude 3.5/4, GPT-4o, or equivalent) with tool definitions over a framework-specific agent abstraction.
- **Tools** — Typed function definitions that the model calls. Keep schemas minimal and strict. For large tool libraries (>20), use dynamic discovery (semantic embedding-based tool search) rather than loading all definitions upfront — Anthropic's advanced tool use (November 2025) shows 85% token reduction with on-demand tool search.
- **Handoffs** — Explicit transfer of control between agents. The OpenAI Agents SDK models this as a first-class primitive; in plain code, it's a routing decision plus context passing. Handoffs are the right pattern for triage (front-line agent → specialist) and skill-based routing. They reset conversational state to the new agent's context — don't use them for shared-memory scenarios.
- **Guardrails** — Input/output validation outside the model call. Validate before the LLM processes input; validate structured outputs after. The Agents SDK provides `guardrails` as an explicit layer. At minimum, implement a validation step between user input and agent processing, and between agent output and downstream systems.
- **Tracing** — Every tool call, model call, and state transition logged with a trace ID. Langfuse, LangSmith, or OpenTelemetry-based tracing (OpenAI SDK ships built-in tracing) is non-negotiable for production. Without traces, you cannot distinguish an agent that did the right thing for the wrong reason from one that failed silently.

## Evidence

- **Anthropic engineering blog:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Their four-pattern breakdown (RAG, tool use, agentic loops, memory) maps directly onto the five primitives. HN discussion (June 2025, 543 points) confirms the guide "held up really well" over 6+ months. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **OpenAI Agents SDK (March 2025, 19k+ GitHub stars):** Ships exactly five primitives — agents, tools, handoffs, guardrails, tracing. Built on top of the same patterns with minimal abstraction. Production-ready additions over the experimental Swarm predecessor: built-in session management, guardrails, and tracing. — [https://github.com/openai/openai-agents-python](https://github.com/openai/openai-agents-python)
- **hjLabs.in production comparison:** After shipping agents on LangGraph, CrewAI, and AutoGen, the honest assessment: "The challenge isn't writing the agent — it's running it reliably in production." All three frameworks converged on the same primitives internally. Framework choice matters less than primitives discipline. — [https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/](https://hemangjoshi37a.github.io/hjLabs-AI-Engineering-Notes/04-crewai-vs-langgraph-vs-autogen-production-comparison/)
- **Cleanlab survey (August 2025):** 5% production adoption, 70% stack rebuild rate, <1/3 satisfied with observability. Directly validates that the five primitives — especially tracing and guardrails — are the actual gaps blocking production success. — [https://cleanlab.ai/ai-agents-in-production-2025/](https://cleanlab.ai/ai-agents-in-production-2025/)

## Gotchas

- **Reaching for multi-agent when single-agent suffices.** The 2x cost and 64% overlap statistic from Princeton NLP is a strong prior: add agents only when task decomposition genuinely requires separate contexts or skill specializations, not because it feels more "agentic."
- **Handoffs as a substitute for shared memory.** Handoff resets state to the new agent's context. For long conversations with shared context needs, pass state explicitly or use a shared memory layer — don't assume handoff preserves conversational continuity.
- **Tool bloat from the start.** Loading all tool definitions into context is the default mistake. Start with the 3-5 tools the agent needs for the current task. Add more with dynamic discovery once the tool count exceeds what fits comfortably in context.
- **Tracing as an afterthought.** Teams that skip structured tracing early and add it later pay double: they must retrofit instrumented calls and they have no historical traces to debug from. Trace from the first agent call, not from first production incident.
- **Framework loyalty over primitives discipline.** LangGraph, CrewAI, AutoGen, and the OpenAI Agents SDK are all valid implementation choices. The failure mode is committing to one framework's abstractions before understanding which primitives you actually need. Start with the primitives in plain code; adopt a framework when the boilerplate cost exceeds the coordination complexity.
