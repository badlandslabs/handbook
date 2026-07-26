# S-1681 · The Orchestration Decision Stack — When You're Not Sure If You Need One Agent or Five

You're building an AI workflow and you don't know whether to chain a few prompts, wire up a router that dispatches to specialists, let a single agent loop with tools, or spin up a team of agents that pass state between themselves. Every framework makes all of these look equally reasonable. Production evidence says they are not — the wrong choice here is the most expensive architectural mistake in agentic systems, and you won't find out until you're deep into debugging why your "smart router" is routing everything to the same handler, or why your single-agent loop is looping.

## Forces

- **Simple chains handle ~80% of production use cases, but teams reach for agents first.** The frameworks are agent-first, so that's what gets built — then over-engineered, then rewritten. LangChain's 2025 production survey found this directly. The cost of over-engineering is paid in debugging complexity, token spend, and failure surface area.
- **Pattern choice is not reversible at zero cost.** Moving from a single-agent loop to a structured pipeline means rewriting tool interfaces, reworking state management, and retesting. Moving the other way — collapsing five agents into one — means rethinking what your tools expose. Pick the simplest pattern that could plausibly work, not the most powerful one that might be needed.
- **Context window limits what a single agent can hold, but not all at once.** A summarizer → classifier → router chain can run sequentially through a context window that's too small for a single agent to hold all the data. You don't need five agents — you might just need to chunk the data and pipe it.
- **Multi-agent systems introduce failure modes that single-agent systems don't have.** State inconsistency between agents, circular delegation (A→B→A), and cascading corruption from one agent's bad output are not problems that affect a single agent handling a linear chain.

## The move

**A decision ladder — start at step 1, move down only when the simpler pattern genuinely cannot work.**

### Step 1: Can a simple sequential chain do this?

A→B→C, each step's output feeds the next. No branching, no agent loops.

- Use when the workflow is a pipeline: extract → validate → classify → store. Each step is deterministic and isolated.
- Latency compounds — A's latency + B's latency + C's latency. If step N fails, steps N+1..M never run.
- The "sequential only" constraint is a feature. It makes every failure easy to locate and every step easy to test independently.
- **The move:** Start here. Always.

### Step 2: Do you need a router / classifier dispatch?

A lightweight model (or rule set) classifies the input and routes it to a specialized handler. Each handler can use a different model, prompt, or tool set. Handlers run in isolation.

- Use when inputs have distinct types that need different treatment — customer support triage, document type routing, intent classification that branches into separate workflows.
- The router is a classifier, not an agent. Keep it simple: Haiku 4.5 or GPT-4o-mini is sufficient for most routing decisions. Don't route with a frontier model unless the routing decision itself requires frontier reasoning.
- Router accuracy is the single point of failure — a misrouted request goes to the wrong handler and the rest of the system never sees it.
- **The move:** When you have 2+ distinct workflow paths that share no common steps.

### Step 3: Do you need an agent loop?

A single agent with tools calls them repeatedly until a stopping condition is met.

- Use when the problem space is genuinely open-ended — code generation and debugging, research tasks that require variable numbers of web searches, complex planning under uncertainty.
- **Requires explicit stopping conditions** — token budget, step count ceiling, or a verifiable end-state check. Without these, the loop is the failure mode. (See S-1680 "The Failure Boundary Stack.")
- **Requires tool verification** — the agent must confirm tool calls succeeded before acting on their output. HTTP 200 from a tool call does not mean the tool call did what the agent expected. (See S-1677 "The Phantom Receipt Stack.")
- Code execution in a sandbox is the highest-value tool for agent loops — Slava Dubrov's benchmarks show up to 98.7% token reduction when replacing LLM-generated code strings with executed sandboxed code.
- **The move:** When the number of steps is genuinely unknowable at the start of the run.

### Step 4: Do you need a multi-agent system?

Multiple specialized agents coordinated by an orchestrator, with isolated state and explicit handoff protocols.

- **Three coordination patterns have production traction:**
  - **DAG-based (explicit dependency graph):** Tasks have defined predecessors and successors. Deterministic, testable, easy to audit. Best for workflows with fixed structure.
  - **Event-driven (async pub/sub):** Agents react to events rather than being called directly. Good for loosely coupled systems where agents need to operate independently. Harder to trace end-to-end.
  - **Actor model (isolated state + message-passing):** Each agent has its own memory and state, passing messages to others. Supervision hierarchies handle failures. Best for resilient, long-running systems. The Zylos research notes this pattern is gaining ground for "durability-first" production deployments.
- Multi-agent introduces state inconsistency as the primary failure mode. Two agents that don't share memory may act on contradictory premises. One agent's corrupted context can silently propagate to all downstream agents.
- **The move:** When you have genuinely independent parallel workstreams, strict isolation requirements between subsystems, or specialists that need different models/prompts/tools that can't coexist in one agent's context.

## Evidence

- **LangChain Production Survey (2025):** Simple chains handle ~80% of production use cases. Teams consistently over-engineer their first implementations. — [Agentika / LangChain](https://agentika.uk/blog/llm-orchestration-patterns.html)
- **Multi-agent orchestration taxonomy:** Three schools — DAG-based (deterministic execution), event-driven (async reactive), actor model (supervision hierarchies). Production failures observed: semantic failures, cascading context corruption, circular delegation deadlock, runaway cost from unbounded retry. — [Zylos Research, 2026-04-14](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)
- **Survey of 500+ technical leaders (Anthropic / Material, Dec 2025):** 57% of organizations deploying agents for multi-stage workflows; 81% planning to tackle more complex use cases in 2026. Code generation, data analysis, and customer service are the top three highest-impact use cases. — [Anthropic Engineering Blog](https://claude.com/blog/how-enterprises-are-building-ai-agents-in-2026)
- **Tool use benchmark:** Code execution in sandbox reduces token cost by up to 98.7% versus LLM-generated code strings. CLI tools are 4–32× cheaper than MCP for local development. MCP carries the highest security surface area (50+ CVEs as of early 2026). — [Edge of Context, Slava Dubrov, 2026-03-24](https://slavadubrov.github.io/blog/2026/03/24/ai-agent-tool-use)
- **Scaling patterns analysis:** Multi-agent orchestration (puppeteer pattern), graduated autonomy, and agent registries are the patterns with real production deployments in 2026. Async decoupling via message queues prevents cascading failures in multi-step workflows. — [HackerNoon / Rambabu Tangirala, 2026-04-20](https://hackernoon.com/seven-architectural-patters-for-scaling-agentic-ai-in-production)

## Gotchas

- **Over-engineering with agents is more common than under-engineering.** The research consensus is clear: start with the simplest pattern and graduate up the ladder only when you hit a concrete limitation, not when you imagine one might appear.
- **Router accuracy is a silent bottleneck.** If your classifier routes 10% of requests to the wrong handler, 10% of your production traffic silently degrades. Monitor routing accuracy in production, not just during evaluation.
- **Multi-agent state inconsistency is the failure mode that bites hardest at scale.** If agents share mutable state without a synchronization protocol, you'll get cascading context corruption where one agent's bad read propagates downstream and nobody's output is trustworthy. Use explicit state handoff schemas, not shared memory.
- **The "agent" framing makes teams forget to define stopping conditions.** Every agent loop needs a step ceiling, a token budget, or a verifiable end-state check. If you design it as "just loop until done," it will loop until something external stops it — usually a timeout or a bill.
