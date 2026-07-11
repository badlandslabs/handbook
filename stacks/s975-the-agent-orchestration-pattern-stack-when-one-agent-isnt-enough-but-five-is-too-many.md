# S-975 · The Agent Orchestration Pattern Stack — When One Agent Isn't Enough But Five Is Too Many

Your single-agent prototype works. Then the task grows: it needs specialized domain knowledge, different models for different subtasks, and the ability to recover when one step fails. You reach for a multi-agent framework and immediately hit choice paralysis — LangGraph, CrewAI, AutoGen, or just Python? The answer isn't "pick a framework" — it's pick an orchestration pattern that matches your workflow's dependency structure. The pattern is the architecture. The framework is just how you express it.

## Forces

- **The naive trap is real** — Anthropic recommends starting with direct LLM API calls, and most patterns are implementable in a few lines of code (Anthropic, "Building Effective AI Agents," Dec 2024). Most teams skip this and reach for a framework before understanding their workflow's dependency structure.
- **Pattern mismatch is the #1 killer** — "Across the deployments we have observed, a large share of failures originate in orchestration design rather than individual agent capability — agents are individually capable but poorly coordinated" (Bartek Pucek, The Thinking Company, 2026). A sequential chain serializes everything; a fan-out architecture can't handle dependent steps.
- **Inference cost compounds at the multi-agent boundary** — 4-agent workflows run $5–8 per complex task in inference costs alone, and naive multi-agent pipelines don't route cheap tasks to cheap models (RaftLabs, March 2026).
- **Context window saturation is a real ceiling** — LLM accuracy drops measurably when context exceeds 60–70% of the window; each agent should own a narrow context, not a shared ocean (AI Magicx, April 2026).
- **Untyped handoffs kill workflows faster than anything else** — "The biggest failure points are not the agents themselves — they are the contracts between agents (typed schemas), the observability gap, and inference cost compounding" (RaftLabs, March 2026).

## The Move

Six patterns cover the vast majority of production use cases. Pick the one that matches your workflow's dependency structure — not the one with the best GitHub stars.

**1. Start with direct API calls, not a framework.** If your workflow is 1–3 steps with no branching, write it in Python. Only reach for an orchestration framework when you have conditional logic, state, or multi-agent coordination.

**2. Match pattern to dependency structure:**
- **Sequential pipeline** — each step builds on the last (summarize → translate → QA). Order matters. Fail-fast: if step 2 fails, restart from step 1.
- **Fan-out / fan-in** — parallel independent tasks (analyze 10 stocks concurrently). Scales horizontally. Aggregate results at the fan-in point.
- **Supervisor / hierarchical** — one orchestrator delegates to specialists. Best for domains where a generalist needs to coordinate experts (13 agents in PRISM-INSIGHT, each owning a domain like technical analysis, financials, news).
- **Router** — a classifier routes tasks to different agents or pipelines based on intent. Fast-path for simple queries, deep-path for complex ones.
- **Evaluator-optimizer loop** — one agent produces, another critiques, they iterate until quality threshold. Best for writing, code review, strategic planning.
- **Hierarchical delegation** — multi-level supervisor chain for very large workflows. Rarely needed below ~20 agents.

**3. Combine 2–3 patterns per production system.** No pattern runs alone. PRISM-INSIGHT uses supervisor + fan-out: a central coordinator assigns domain agents that work in parallel, then aggregates results. Microsoft Semantic Kernel Sequential orchestration passes each agent's full conversation to the next by default, which can be configured to `chain_only_agent_responses=True`.

**4. Use typed schemas at every handoff.** Define the input/output contract for each agent boundary in Pydantic or JSON Schema. This is the observability and debuggability layer that makes multi-agent systems tractable.

**5. Route by model capability, not uniformity.** Route simple classification to GPT-4o-mini, complex reasoning to Opus/GPT-5. PRISM-INSIGHT uses GPT-4.1 for analysis, GPT-5 for trading decisions, Claude Sonnet for conversation. This directly reduces the $5–8/task inference cost.

**6. Keep each agent's context domain-narrow.** Tool selection accuracy decreases as tool count grows — 50 tools on one agent is worse than 5 agents with 10 tools each (AI Magicx, April 2026).

## Evidence

- **Anthropic engineering guide:** Defines agents as "systems where LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks." Recommends direct API calls first. Multi-agent approaches improve complex task completion by 90% (Anthropic, "Building Effective AI Agents," Dec 2024) — https://docs.anthropic.com/en/docs/build-a-skill/agents
- **Real production system — PRISM-INSIGHT:** 13 specialized agents for Korean stock analysis, live since March 2025. 408% simulated return (Mar–Sep 2025), +9.35% on real money account since late September. Uses GPT-4.1 for analysis, GPT-5 for trading decisions, Claude Sonnet for conversational interface. Costs ~$200/month in API calls for 450+ users — https://news.ycombinator.com/item?id=45946056
- **Practitioner analysis — thinking.inc (Bartek Pucek, March 2026):** Six core patterns covering most enterprise use cases. Production systems typically combine 2–3 patterns. "Across the deployments we have observed, a large share of failures originate in orchestration design rather than individual agent capability." — https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns
- **Production engineering comparison (May 2025):** Tested LangGraph (stateful graph), CrewAI (role/task model), and AutoGen (conversational peers) under real deadlines. LangGraph wins on complex multi-step workflows with conditional branching and state. CrewAI wins on getting to production quickly with role-based pipelines. AutoGen wins on multi-party debates and research conversations. Zero framework-level costs for all three — https://python.plainenglish.io/autogen-vs-langgraph-vs-crewai-a-production-engineers-honest-comparison-d557b3b9262c
- **Enterprise survey — RaftLabs (March 2026):** 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025 per Gartner). 57% of organizations already have agents in production. Untyped handoffs, observability gaps, and inference cost compounding are the top three failure modes — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **LangGraph production patterns — Inductivee (January 2026, updated April 2026):** LangGraph 0.2+ provides persistent state (PostgresSaver), human-in-the-loop interrupts, parallel fan-out/fan-in, and first-class streaming. These four capabilities separate production-grade workflows from prototypes — https://inductivee.com/blog/langgraph-multi-agent-workflow-deep-dive

## Gotchas

- **Starting with a framework before understanding your pattern** — LangGraph and CrewAI express different patterns. Using LangGraph to build a sequential pipeline adds graph complexity you don't need. Use direct API calls or a lightweight pipeline until you have branching or state requirements.
- **Full-context handoff explosion** — Microsoft Semantic Kernel passes each agent's full conversation history to the next agent by default. In a 5-agent chain, agent 5 receives 4 prior conversations plus its own. Configure `chain_only_agent_responses=True` or truncate aggressively.
- **Ignoring cost at the architectural level** — Multi-agent inference costs compound. If you design a hierarchical system where a supervisor calls a sub-agent 10 times per request, you need cost controls (max iterations, model routing, caching) built into the architecture, not bolted on after.
- **Tool bloat on single agents** — Adding 50 tools to one agent degrades tool selection accuracy. Split into domain-specific agents with smaller, focused tool sets. This also gives you natural failure isolation.
- **No observability at handoff points** — Without structured handoff schemas and logging at each agent boundary, multi-agent traces are unreadable. Every handoff should emit a structured event (agent, input schema, output schema, duration, success/failure) even in development.
