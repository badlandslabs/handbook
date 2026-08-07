# S-2263 · The Agent Observability Stack — When Your Agent Runs But Nobody Knows What It Did

You shipped an agent to production. It handles multi-step tasks, calls tools, loops, recovers. Three weeks in, a user reports it deleted something it shouldn't have. You open the logs and find: one POST request, one 200 OK. You have no idea what happened between those two events. This is the observability gap — and unlike traditional software, agent failures hide in the steps between call and response, not in the call itself.

## Forces

- **Agents are trees, not lines** — a single user request may spawn 5–15 internal LLM calls, tool executions, retrievals, and sub-agent handoffs. Traditional HTTP monitoring sees one request; it cannot see the execution tree inside
- **Traditional stack traces don't work for AI** — agents are probabilistic, not deterministic. The same input can produce different outputs. Errors surface in middle steps, not in final responses
- **Token costs are invisible until the invoice** — agents can consume 500–50,000 tokens per request, and multi-step loops compound that fast. Without per-call cost tracking, budget overruns are discovered retrospectively
- **Intermediate failures are the real failure mode** — the agent may complete the task but use the wrong tool at step 3, or loop 20 times before converging. Monitoring only the final output misses the failure that actually matters
- **Ad-hoc logging scales poorly across teams** — print statements and log files work for single-agent debugging; they break down when multiple agents run concurrently or when you need to compare traces across environments

## The Move

Build observability into the agent runtime itself, capturing every step as structured data. The consensus across Langfuse, OpenTelemetry's GenAI SIG, LangSmith, and open-source practitioners converges on a layered approach:

- **Trace every LLM call** — log the full prompt, completion, model parameters, token usage, latency, and cost at the individual call level. This is the atomic unit of agent observability
- **Attach spans to every tool invocation** — instrument tool calls with input arguments, output, duration, and success/failure status. A tool call without a trace is a black box
- **Capture control flow as first-class events** — sub-agent handoffs, loop iterations, and branching decisions should be represented as trace spans, not buried in logs
- **Adopt OpenTelemetry GenAI semantic conventions** — the OTel GenAI SIG (led by IBM and Google, formalized in 2025) defines standard attributes (`gen_ai.*`) for model names, token counts, operation types, and cost. Using these conventions avoids vendor lock-in and lets you pipe traces to any compatible backend (Datadog, Grafana, Jaeger, Honeycomb)
- **Group traces by session and user** — agents are stateful and multi-turn. Correlate traces to conversations and user identity so you can replay a full execution tree, not just isolated calls
- **Track cost per agent, per user, per feature** — set daily and weekly budgets with alerts at 80% threshold. An agent at 2% error rate that self-recovers via retry is healthy; one climbing toward 5% needs investigation

## Evidence

- **OpenTelemetry GenAI SIG (IBM + Google, March 2025):** Published formal semantic conventions for AI agent tracing — `gen_ai.*` attributes for model names, token counts, operation types, and cost — enabling vendor-neutral instrumentation across any OTel-compatible backend. OpenLLMetry (7,360 GitHub stars, Apache-2.0) provides the reference implementation, instrumenting LangChain, LlamaIndex, CrewAI, and other frameworks with a single `Traceloop.init()` call
  — [opentelemetry.io/blog/2025/ai-agent-observability](https://opentelemetry.io/blog/2025/ai-agent-observability)

- **Langfuse production guide (updated March 2025):** Documents that complete agent observability requires capturing LLM calls (prompts, completions, cost), tool calls (chosen tool, arguments, output), control flow (subagents, handoffs, loop iterations), session context, and quality signals — all correlated as structured traces. Their self-hostable, open-source platform is the most common LangSmith alternative for teams with data-sovereignty requirements
  — [langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse)

- **OpenHelm production guide (Max Beech, October 2025):** Frames the structural difference between traditional software (deterministic, same input → same output, stack traces work) and AI agents (probabilistic, same input → different outputs possible, failures hide in middle steps). Documents the five pillars of agent observability: structured logging (JSON per event), trace-level tracing (span trees), metrics (error rates, latency, token costs), debugging workflows (reproduce locally, replay traces), and cost tracking per agent/user/feature
  — [openhelm.ai/blog/ai-agent-logging-observability-production](https://www.openhelm.ai/blog/ai-agent-logging-observability-production)

- **docker-agent OTel integration (Docker, 2026):** Demonstrates the pattern of emitting OTel GenAI (`gen_ai.*`) and MCP (`mcp.*`) spans covering agent turns, model calls, tool calls, sub-agent handoffs, and provider fallbacks — all under a single W3C `traceparent` context so the full run renders as one connected trace tree. Ships spans locally as no-ops without a configured OTLP endpoint, making local development frictionless
  — [docs.docker.com/ai/docker-agent/community/opentelemetry](https://docs.docker.com/ai/docker-agent/community/opentelemetry)

## Gotchas

- **Don't monitor only the final output** — an agent can complete a task while using the wrong approach at every intermediate step. Trace the full execution path, not just the terminus
- **Alert on error _rates_, not individual failures** — LLMs refuse, timeout, or return unexpected formats. A self-recovering 2% error rate is healthy; a 2% rate climbing to 5% needs attention. Individual failure alerts create noise
- **Don't skip token cost tracking** — agents can burn through 500–50,000 tokens per request. Without per-call cost visibility, budget overruns are discovered on the monthly invoice, not during the sprint
- **Don't instrument without a debugging workflow** — traces without a process to act on them create data debt. Build the workflow first: reproduce failures locally, trace full execution paths, identify prompt regressions
- **Don't mix observability vendors blindly** — LangSmith, Langfuse, Arize, and Laminar each have distinct strengths. LangSmith integrates tightly with LangChain; Langfuse supports self-hosting; Laminar offers browser-agent session replay tied to traces. Choosing one and committing to its SDK is better than trying to double-instrument
