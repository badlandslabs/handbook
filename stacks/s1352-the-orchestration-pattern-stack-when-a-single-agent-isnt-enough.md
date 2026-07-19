# S-1352 · The Orchestration Pattern Stack

When a single agent can't hold the whole workflow in its context window, and you need multiple agents, tools, and human checkpoints working in concert — but you don't know whether to reach for LangGraph, a state machine, a simple sequential chain, or something else entirely.

## Forces

- **Premature orchestration complexity is the most common anti-pattern** — teams reach for LangGraph's full graph abstraction before they even know if a sequential chain would work
- **Framework lock-in is real** — "there's absolute 0 framework out there that's good enough for serious work" (HN practitioner, 2026), yet building from scratch means reinventing retry logic and state persistence
- **57% of AI project failures stem from orchestration design** — individual agents work fine; coordination is what breaks
- **The right pattern depends on execution duration and failure recovery needs** — short-lived synchronous pipelines and multi-hour durable workflows have fundamentally different requirements

## The Move

Choose the orchestration pattern that matches your execution window and failure tolerance, not the one with the best marketing.

### The six production patterns (2026)

**1. Sequential Chain** — agents execute one after another, each reading the prior's output. Dead simple, maximum 3-4 hops before context bloat kills you. Use for: one-shot pipelines where failure of any step means restart.

**2. Parallel Fan-out / Fan-in** — a router dispatches tasks to multiple agents simultaneously, collects results, then merges. 30-60% cost reduction vs sequential (Anthropic 200+ enterprise deployments). Use for: independent subtasks like "search all three data sources at once."

**3. Supervisor / Single-Agent Router** — one orchestrator agent decides which sub-agents to call and in what order. Clean separation of "what needs doing" from "who does it." Use for: dynamic workflows where the sequence isn't known upfront.

**4. State Machine (explicit transitions)** — nodes represent discrete states; edges represent named transitions; the graph never enters an undefined state. Preferred by teams with financial or compliance requirements. LangGraph's `StateGraph` with typed transitions is the common implementation. Use for: anything that needs auditable state transitions.

**5. Hierarchical / Multi-Level Supervisor** — a top-level agent breaks work into domains, assigns to sub-agents, reviews outputs, and iterates. Matches how teams actually organize (e.g., "architect → coder → tester → reviewer"). Use for: complex multi-domain tasks like end-to-end software development.

**6. Durable Execution (infrastructure-level)** — the workflow engine persists state to durable storage (Postgres, SQLite) at every step. If the process crashes mid-execution, it resumes from the last checkpoint. Temporal, Restate, and LangGraph's `PostgresSaver` are common implementations. Use for: multi-hour workflows where a crash mid-pipeline is unacceptable.

### Human-in-the-loop via interrupts

LangGraph's `interrupt()` suspends graph execution and waits for external input:

```python
from langgraph.types import interrupt, Command

def approval_node(state):
    decision = interrupt({"action": "refund", "amount": state["amount"]})
    return {"status": "approved" if decision["approved"] else "rejected"}

# Resume hours later with the same thread_id:
graph.invoke(
    Command(resume={"approved": True}),
    config={"configurable": {"thread_id": "order-9912"}},
)
```

This is the feature that separates "toy demo" from finance/ops-grade deployments. Every node that spends money or sends external communication should have an interrupt.

### Start with a sequential chain

The founder's checklist from r/LangChain practitioners (2026): draw the graph on paper first — boxes and arrows, not code. Ship a single-agent baseline. Measure latency, cost, and failure modes. Only add orchestration complexity when you have metrics proving the current approach doesn't meet requirements.

## Evidence

- **HN "Ask HN" — Multi-Agent AI Workflow Orchestration (April 2026):** Practitioners reported rolling their own orchestrator ("there's absolute 0 framework out there that's good enough for serious work"), using LangGraph + custom supervisor layers, AGNO for minimalistic isolation, and Dagu.sh for CLI-level workflow chaining. Agent-to-agent data passing used MongoDB shared documents with pipeline IDs. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

- **AnhTu.dev — 6 Patterns for Production Agent Coordination (April 2026):** Analysis of Anthropic's 200+ enterprise deployments: 57% of AI project failures stem from orchestration design. The "golden rule" — start with the simplest pattern, only upgrade when metrics prove it insufficient — is cited from observed production failures. 30-60% cost reduction achievable with the Router pattern. — [https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121](https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121)

- **Zylos Research — Durable Execution and State Machines for Production AI Agents (May 2026):** Production agents encounter network partitions, rate limits, and process crashes that naive implementations can't survive. Three converging solutions: durable execution (automatic state persistence), finite state machines (explicit transitions), and event-driven orchestration. Temporal and Restate cited as infrastructure-layer durable execution tools. — [https://zylos.ai/research/2026-05-30-durable-execution-state-machines-production-ai-agents](https://zylos.ai/research/2026-05-30-durable-execution-state-machines-production-ai-agents)

- **HN — Multi-Agentic Software Development Is a Distributed Systems Problem (3 months ago, 119 points):** Treating multi-agent pipelines as distributed systems reveals FLP impossibility parallels — agents cannot guarantee both safety (produce correct output) and liveness (always eventually produce output). Teams must choose the tradeoff. Practical implication: design explicit abort paths, not just happy paths. — [https://news.ycombinator.com/item?id=47761625](https://news.ycombinator.com/item?id=47761625)

## Gotchas

- **Don't reach for LangGraph's full graph API on day one** — if your workflow is "A → B → C" and failures mean restart, a plain Python loop is correct. LangGraph adds complexity you pay for forever.
- **State schema matters more than the graph structure** — define upfront what each node reads and writes, including reducer logic for lists that grow across steps. Teams that skip this end up with state mutations that silently accumulate or overwrite.
- **Fan-out without a merge strategy produces garbage** — multiple agents writing to a shared "result" field will overwrite each other. Each parallel branch needs its own output key, merged explicitly.
- **Interrupt without durable storage is a race condition** — calling `interrupt()` but storing state in memory means a process restart loses the paused graph. Always pair interrupts with `PostgresSaver` or equivalent.
