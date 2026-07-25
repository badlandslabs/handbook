# S-1623 · The Multi-Agent Coordination Stack

You have three specialized agents — researcher, coder, reviewer. Each is brilliant alone. Together, they produce confident nonsense, loop infinitely on edge cases, and bury the real answer under layers of inter-agent confusion. This is the coordination tax: adding agents multiplies capability and compounds failure in equal measure.

## Forces

- **Reliability compounds against you.** Five agents each at 95% reliability deliver ~77% end-to-end success. Each inter-agent handoff is a trust boundary where silent failures breed confident wrong answers.
- **The coordinator is the hardest role.** Routing tasks correctly, aggregating results, and detecting loops requires more prompt engineering than all the specialist agents combined.
- **Frameworks feel safe, then betray you.** LangGraph, CrewAI, and AutoGen all have real production users and real production failures — often the same ones.
- **Token budget is the real bottleneck.** Anthropic's internal data shows token usage explains 80% of performance variance in multi-agent research tasks. More agents = more tokens = better results up until you hit cost ceilings or loop runaway.
- **Single-agent with subagent-tools is usually enough.** OpenAI explicitly draws this line: when a manager invokes a specialist via `.as_tool()`, the manager keeps ownership. That's a fundamentally different architecture from agents that transfer control, and it covers 80% of real use cases.

## The Move

Design the coordinator before the specialists. Every other decision flows from this one.

**1. Choose a topology first, not a framework.** Five patterns cover most real production cases:
   - **Supervisor/Router** — one LLM dispatches sub-tasks to specialists; good for task classification + delegation (most common production pattern)
   - **Sequential Pipeline** — output of agent N feeds agent N+1; good for strict ordering (spec → code → review → deploy)
   - **Parallel Workers + Aggregator** — same task dispatched to multiple agents, results merged; good for reliability and diverse perspectives
   - **Hierarchical** — manager agent spawns sub-managers that spawn workers; scales to complex tasks but hard to debug
   - **Swarm / Emergent** — agents negotiate and form topology dynamically; powerful but operationally chaotic

**2. Treat every inter-agent boundary as a trust boundary.** Validate structured outputs at every handoff. A critic step before each handoff catches silent failures that compound. Never pass raw LLM output from one agent directly into another without schema enforcement.

**3. Keep the chain short by default.** The reliability math is unforgiving: 3 agents × 95% = 86% end-to-end. 8 agents × 95% = 66%. Start with one agent. Decompose only when distinct, separable capabilities genuinely justify coordination overhead. A sprawling ten-agent swarm with no boundary controls is mathematically doomed.

**4. Instrument every hop.** Capture: which agent ran, what it received, what it returned, tokens spent, time elapsed, and whether the output passed validation. Without this, you cannot distinguish a looping agent from a slow one, or a confident failure from a genuine success.

**5. Implement hard budget guards from day one.** Set max iterations, max total tokens per run, and timeout per agent. Unbounded multi-agent loops have burned months of token budgets in minutes. Budget guards are not optional — they are the difference between a useful tool and a financial incident.

**6. Validate before you trust.** For high-stakes outputs, add a mandatory critic/reviewer agent between each handoff — not as a nice-to-have but as a hard gate. The critic's job is to catch silent failures, not to improve the answer.

## Evidence

- **Engineering Blog:** Anthropic's production research system (Opus 4 lead + Sonnet 4 subagents) outperformed single-agent Opus 4 by 90.2% on internal BrowseComp evaluation. Key finding: token usage explained 80% of performance variance. Published June 13, 2025 — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **HN Ask HN (107 points):** Production practitioners reporting: one team runs a 13-agent system (PAI Family) with agents that argue and bet against each other on a prediction market; another uses `spec → plan → design → code → review` agents where "the arrangement of the checks between agents matters more than which model you pick." HN thread: [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705) and [news.ycombinator.com/item?id=47270020](https://news.ycombinator.com/item?id=47270020)
- **Show HN (107 points, 35 comments):** Hive framework — built for ERP automation (PO/invoice reconciliation), rejects "chatbot UX" in favor of services that act while users sleep. Explicit critique of LangChain/AutoGPT failures in production: brittle loops, can't handle messy data. GitHub: [github.com/adenhq/hive](https://github.com/adenhq/hive)
- **Technical Analysis:** AutoGen v0.5.2 + vLLM v0.6.2 on AWS EKS (G5.2xlarge, A10G GPUs) achieved p95 latency ~2.4s at 50 concurrent sessions vs. ~6.3s single-process baseline, using Redis for inter-agent messaging with stateless agent workers. — [markaicode.com/architecture/autogen-llm-architecture](https://markaicode.com/architecture/autogen-llm-architecture)
- **Community Resource:** Vectara's awesome-agent-failures repo documents failure modes with real case studies including NEDA/Tessa eating disorder chatbot disaster. Reliability compounding table: 3×95% → 86%, 5×95% → 77%, 8×95% → 66%. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)

## Gotchas

- **Silent failures are the most dangerous.** Multi-agent systems often return a confident, plausible answer that is built entirely on broken sub-tasks. There is no error message — just a wrong answer. Validation at every handoff is the only defense.
- **Rolling your own is often correct for production.** Multiple practitioners explicitly report that existing frameworks are "not good enough for serious work" and build on Node.js + Express + V8 isolates with MongoDB for state, or use LangGraph as a state machine backbone with custom orchestration on top. The frameworks are good for prototyping; production often demands owned infrastructure.
- **"Lost in the Middle" destroys shared-context architectures.** Performance degrades up to 73% when critical information is buried in long shared contexts. Distributed context management — each agent has its own focused context — outperforms shared context at scale.
- **Observability is an afterthought in every framework.** LangGraph has built-in tracing; everything else requires custom instrumentation. If you don't know which agent ran, for how long, with what input/output, you cannot debug failures — you can only watch them happen.
- **Model version changes break agent prompts non-obviously.** An agent that worked with Claude 3.5 Sonnet may behave differently with 3.7 Sonnet, changing handoff behavior, tool call frequency, and error recovery patterns. Pin model versions in production and eval on every upgrade.
