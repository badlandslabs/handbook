# S-906 · The Orchestration Tax Stack — When Every Agent Needs a Boss to Stay in Lane

Your single ReAct agent worked fine on demos. You shipped it. Three weeks in, it's calling tools out of order, looping on edge cases, and no one can trace why. The fix everyone reaches for: add a supervisor agent. Then that supervisor needs its own supervisor. Twelve agents later, your "simple assistant" is a management consulting nightmare — and debugging a routing failure means reading 800 lines of agent-to-agent context handoff.

This is the orchestration tax: the complexity you pay every time you add an agent layer, and the mistake of paying it before you know what the complexity buys.

## Forces

- **Single agents hit a complexity ceiling.** ReAct-style loops handle 3-5 tool calls cleanly. Beyond that, instruction conflict and error accumulation make them unreliable — which is exactly when teams reach for multi-agent architectures, and exactly when they create a new problem.
- **More agents means more routing surfaces to debug.** Every handoff between agents is a potential failure point, a token budget cost, and an observability hole. The HN thread on multi-agent setups shows teams consistently underestimating how hard distributed failure is to trace compared to a single loop.
- **Framework abstraction hides the routing logic.** LangGraph, CrewAI, and AutoGen all provide orchestration primitives — but the routing decision (who handles this task?) lives in framework-specific configuration that's hard to inspect when something breaks.
- **The right orchestration pattern depends on the workflow shape.** Sequential handoffs, parallel fan-out, supervisor-and-worker, and peer-to-peer all solve different problems. Teams pick a pattern based on familiarity, not fit.
- **Production data disagrees with the demos.** Cleanlab's August 2025 survey found only 5.2% of organizations had verified production agents. Of those, most were still iterating on basic capability and control — not scaling orchestration complexity.

## The move

**Start with one agent. Only split when you have a concrete failure to solve.**

### 1. Use deterministic routing before LLM-based routing
Route tasks to agents or tools by classification — not by asking the LLM to decide. A fast classifier (embedding similarity, keyword match, or a small model) that routes 80% of traffic is cheaper and more predictable than letting an LLM orchestrator decide on every call. Microsoft ISE's retail customer migration from a modular monolith with a router to microservices agents showed this: the routing logic must be inspectable and auditable first.

### 2. Evolve to multi-agent only at documented failure points
Replit's agent architecture evolved from a single ReAct agent to a multi-agent system with a manager agent and specialized sub-agents — **after** observing that a single agent's error rate increased with task complexity. Track per-step failure rates before splitting. If your single agent fails at step 4 of 7 with a specific tool combination, that's your split criteria — not "it feels complex."

### 3. Make the orchestrator dumb where possible
The supervisor/orchestrator should handle routing and coordination — not reasoning about task content. Anthropic's guidance is explicit: "find the simplest solution possible, and only increase complexity when needed." For the 80% of tasks that are routine, a deterministic routing table beats an LLM orchestrator. Use the LLM orchestrator only for the 20% where the routing decision genuinely requires judgment.

### 4. Separate tool definitions by agent scope
Don't give every agent access to every tool. Anthropic's advanced tool use beta uses on-demand tool discovery to avoid token overhead — but the underlying principle is broader: agents should have minimal tool access aligned to their role. A researcher agent gets web search and document retrieval. An executor gets file operations and CI APIs. Scope reduces hallucinated tool calls and makes failure isolation possible.

### 5. Instrument handoffs explicitly
Every agent-to-agent message is a potential failure. Log: source agent, target agent, task description, output summary, and error state. Without this, a cascade failure across 4 agents produces logs that are impossible to reconstruct. This is where the "silent green exit" failure mode (S-905) becomes especially lethal in multi-agent systems — an agent can return success to its caller while the actual work quietly failed downstream.

### 6. Design for human-in-the-loop at escalation boundaries
TechTarget's survey of real deployments recommends human checkpoints for high-stakes decisions even in fully autonomous pipelines. The 95% pilot failure rate cited across multiple sources (MIT/Fortune, Gartner) consistently points to the same root cause: teams automate too much, too fast, without observability to catch failures. Co-pilot mode (agent suggests, human approves) for edge cases is not a cop-out — it's the difference between shipping and iterating.

## Evidence

- **Anthropic Engineering:** "Agents should discover and load tools on-demand" — the Tool Search Tool reduces token overhead 85% by keeping only task-relevant tools in context. Their core guidance: prefer workflows (predefined code paths) over agents (dynamic LLM-directed loops) when the task structure is known. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Replit Case Study (LangChain Breakout Agents):** Evolved from a single ReAct agent to a multi-agent system with manager and specialized sub-agents **only after** observing increased error rates on complex tasks. Architecture uses explicit role separation: Manager Agent handles workflow orchestration, sub-agents handle execution — not ad-hoc dynamic role assignment. — [URL](https://www.langchain.com/breakoutagents/replit)

- **Microsoft ISE Developer Blog (June 2026):** Documented migration from a modular monolith with a router pattern (single intent detection → single agent) to microservices agents. Key lesson: routing logic must be auditable before distributing agents. Used coordinator pattern for agent reuse across teams. — [URL](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Cleanlab Survey (August 2025, n=1,837):** 5.2% of organizations have verified production agents. Of those, most are still in capability iteration — not scaling orchestration. 70% of regulated enterprises rebuild their stack every 3 months or faster. — [URL](https://cleanlab.ai/ai-agents-in-production-2025)

- **Show HN: PRISM-INSIGHT:** Multi-agent stock analyzer with 13 specialized agents running live since March 2025. Architecture uses explicit agent role definitions by domain (technical analysis, financials, news, trading flows). Demonstrates that role-based decomposition works when roles are narrow and well-bounded. — [URL](https://news.ycombinator.com/item?id=45946056)

- **TechTarget / Info-Tech Research:** Seven best practices from real deployments, including "start with the workflow, not the agent" and "multi-agent architecture is the norm" — meaning structured orchestration, not ad-hoc dynamic delegation. Governance and evaluation are the top planned investments (63%). — [URL](https://www.techtarget.com/searchCIO/feature/Agentic-ai-in-practice-lessons-from-real-deployments)

## Gotchas

- **Don't build a supervisor agent to manage supervisor agents.** The hierarchical pattern (orchestrator → supervisor → worker) is valid for complex workflows, but teams frequently create a hierarchy 2 levels deeper than the workflow actually needs. If you can't explain why a task requires 4 layers of routing, use 2.
- **LLM-based routing is non-deterministic by design.** When your orchestrator uses an LLM to decide which sub-agent handles a task, you gain flexibility at the cost of reproducibility. Log every routing decision and its outcome — you'll find certain task types consistently route wrong and need deterministic overrides.
- **Multi-agent concurrency amplifies the silent green exit problem (S-905).** In a single-agent loop, the loop can detect its own failures. In a multi-agent system, Agent A reports success to the supervisor while Agent B silently failed. You need end-to-end task verification at the workflow level, not the agent level.
- **Token budgets compound across agent layers.** Anthropic's tool search optimization shows: 85% token reduction from on-demand tool discovery. A 4-agent pipeline where every agent loads the full tool manifest on every call will blow your context window and your cost budget before it blows your error rate.
