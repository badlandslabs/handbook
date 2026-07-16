# S-1203 · The Agent Trace-and-Replay Stack — When You Pay Full Price to Re-Run a Workflow You Already Ran

Your agent is 37 steps into a 45-step compliance audit. Step 38 fails — a subtle schema mismatch in the data it passed to a downstream tool. You fix the tool prompt. You re-run. Forty-five steps. Forty-five LLM calls. $2.40 gone. This happens eight more times before the sprint ends. The cost of debugging agents is billed in re-execution. The fix: instrument every step from day one, and build the replay surface before you need it.

## Forces

- **Agents are non-deterministic by nature.** Traditional APM assumes the same input → same output. Replaying an agent request does not reproduce the same failure — the model may take a different path the second time.
- **Debugging multi-agent coordination is harder than single-agent failures.** As one HN contributor put it: "The hardest failure mode isn't a single agent hallucinating — it's Agent A correctly doing its job but passing slightly malformed state to Agent B, which then confidently executes a destructive action. By the time you see the error, the root cause is three steps up the chain." Standard OpenTelemetry gives latency and token counts per LLM call but no visibility into cross-agent state handoffs.
- **Enterprise adoption has outpaced tooling.** Multi-agent architecture adoption jumped from 23% to 72% of enterprises from 2024 to 2025. Yet only 37.3% of agent teams run online production evaluations. The industry built agents faster than it built the tools to monitor them.
- **Re-running for debugging is economically unsustainable.** A single agent run with 30+ steps, multiple tool calls, and API rate-limit pauses can cost dollars per execution. Teams report burning $100+ per day on re-runs once workflows are non-trivial.

## The Move

**Record everything, replay surgically.** Treat agent execution like flight data recorder — every step checkpointed, with inputs and outputs, so you can fork from any point and replay only the downstream steps.

### Instrument with OpenTelemetry first

OpenTelemetry is the converging standard. AutoGen, LangGraph, and most major frameworks ship with OTel-compatible tracing built in. Install the SDK, point at any backend (Jaeger, Tempo, your cloud APM), and get structured spans for every LLM call, tool invocation, and agent handoff from day one. This is table stakes — not optional.

### Add framework-specific tracing on top

LangSmith (deepest LangChain/LangGraph integration; processes traces from 400+ companies), Langfuse (open-source, self-hostable, framework-agnostic), and Arize Phoenix (ML-grade eval primitives, OpenTelemetry-native) each occupy different trade-off surfaces. Pair one of these with whole-stack APM (Datadog or Honeycomb) for infra-layer correlation.

### Build the replay surface before you need it

The emerging pattern — independently built by multiple teams as of 2025-2026 — treats agent traces as versioned, forkable artifacts:

1. **Record every step** — inputs, outputs, LLM calls, tool invocations, full state. Persist to PostgreSQL or SQLite.
2. **Visualize as a DAG** — timeline view of execution path so you can see where the branch diverged.
3. **Fork at any step** — fix the prompt or tool, then replay only steps downstream of the fork point. No re-execution of the upstream path.
4. **Diff runs** — compare two executions side-by-side to understand behavioral regressions.

Tools in this space: Time Machine (TypeScript SDK + LangChain adapter, PostgreSQL backend), Agent Replay (SQLite + TypeScript CLI, 100% local), AgentLens (open-source, self-hostable alternative to LangSmith), Retrace (cloud, replay + fork + share).

### Tag state handoffs explicitly

Multi-agent failures are overwhelmingly handoff failures. Add explicit instrumentation on every agent-to-agent state pass: what was passed, in what format, at what step. This is the "root cause is three steps up the chain" problem made traceable.

## Evidence

- **HN Ask HN (47358618):** "OpenTelemetry and standard observability stacks are great for seeing the latency and token counts of individual LLM calls, but they break down when you try to debug the coordination between agents. The hardest failure mode we've had to debug isn't a single agent hallucinating; it's Agent A correctly doing its job, but passing slightly malformed state to Agent B, which then confidently executes a destructive action. By the time you see the error, the root cause is three steps up the chain." — [HN discussion: How are people debugging multi-agent AI workflows in production?](https://news.ycombinator.com/item?id=47358618)
- **Research synthesis (AgentMarketCap, 2026-04):** "Multi-agent architecture adoption jumped from 23% to 72% of enterprises (2024→2025). 49% of enterprises run 10+ agents in production simultaneously. Only 37.3% of agent teams run online production evaluations." — [Agent Observability in 2026: How LangFuse, Arize Phoenix, and OpenTelemetry Are Closing the Production Debugging Gap](https://agentmarketcap.ai/blog/2026/04/11/agent-observability-distributed-tracing-langfuse-arize-opentelemetry-2026)
- **Show HN (47315394):** "When an agent fails at step 9, you should be able to fork from step 8 and replay only what is downstream. Teams burning $100+ per day on re-runs is normal once you are running non-trivial workflows in production." — [Show HN: Time Machine – Debug AI Agents by Forking and Replaying](https://news.ycombinator.com/item?id=47315394)
- **Show HN (47205382):** "I built AgentLens because debugging multi-agent systems is painful. LangSmith is cloud-only and paid. [AgentLens is] open-source, self-hostable." — [Show HN: AgentLens – Open-source observability for AI agents](https://news.ycombinator.com/item?id=47205382)
- **AutoGen documentation:** "AutoGen has built-in support for tracing and observability. This capability is powered by the OpenTelemetry SDK. Compatible with any OpenTelemetry-compatible backend." — [Tracing and Observability — AutoGen (Microsoft)](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tracing.html)

## Gotchas

- **Instrumentation is not optional retro-fit.** Adding tracing to an agent after it has failed in production means you have no historical traces to replay. OTel must be in from step one.
- **High-cardinality trace storage burns money fast.** A single 30-step agent run with full LLM call inputs/outputs stored per step can be megabytes. Budget for storage tiering (hot for recent runs, cold for archived) before it surprises you.
- **Replay does not guarantee deterministic reproduction.** The same input to a non-deterministic model can produce a different output. Replay helps you inspect what happened; it doesn't fully close the non-determinism gap. Use it to narrow the hypothesis, not to prove the fix works.
- **Cross-agent state handoffs need explicit schema contracts.** If Agent A passes a dict to Agent B and B's schema expectations drift, the failure looks like B's fault. The fix is contract-level validation at every handoff, not better tracing after the fact.
