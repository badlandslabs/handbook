# S-2312 · The Graph-First Stack — When Your Agentic Pipeline Becomes a Spaghetti Chain

Your pipeline started simple: one prompt, one tool, one response. Six months later it has 14 conditional branches, a "just-in-case" retry layer, three agents that sometimes call each other, and nobody knows why it works on Tuesdays. The problem isn't your code. The problem is that you built a graph without drawing it first. [S-2308](s2308-the-specialization-split-stack-when-one-agent-is-not-enough.md) covers when to split agents. This entry covers how to wire them together so the system survives contact with production.

## Forces

- **Agents are stateless by default.** The LLM has no memory between calls. Without an explicit state model, every "multistep" workflow is just a brittle sequence of API calls held together by convention and hope.
- **Implicit graphs are undebuggable.** When orchestration lives in if/else chains and ad-hoc logging, you can't inspect execution paths, replay failures, or reason about recovery. What looks like a pipeline is actually a graph you never drew.
- **Tools are edges, not magic.** Giving an agent 30 tools without priority routing is how you get 22% context collapse and 13% tool overload — not from bad tooling, from bad graph design.
- **Premature orchestration is the new premature optimization.** Reaching for LangGraph or CrewAI before understanding the control flow you need adds framework debt on top of design debt.

## The move

Model the workflow as an explicit directed graph *before* writing any agent code. Agents are nodes. Tool calls and handoffs are edges. State flows between nodes.

**1. Start with the ReAct loop as your atomic node.**
Every agent is a cycle: `Observe` (gather context) → `Think` (LLM reasons) → `Act` (call tool or produce output) → `Evaluate` (is the goal met? loop or exit). This is the node implementation, not the architecture.

**2. Use typed state as your graph's currency.**
Define a Pydantic model or dataclass for the workflow state that every node reads from and writes to. LangGraph calls this the `StateGraph`; PydanticAI calls it `result_type`. The model is the contract between nodes. A practitioner on HN put it: "I'm building a non-trivial AI app and the validation and dependency injection is such a great addition compared to using the LLM libraries directly."

**3. Route with structured outputs, not string matching.**
Conditional edges should dispatch on enum values or typed discriminators from an LLM `function_call` or structured output — not on parsing plain text. This keeps the graph deterministic and typed end-to-end.

**4. Permit cycles, but cap them explicitly.**
Loops are necessary for iterative refinement and retry logic. Set a `max_iterations` counter in state and trap at the boundary. Without a hard cap, a looping agent becomes a runaway process with a token budget.

**5. Checkpoint at node boundaries, not just at the end.**
On failure, the system should resume from the last completed node, not re-execute from the start. Production Kubernetes deployments for multi-agent systems at enterprise scale use Redis or PostgreSQL for checkpoint persistence. This is what turns an "agent" into a durable workflow.

**6. Build a router node for fan-out, not a mega-agent.**
A central orchestrator node (the "brain") classifies intent and routes to specialist nodes. Microsoft ISE documented this evolution: their retail customer started with a modular monolith router pattern, then decomposed into microservices when agents needed cross-system reuse. Don't skip the router pattern — it prevents the "every agent calls every other agent" mesh that produces circular dependencies.

## Evidence

- **Enterprise LangGraph deployment (support ticket routing):** A B2B SaaS company deployed a LangGraph graph with three specialist nodes — a classification agent (identifies product area, urgency, contract tier), a knowledge retrieval agent (fetches docs and prior tickets), and a resolution agent (generates draft response). Critical tickets route directly to a senior engineer with a pre-composed escalation summary. Result: first response time dropped 61%, CSAT increased from 3.8 to 4.4 out of 5. — [Gheware DevOps AI Blog](https://devops.gheware.com/blog/posts/langgraph-multi-agent-orchestration-enterprise-2026.html)

- **Coding agent on LangGraph (Qodo):** Qodo chose LangGraph specifically because the graph model let them express their coding agent's multi-step workflow as explicit state transitions rather than implicit control flow. The HN discussion that followed became a framework comparison forum, with PydanticAI praised for validation and dependency injection, and smolagents noted as tightly coupled to HuggingFace. — [HN discussion, March 2025](https://news.ycombinator.com/item?id=43468435)

- **Microsoft ISE coordinator pattern (microservices evolution):** Microsoft's Industry Solutions Engineering team documented a retail customer's evolution from a modular monolith router pattern (one orchestrator, one agent per request) to a coordinator-based multi-agent microservices architecture. Key insight: the initial router pattern failed at scale because agents were tightly coupled to the chatbot application, blocking cross-system reuse. The fix was moving agents to independent services with a central coordinator — not redesigning the agents. — [Microsoft ISE Developer Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Enterprise failure mode data (2026):** Context collapse affects 22% of multi-step pipelines when agents lose task context across transitions. Tool overload (giving a single agent 30+ tools without priority routing) accounts for 13% of failures. Both are graph design problems, not model problems. — [Lines & Circles Enterprise AI](https://linesncircles.com/Blog/Enterprise/AI_Agent_Orchestration_2026)

## Gotchas

- **Reaching for a framework before designing the graph.** LangGraph and CrewAI are popular (36k and 44k GitHub stars respectively as of 2026) but they impose graph semantics that you need to understand first. Practitioners on HN report hand-rolling agents with async Python and append-only message lists for production — simpler, more debuggable, until you need cycles and checkpointing.
- **No loop counter.** Without an explicit `iteration` or `step` count in state, you cannot distinguish "working through step 3 of a 5-step plan" from "looping indefinitely." Every runaway agent is a missing counter.
- **State mutation without schema.** When state is a plain dict mutated in-place across nodes, you lose the ability to replay or diff. Typed state models catch schema drift at runtime, not in production.
- **Human-in-the-loop treated as optional.** Approval gates, pause/resume, and override points need to be first-class graph nodes — not afterthought exception handlers. LangGraph's `interrupt` primitive exists because it is structurally necessary, not ergonomically convenient.
