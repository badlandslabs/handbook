# Trajectory Testing — Evidence Bank
*Last updated: 2026-08-06*

## Primary Sources

### 1. genai.qa — LangSmith vs Braintrust vs Galileo: Agent Trajectory Testing (April 22, 2026, updated July 2, 2026)
**URL:** https://genai.qa/ai-agent-trajectory-testing-2026/
- Trajectory testing evaluates multi-step path (tool calls, state transitions, approval gates, error recovery, loop behavior, budget adherence), not just final answer correctness
- Golden trajectories: 50–500 curated trajectories covering common flows, edge cases, compliance-critical scenarios, adversarial inputs — canonical correctness dataset for agent systems
- LangSmith = default for LangGraph agents; Braintrust = multi-framework deployments; Arize Phoenix = OSS-first / UAE data-residency-sensitive
- Scenario table: correct output via wrong API path passes output eval but fails trajectory eval; correct answer at 40× cost passes output eval but fails trajectory eval
- "Evals as CI" pattern: trajectory regression on every PR

### 2. Zylos Research — Agent Observability and Production Debugging (April 29, 2026)
**URL:** https://zylos.ai/en/research/2026-04-29-agent-observability-production-debugging/
- Core epistemological challenge: with API you know what happened; with agent you don't know why and the what is probabilistic
- Root cause attribution gap: "trace shows every step, but which context item or earlier tool result was causally responsible? — research problem production tooling has not solved"
- Minimum viable observability stack: Langfuse + structlog with trace_id correlation + Prometheus cost gauge + session duration histogram + alerts
- Oodle.ai: $10/million agent traces (HN Show HN, ~18 days ago)
- Trainly: free 72-hour production trace audit

### 3. Genαi — OpenTelemetry GenAI Semantic Conventions 2026 (June 17, 2026, updated July 26, 2026)
**URL:** https://genalphai.com/agent-observability-with-opentelemetry-genai-conventions
- 5 agent span operations: create_agent (CLIENT), invoke_agent_client, invoke_agent_internal (INTERNAL), invoke_workflow, execute_tool
- All GenAI conventions remain Development (unstable) as of July 2026; only shared core like error.type Stable
- Canonical docs moved to open-telemetry/semantic-conventions-genai repository
- gen_ai.provider.name replaces deprecated gen_ai.system (v1.37+)
- Vendor adoption: Langfuse, Honeycomb Agent Timeline, MLflow 3.11+ all consume this format
- Minimum viable telemetry: gen_ai.conversation.id, gen_ai.agent.name, gen_ai.operation.name, gen_ai.provider.name, model, both token counts

### 4. Braintrust — Agent Tracing: How to Debug AI Agents in Production (June 26, 2026)
**URL:** https://www.braintrust.dev/articles/agent-tracing-debug-ai-agents-production
- Flat logs leave every step disconnected from the next
- Example: support agent gives wrong refund answer; log shows only final response, not the retrieval or LLM call that produced it
- Traces capture inputs, outputs, timing, tool calls, retrievals, model calls, state changes
- Turning failing traces into regression evals: pattern for eval-as-CI workflow

### 5. Hacker News — How are people debugging multi-agent AI workflows in production? (4 months ago)
**URL:** https://news.ycombinator.com/item?id=47358618
- Multi-agent workflows share characteristics with early distributed systems
- Failures difficult to understand — hard to trace where issues originated
- Traditional reliability patterns (tracing, circuit breakers, retry policies, SLOs) directly applicable
- Agent Sentinel AI product referenced as solution

### 6. Agent MarketCap — OpenTelemetry GenAI Semantic Conventions 2026 (April 10, 2026)
**URL:** https://agentmarketcap.ai/blog/2026/04/10/opentelemetry-genai-semantic-conventions-agent-observability-2026
- Prior state: teams staring at logs with no model name, token count, trace_id, or parent span
- Langfuse, LangSmith, Helicone all competing without shared standard until GenAI semconv
- GenAI semconv = enabling vendor-neutral instrumentation

### 7. IcyFeather233/Awesome-LLM-Agent-Trajectory-Analysis (TSE 2026)
**URL:** https://github.com/IcyFeather233/Awesome-LLM-Agent-Trajectory-Analysis
- Survey accepted to IEEE Transactions on Software Engineering (TSE 2026)
- Agent failures are not deterministic code bugs but embedded in long, language-heavy, multi-step trajectories
- Trajectory analysis = core path for: diagnosing failures, attributing root causes, guiding system-level fixes
- AgentTrace: causal tracing framework for post-hoc failure diagnosis in multi-agent workflows — reconstructs causal graphs from execution logs, traces backward from errors, ranks candidate root causes without LLM inference at debug time
- Causal Agent Replay (CAR): counterfactual interventions on individual steps within trajectories to quantify causal impact

### 8. HN Show HN — Oodle.ai (18 days ago)
**URL:** https://news.ycombinator.com/item?id=48907615
- $10 per million agent traces
- Kiran and Vijay building agent observability platform

### 9. HN Principles for Production AI Agents (July 28, 2025)
**URL:** https://news.ycombinator.com/item?id=44712315
- 128 points, 19 comments on app.build "Six Principles for Production AI Agents"
- Debate on LLM-as-judge effectiveness: empirical evidence requested; skeptic found LLMs NOT good critics in internal experiments
- App.build combines tracing with simulation: test across thousands of scenarios and personas before shipping; step-by-step replay from any checkpoint

## Key Cross-Cutting Findings

1. **Trajectory testing ≠ output eval.** The execution path is the real artifact. 40× cost, wrong API targets, missed approval gates all pass output-level assertions.
2. **OTEL GenAI semconv is the instrumentation standard** — vendor-neutral, 5 span operations, adopted by Langfuse/LangSmith/Arize/Honeycomb.
3. **Golden trajectories are the test suite** — 50–500 curated from production failures, not just happy paths.
4. **Root cause attribution is an open research problem.** Traces show every step; they don't automatically identify which step caused the failure.
5. **Minimum viable stack is achievable in under an hour** — Langfuse + structlog + Prometheus metrics.
