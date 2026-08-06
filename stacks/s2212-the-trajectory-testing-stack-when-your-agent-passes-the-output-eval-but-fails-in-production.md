# S-2212 · The Trajectory Testing Stack

Your agent gets an A on output correctness. Your compliance reviewer gives it an F. The tool calls went to the wrong account. The approval gate was skipped. The cost was 40× budget. All invisible to a final-answer eval — all present in every production trace. This is the trajectory testing gap: the execution path is the real artifact, and almost nobody tests it.

## Forces

- **Output-centrism bias.** LLM benchmarks and most eval frameworks score final answers. But in agentic systems, correctness is a property of the path, not the endpoint — a wrong API call producing a right-looking answer is worse than an honest wrong answer.
- **Trajectory failures are invisible to output tests.** Wrong account accessed, missed approval gate, loop without progress, cost overrun — all pass output-level assertions. Trajectory testing is the only way to surface them.
- **The scaffolding gap.** Tracing is often added reactively after a production incident. Trajectory testing needs to be baked into the scaffold, not bolted on. Retrofitting is painful.
- **Root cause attribution is an open problem.** Full traces tell you *what* happened at every step. They do not tell you *which prior step caused the failure* — that requires causal inference, still a research area.

## The move

**Instrument the path, not just the output. Build golden trajectories from production traces. Assert on the execution, not just the result.**

1. **Capture production traces at scale.** Every agent session → trace with `trace_id` correlation, per-step inputs/outputs, tool calls, retrievals, token counts, and latency. Use OpenTelemetry GenAI semantic conventions — `create_agent`, `invoke_agent_client`, `invoke_agent_internal`, `invoke_workflow`, `execute_tool` — with `gen_ai.conversation.id` for session linkage and `gen_ai.provider.name` for model attribution.
2. **Curate 50–500 golden trajectories.** Cover: common happy paths, edge cases, compliance-critical flows (approval gates, PII access), adversarial inputs. These are your canonical correctness dataset — the integration test suite for your agent.
3. **Assert on trajectory properties, not just outputs.** Tool call sequence, API targets, loop counts, approval gate hits, cost accumulation, error recovery paths. Compare against golden trajectory to catch structural deviations.
4. **Run trajectory tests in CI.** "Evals as CI" pattern: every PR runs trajectory regression against the golden set. Fail on cost > 5× median, session duration > 2× P95, or structural deviation from golden path.
5. **Use structured logging with `structlog`** correlating `trace_id` in every log line. Emit cost as a Prometheus gauge and session duration as a histogram per session type. Alert on cost and duration outliers.
6. **Adopt OTEL-native tracing.** Langfuse v4, Braintrust, Arize Phoenix, and LangSmith all consume OpenTelemetry spans. One instrumentation feeds all platforms — no re-instrumentation when switching vendors.

## Evidence

- **Trajectory testing comparison:** Mature agent teams curate 50–500 golden trajectories as their canonical correctness dataset. LangSmith is the default for LangGraph agents; Braintrust for multi-framework deployments; Arize Phoenix for OSS-first or UAE data-residency-sensitive workloads — [genai.qa, "LangSmith vs Braintrust vs Galileo: Agent Trajectory Testing," April 22, 2026, updated July 2, 2026](https://genai.qa/ai-agent-trajectory-testing-2026/)
- **HN multi-agent debugging discussion:** Practitioners describe production agent failures as fundamentally different from API failures — a single task involves multiple LLM calls, tool invocations, and retries; failures are difficult to understand without full trace lineage. Distributed systems reliability patterns (tracing, circuit breakers, retry policies, SLOs) are directly applicable — [Hacker News, "How are people debugging multi-agent AI workflows in production?"](https://news.ycombinator.com/item?id=47358618)
- **OpenTelemetry GenAI conventions:** 5 agent span operations (`create_agent`, `invoke_agent_client`, `invoke_agent_internal`, `invoke_workflow`, `execute_tool`) define the instrumentation standard. All GenAI conventions remain Development (unstable) as of July 2026; only shared core attributes like `error.type` are Stable. Vendor adoption is complete — Langfuse, Honeycomb Agent Timeline, and MLflow 3.11+ all consume this format — [Genαi, "OpenTelemetry GenAI Semantic Conventions 2026," June 17, 2026, updated July 26, 2026](https://genalphai.com/agent-observability-with-opentelemetry-genai-conventions)
- **Root cause attribution gap:** "The agent produced a wrong plan. The trace shows every step. But *which* context item, *which* instruction, or *which* earlier tool result was causally responsible for the wrong plan? This is a research problem — causal attribution in neural networks — that production tooling has not solved." — [Zylos Research, "Agent Observability and Production Debugging," April 29, 2026](https://zylos.ai/en/research/2026-04-29-agent-observability-production-debugging/)
- **Minimum viable observability stack:** Langfuse for trace capture, `structlog` with `trace_id` correlation, cost accumulation as Prometheus gauge, session duration histogram, alert on cost > 5× median and duration > 2× P95 — [Zylos Research, April 29, 2026](https://zylos.ai/en/research/2026-04-29-agent-observability-production-debugging/)

## Gotchas

- **Output eval passes ≠ trajectory eval passes.** A correct answer via a wrong API call, or a correct answer at 40× cost, both pass output-level assertions. Trajectory testing catches these; output-only testing misses them.
- **The root-cause attribution gap is real.** Even with perfect instrumentation, you cannot automatically answer "which step caused this failure." Causal Agent Replay (CAR) and AgentTrace are active research approaches; neither is production-ready tooling as of mid-2026. Budget investigation time accordingly.
- **Tracing retrofitted after incidents is painful.** Instrument the path from day one. The minimum viable stack (Langfuse + structlog + Prometheus metrics) takes under an hour to wire up on a new agent — waiting until after a compliance incident means re-instrumenting under pressure.
- **Trajectory count alone is noise.** 500 golden trajectories covering only happy paths miss the edge cases that cause production incidents. Curate trajectories from actual production failures, not just expected flows.
