# S-1888 · The Agent Observability Stack — When You Know What Happened But Not If It Was Right

Your agent is instrumented. You see every tool call, every LLM span, every latency number. Dashboards are green. Then a user reports it confidently sent a customer the wrong refund amount. You open the trace, see it called the right tools in the right order, and have no idea why the output was wrong. You have full observability and zero answers. This is the observability trap: 89% of teams have tracing in place, but only 37% run online evaluations that would tell them whether their agent was actually correct.

## Forces

- **Tracing tells you what happened; evals tell you if it was right** — these are different capabilities, and most teams conflate them
- **Agents are non-deterministic by design** — the same input can produce different outputs on different runs, so replay-based debugging breaks
- **Semantic failures are invisible to syntactic tooling** — a confident wrong answer returns HTTP 200; traditional APM sees nothing
- **Context accumulates across turns** — a session's state depends on every prior tool result, retrieved document, and LLM response, requiring session-level tracing
- **Multi-agent architectures compound the tracing problem** — nested agents, tool call cascades, and cross-agent handoffs require tree-structured spans, not flat logs
- **OpenTelemetry GenAI conventions are still in development** — no stable standard as of mid-2026, creating fragmentation across observability platforms

## The Move

The core pattern is a three-layer stack: **trace → evaluate → act**. Tracing captures what the agent did. Evaluation scores whether it was correct. Action closes the loop by improving prompts, fixing tool definitions, or updating test datasets.

### Layer 1 — Structured Tracing

- Instrument every LLM call as a span: input prompt, model, temperature, token count, output, latency, cost
- Instrument every tool call as a nested span: tool name, arguments, response, duration
- Propagate a stable `trace_id` through all sub-agent calls and tool invocations
- Group traces by session to reconstruct the full conversation tree
- Capture the complete prompt context at each step — what documents were retrieved, what memory was read, what prior tool results were included

### Layer 2 — Evaluation Pipeline

- Run **offline evals** against a curated test dataset before every deployment (evals-as-CI pattern)
- Run **online evals** on a sampled percentage of production traces (10–20%) continuously
- Use **LLM-as-judge** for automatic scoring: compare agent output against reference answers or check for specific quality criteria
- Track **eval scores over time** with alerting on degradation — a drop from 91% to 84% quality triggers a notification even if latency is fine
- Sample production failures, annotate them, and add them back to the test dataset (the flywheel)

### Layer 3 — The Closed Loop

- Connect observability to action: production traces feed test datasets, which feed evals, which drive prompt/tool improvements
- Use AI-assisted debugging sparingly — ask "why did the agent do this?" in natural language on a trace to get hypotheses, not diagnoses
- Track the **seven metrics that matter**: LLM latency, tool call frequency and duration, error rate by type, context length per session, eval score, and user satisfaction signal
- Avoid buying platforms that log LLM calls but can't reconstruct the reasoning chain from a session replay — they're logging solutions, not observability solutions

### Tool Choices

| Tool | Type | When to use |
|------|------|-------------|
| **LangSmith** | Proprietary SaaS | Already using LangChain/LangGraph; want zero-config LangGraph tracing with Studio replay |
| **Langfuse** | Open-source (MIT), self-hostable | Need data sovereignty, self-hosting, or OpenTelemetry-native ingestion; acquired by ClickHouse Jan 2026 |
| **Arize Phoenix** | Open-source, free | Fast local debugging, CI integration, RAG drift detection, offline evals; OTel-native |
| **OpenLLMetry (Traceloop)** | Open-source | Emit OTel traces to any backend; good for teams with existing Datadog/Grafana stacks |
| **OpenTelemetry GenAI conventions** | Standard (dev status, 2026) | Use for standardized span attributes (`gen_ai.*`) across providers; not yet stable |

## Evidence

- **Survey data — observability gap:** LangChain's State of Agent Engineering (June 2026, n=1,340 practitioners) found 89% have implemented observability for their agents, but only 52.4% run offline evaluations and just 37.3% run online evaluations. Human review remains the dominant eval method at 59.8%, followed by LLM-as-judge at 53.3%. — [LangChain State of Agent Engineering 2026](https://www.langchain.com/state-of-agent-engineering)

- **Platform adoption and evaluation cross-reference:** The same LangChain survey showed observability is near-universal (89%) while production quality remains the #1 barrier (32% citing accuracy/consistency/hallucinations). An AgentMarketCap analysis (April 2026) cross-referenced this gap: teams with full tracing but no eval pipeline can detect that an agent called a tool, returned a result in 200ms, and generated a response — but cannot systematically verify that the response was accurate. — [AgentMarketCap: Agent Observability 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-observability-distributed-tracing-langfuse-arize-opentelemetry-2026)

- **Multi-agent tracing requirements:** Langfuse added Agent Graphs in November 2025, visualizing execution flow for multi-step agents by inferring graph structure from observation timings and nesting. LangSmith's LangGraph tracing captures every node, edge, and state transition automatically. A Datacamp comparison (2026) notes this matters because agents that spawn sub-agents or loop over tool calls require tree-structured span hierarchies, not flat log streams. — [Datacamp: Langfuse vs LangSmith 2026](https://www.datacamp.com/blog/langfuse-vs-langsmith)

## Gotchas

- **89% observability ≠ 89% understanding.** Basic tracing (logging LLM calls with inputs/outputs) is table stakes. It tells you the skeleton of what happened. Without evaluation, you still can't answer "was this correct?"
- **OpenTelemetry GenAI conventions are not stable.** As of mid-2026, all GenAI-specific span attributes (`gen_ai.*`) remain in Development status. If you're building custom OTel instrumentation, expect breaking changes.
- **LLM-as-judge eval pipelines drift.** The judge model itself changes over time, so your eval pass rate can shift not because the agent changed but because the judge did. Pin judge model versions.
- **Sampling is not enough for high-stakes domains.** If your agent approves refunds, sends emails, or moves money, 10–20% sampling means 80–90% of production runs go unevaluated. Either sample smarter (prioritize high-value, anomalous, or flagged traces) or evaluate everything.
- **Auto-diagnosis features compound uncertainty.** Using a non-deterministic LLM to debug another non-deterministic agent's failure adds noise rather than reducing it. Treat AI-assisted debugging as a hypothesis generator for human review, not an autonomous root-cause engine.
