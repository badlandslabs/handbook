# S-1008 · The Orchestration Pattern Match Stack

When your agent workflow has multiple steps, you face a choice that looks like an architectural decision but is really an autonomy calibration question: how much should the LLM control what happens next? The wrong answer—picking a pattern that grants too much or too little autonomy—produces either brittle pipelines that can't recover or runaway agents that can't stop. The match is finding the orchestration shape that mirrors the actual decision-space of your task.

## Forces

- **Chains assume known paths; agents assume unknown ones.** Linear workflows with fixed steps are underkill for open-ended tasks; full agent loops are overkill—and expensive—for deterministic ones
- **Multi-agent adds accuracy at near-double the cost.** Princeton NLP research shows single agents match or outperform multi-agent on 64% of benchmarked tasks, with multi-agent adding ~2.1 percentage points of accuracy at roughly 2× cost (Apptitude, citing Princeton NLP, 2026)
- **Orchestration failure is structural, not prompting.** The dominant production failure modes—cascading context corruption, deadlocks, silent state loss, runaway cost—are solved by architecture, not better prompts (Zylos Research, 2026)
- **Framework choice locks you in.** LangGraph, CrewAI, and Microsoft Agent Framework represent genuinely different mental models; swapping between them mid-project is weeks of refactoring (TURION.AI, 2026)

## The move

Match orchestration pattern to autonomy requirement. Start at minimum viable complexity, not maximum expressiveness.

**The three-pattern production ladder:**

1. **Simple chains** — zero autonomy. The LLM executes a fixed sequence of steps; the orchestrator controls flow. Use for: summarization, translation, classification, any task where the path is known upfront. LangChain 2025 usage data shows 73% of production systems use chains—only 12% use full agents (Agentika, 2026). If a chain can work, use one.

2. **Router patterns** — conditional autonomy. A classifier or LLM routes the input to the appropriate handler. Use for: task triage, hybrid workflows where different input types need different pipelines. The LLM decides *which* path; each path is still a chain. An intent classifier with a fallback to a general agent handles this cleanly.

3. **Agent loops** — full autonomy. The LLM decides what tools to call, in what order, and when to stop. Use for: open-ended research, complex debugging, tasks where the sub-steps cannot be enumerated upfront. Hard-cap the loop with a step limit or token budget to prevent runaway execution.

**The multi-agent triggers** (only escalate when one of these is true):
- Task requires genuinely different domain expertise (code + legal + finance)
- Parallel subtasks can run independently and benefit from parallelization
- Output validation requires a separate model from the generator
- The single agent repeatedly runs into context-window limits on complex tasks

**Six proven multi-agent patterns** (Beam.ai, 2026):
1. **Orchestrator-Worker** — central agent decomposes and assembles; workers are specialized and cheap
2. **Hierarchical Team** — manager agent delegates to specialist agents with defined roles
3. **Pipeline** — sequential handoffs where each agent refines the previous output
4. **Supervisor** — single agent oversees workers, decides sequencing and retry
5. **Peer-to-Peer** — agents negotiate and collaborate without central coordinator
6. **Swarm** — many specialized agents handle one task concurrently, results are aggregated

**Framework decision matrix** (ODSEA, 2026; TURION.AI, 2026):
- **LangGraph** — DAG/state machine; strongest production record (Klarna, LinkedIn, Uber, Replit); 33.4k GitHub stars; best for: deterministic workflows where you need explicit control over state and flow
- **CrewAI** — role-based teams; best developer experience; 52.5k stars; best for: rapid prototyping when team-role metaphors map naturally to your domain
- **Microsoft Agent Framework** (ex-AutoGen) — conversational; 1.0 GA April 2026; best for: research/experimental; too new for production commitments
- **AutoGen/AG2** — legacy; maintenance mode; viable only if you're already on it

## Evidence

- **Engineering blog:** LangChain 2025 production usage data—73% of deployed systems use chains, only 12% use full agents—Agentika, February 2026 — https://agentika.uk/blog/llm-orchestration-patterns.html
- **Research synthesis:** DAG, event-driven, and actor model comparison with failure taxonomy; OpenAI VP of App Infrastructure: "durability is as important as performance" for long-running agents—Zylos Research, April 2026 — https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns
- **Primary research:** Non-technical operator coordinating Claude + GPT across 100+ sessions on a 5,100+ test codebase; 12 distinct coordination error patterns discovered; every pattern exists because something specific broke—timothyjrainwater-lab/multi-agent-coordination-framework, GitHub — https://github.com/timothyjrainwater-lab/multi-agent-coordination-framework
- **Framework comparison:** LangGraph has strongest verifiable production record; CrewAI has best DX but unverifiable production claims; Microsoft Agent Framework 1.0 GA announced April 2026; AutoGen in maintenance mode—ODSEA CTO analysis, May 2026 — https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production
- **Benchmark data:** Single agent matches/outperforms multi-agent on 64% of tasks at ~half the cost; multi-agent adds ~2.1pp accuracy at ~2× cost—Apptitude citing Princeton NLP, May 2026 — https://apptitude.io/blog/single-agent-vs-multi-agent-ai-decision-framework
- **Market data:** 1,445% surge in multi-agent system inquiries Q1 2024→Q2 2025; 57% of organizations have agents in production; 40% of multi-agent pilots fail within 6 months—Gartner data via Beam.ai and RaftLabs, 2026 — https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production

## Gotchas

- **Over-engineering with agents when a chain would do.** The 2025 production data is unambiguous: chains dominate in production. Add agents only when you've hit a chain's ceiling.
- **No shared memory by default.** Multi-agent coordination frameworks that assume shared memory will silently corrupt state. The multi-agent coordination framework GitHub repo was built *by a non-technical operator* specifically because zero shared memory across sessions created 12 distinct coordination error patterns—each required a structural fix.
- **DAGs can't express loops naturally.** If your workflow has retry logic, rollback, or "keep going until done," use a state machine (LangGraph's `StateGraph` supports cycles) rather than forcing a DAG.
- **Difficulty-aware dynamic routing cuts cost significantly.** Estimate task complexity with a lightweight classifier and route to shallow or deep pipelines proportionally. Simple queries through deep multi-agent pipelines are an expensive anti-pattern.
- **MCP (Model Context Protocol) is now the universal plugin substrate** across LangGraph, CrewAI, and major competitors, replacing proprietary tool integrations. Build on MCP, not proprietary tool schemas.
