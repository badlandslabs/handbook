# S-1013 · The Multi-Agent Boundary Stack — When Two Agents Disagree on What the State Is

You have two agents working on the same task. Both are performing correctly by their own logic. But they have different views of the shared state — different intermediate outputs, different assumptions about what the other already did, different schema versions for the data between them. The result is a plausible-looking final artifact that contradicts itself in ways neither agent can see. This is not a prompt problem. It is a boundary problem.

## Forces

- **Agents are black boxes with invisible state.** Each agent accumulates context during execution. When two agents hand off data, neither can see the other's internal state — only the surface-level output. Subtle context drift between the handoff message and the receiver's interpretation produces errors that look like hallucinations but are really coordination failures.
- **Untyped handoffs kill multi-agent workflows faster than any other issue.** Frameworks handle individual agent capabilities well. What they don't handle: two agents silently overwriting each other's work on shared state. It is a classic race condition, but in AI systems the output looks reasonable, so you don't notice it until production. — HN user on Ask HN multi-agent thread, 2025
- **Shared state solves the visibility problem but creates the ownership problem.** A blackboard — a shared, queryable workspace where agents post findings and subscribe to updates — makes state visible to everyone. But without a controller deciding who writes when, concurrent writes produce "last writer wins" by accident. — Agent Patterns Catalog (experimental status)
- **Typed schemas at agent boundaries are the equivalent of API contracts.** Every agent-to-agent handoff is a data transfer across an implicit trust boundary. Without versioned schemas, a change in one agent's output format silently breaks all downstream consumers. — RaftLabs, 2026
- **Inference cost compounds across agents.** A 4-agent orchestrator-worker workflow costs $5–8 per complex task. Without structured state management, agents re-do work or wait for confirmation they never get, multiplying cost. — RaftLabs, 2026
- **89% of teams have observability but only 52% have evals.** That gap explains why multi-agent debugging is mostly guesswork. — Gartner data cited by RaftLabs, 2026

## The move

The core move: **treat every agent boundary as a typed, versioned, validated interface** — and enforce that interface with the same rigor you'd apply to a microservice API boundary.

### 1. Schema the handoff

Define an explicit output schema for every agent-to-agent handoff. Include version numbers. Include required vs. optional fields. If the receiving agent cannot parse the schema, it fails loudly instead of silently substituting plausible wrong data.

```python
from typing import TypedDict, Literal

class ResearchAgentOutput(TypedDict):
    schema_version: str  # e.g. "1.3.0"
    claims: list[str]    # extracted factual claims
    confidence: float    # 0.0–1.0
    citations: list[dict]
    gaps: list[str]      # what the research did NOT find
```

### 2. Validate before passing

Run deterministic validation on agent output before it crosses a boundary. This catches schema drift, missing required fields, and out-of-range values. It does not catch semantic errors — for that you need cross-verification — but it prevents the class of failures where output looks structured but is malformed.

### 3. Use structured message passing with explicit handoff framing

Instead of just concatenating messages: frame each handoff as `{from_agent, to_agent, task, output, timestamp, schema_version}`. This makes the handoff auditable and allows the receiving agent to understand context without having to re-derive it.

### 4. Implement a coordinator agent for shared-state access

For any state that multiple agents need to read or write: one coordinator owns the state mutation. Workers post findings to the coordinator; the coordinator decides sequencing and aggregates. LangGraph's supervisor pattern implements this with `create_handoff_tool()` and `interrupt_before` checkpoints. No worker writes directly to shared state.

### 5. Cross-verify with a separate validation agent

For high-stakes handoffs, pass the output through a lightweight validation agent that checks: does the output actually satisfy the task? Are there internal contradictions? Does it contradict prior outputs from other agents? This is the generator-verifier pattern (Anthropic, 2026) applied at agent boundaries.

### 6. Log handoffs with full input/output for every boundary crossing

Trace every handoff with its input, the agent's output, and the validation result. This is the only way to debug why a multi-agent workflow produced a contradictory result — the failure mode is invisible without boundary instrumentation.

## Evidence

- **Ask HN thread (47270020):** Practitioners report the #1 underappreciated problem in multi-agent systems is state coordination. One user described running a 13-agent "PAI Family" system where agents collaborate, argue, and bet against each other — and explicitly identified shared-state race conditions as the persistent failure mode. — https://news.ycombinator.com/item?id=47270020
- **RaftLabs production survey:** In a survey of enterprise multi-agent deployments, 1,445% surge in multi-agent inquiries (Gartner, Q1 2024 → Q2 2025). 57% of organizations running agents in production. The report explicitly calls out "untyped handoffs" as the #1 killer of multi-agent projects, and notes 89% have observability while only 52% have evals. — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Agent Patterns Catalog — Blackboard pattern:** Documents the classic shared-state coordination failure: agents wired with point-to-point messaging create a brittle protocol as the agent count grows. The blackboard pattern (shared workspace with controller) solves visibility but requires explicit write-ownership rules to prevent concurrent-write corruption. Catalog rates the pattern "experimental" — production adoption patterns are still emerging. — https://agentpatternscatalog.github.io/patterns/patterns/blackboard.html
- **AutoGen shared-state GitHub discussion (#7144, Dec 2025):** Practitioners building multi-agent systems with planners, executors, reviewers, and tool callers identify shared state fragmentation as the core scaling problem: "context that is generated during execution spreads throughout messages and business logic without a unified state layer." Solutions discussed include dedicated state management layers and explicit handoff contracts. — https://github.com/microsoft/autogen/discussions/7144
- **LangGraph documentation — supervisor pattern:** LangGraph's `create_supervisor()`, `create_handoff_tool()`, and `interrupt_before` primitives implement structured coordination: the supervisor owns the graph state, workers return to the supervisor after each task, and human-in-the-loop approval gates can pause execution at any handoff boundary. — https://reference.langchain.com/python/langgraph-supervisor
- **Anthropic Claude Blog — Generator-Verifier pattern (Apr 2026):** Documents the generator-verifier coordination pattern: one agent produces output, a separate verifier evaluates against explicit criteria, feedback returns for revision, loop continues until accepted or max iterations reached. Applicable at agent boundaries for high-stakes handoffs where semantic correctness matters more than speed. — https://claude.com/blog/multi-agent-coordination-patterns

## Gotchas

- **Adding an agent does not fix a coordination problem.** Teams add a "coordinator agent" to solve state disputes, but the coordinator itself needs its own coordination protocol. The recursion bottoms out only with structured, typed handoffs — not more agents.
- **Schema versioning is not optional.** An agent update that changes output format will silently break every downstream agent if the schema has no version number. Bump the version, run the old output through the new schema, fail loudly if it doesn't parse.
- **Shared mutable state is not the same as shared accessible state.** A database that all agents can write to is not a coordination solution — it is a race condition with a permanent address. The blackboard pattern works because a controller sequences the writes, not because everyone can write.
- **Checkpointing state is not the same as checkpointing reasoning.** LangGraph's checkpointing saves the state but not the chain of reasoning that produced it. When a multi-agent workflow fails, you need both — the state to resume from and the trace of why each agent made each decision.
- **Cost compounds invisibly without handoff validation.** An agent that cannot parse a handoff will often re-attempt the work rather than fail. Without boundary validation, you pay for the re-computation without knowing it happened.
