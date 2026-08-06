# S-2253 · The Agent Observability Stack — When You Can't Tell If Your Agent Is Working

Your agent completes tasks and returns answers. But you can't see whether it took the right path, how many tool calls it made, whether it retried a failure three times before succeeding, or why it cost $2.40 on a job that should have been $0.15. Agents operate probabilistically over multiple steps — output quality, latency, and cost all vary per run. The standard observability stack for deterministic services misses all of this. You need a tracing layer built for multi-turn agent trajectories, with evaluation scores and cost attribution at every step.

## Forces

- **Agents fail silently in ways services don't.** A microservice that returns a 200 OK either worked or lied. An agent that returns "Done" may have taken the wrong path, called the wrong tool, or spent 10x budget to arrive there. No HTTP status code tells you.
- **Quality degrades without anyone noticing.** Prompt changes, model swaps, and upstream API drift all silently erode agent quality. Without continuous eval scoring on production traces, regression surfaces only as user complaints.
- **Three layers need monitoring simultaneously** — per-call metrics (latency, tokens, errors), per-feature aggregates (p50/p95 latency, cost per call, eval score), and per-user or per-tenant breakdowns for multi-tenant deployments.
- **The through-line is OpenTelemetry.** Every major observability platform — LangSmith, Langfuse, Helicone, Braintrust, AgentOps, Arize Phoenix — now supports the OpenTelemetry GenAI semantic conventions. The architectural decision is not which tool to use but whether to instrument once and route traces to multiple backends, or accept a single-platform lock-in.

## The move

**Instrument the agent trajectory, not just the LLM call.** Every step — tool calls, tool responses, intermediate reasoning, final output — becomes a trace span. Attach metadata to each span: model, temperature, token counts, cost, latency, and any custom labels (task type, user tier, feature name).

**Layer the monitoring stack in three tiers:**

- **Tracing layer** — captures every agent step as a structured span. Use OpenTelemetry GenAI semantic conventions so traces are vendor-neutral and portable. The trace is the ground truth of what the agent did.
- **Evaluation layer** — runs graders against each completed trajectory. Graders contain assertions: did the agent call the right tool? Did the final state match the expected outcome? Score each run, store the result, track rolling averages per feature.
- **Alerting layer** — watches for regressions. Eval score drops, cost spikes, latency blowups, or error rate increases should trigger alerts. Set deployment gates: a prompt or model change cannot reach production users unless it passes the eval threshold on the held-out test set.

**Choose instrumentation depth based on the agent's autonomy level.** Low-autonomy agents (single tool call, predictable path) need per-call tracing. High-autonomy agents (multi-step, branching, self-correcting) need full trajectory tracing with step-level metadata and cost attribution.

**Pick a trace backend based on team constraints:**

| Tool | Best for |
|------|----------|
| LangSmith | Deep LangChain/LangGraph integration, full eval pipeline |
| Langfuse | Self-hosted, open-source, compliance-sensitive teams |
| Helicone | Gateway-level cost tracking, fast setup, proxy-based |
| Braintrust | Eval-first teams, regression testing, OpenTelemetry-native |
| AgentOps | Dedicated agent products, agent-specific session tracking |
| Arize Phoenix | ML teams already on Arize, offline eval and LLM tracing |

## Evidence

- **Microsoft ISE engineering blog:** A retail partner evolved from a monolithic single-agent router to a microservices coordinator pattern. Critical to the migration was instrumenting every inter-agent call as a trace span with latency and error metadata. Without this, coordinating 6 specialized agents across teams produced undebuggable failures — "it didn't work" had no data behind it. The post documents how observability infrastructure was a prerequisite for the architectural shift, not an afterthought. — [Microsoft ISE Dev Blog, June 2026](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **LLM observability practitioner post:** A developer survey of production LLM apps found that teams without three-tier monitoring (per-call, per-feature aggregate, per-tenant) consistently discovered issues from social media rather than dashboards. The post documents the three-layer metric taxonomy: per-call data (model, tokens, latency, cost, status), per-feature aggregates (call rate, p50/p95/p99 latency, error rate, cost per call, nightly eval score), and per-tenant breakdowns for multi-tenant deployments. — [Manvendra Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-observability-tracing-langsmith-2026/)
- **Tool comparison analysis:** An independent 2026 comparison of 12 agent observability platforms found that 89% of agent teams have some form of observability in place, but one in three still describe quality tracking as "mostly vibes." LangSmith's native LangGraph integration, Langfuse's self-hosted model, and Helicone's gateway-level proxy approach each serve distinct team profiles. OpenTelemetry GenAI semantic conventions are now the common denominator across all 12 platforms, making vendor portability a real architectural option rather than a theoretical one. — [Spanora, February 2026](https://spanora.ai/blog/ai-agent-observability-tools-compared-2026)

## Gotchas

- **Tracing every step generates enormous data volume.** A 20-step agent produces 20+ spans per run. At production scale, this is gigabytes per day. Budget storage costs and implement trace sampling — sample 100% of failures, 1-10% of successes.
- **Eval without regression tests is theater.** Running a grader on production traces and recording the score is monitoring. Running the same grader against a held-out test set on every model or prompt change is regression testing. Most teams do the former and call it done.
- **Custom labels are only useful if you query them.** Adding `task_type`, `user_tier`, and `feature_name` to every span is low-cost. Using those labels to find "what is the eval score for the summarize feature on enterprise tier" is where the value lives. Define the queries before adding the labels.
- **Vendor lock-in is real despite OTEL compatibility.** Every platform surfaces OTEL-compatible traces, but the eval scoring schemas, alert configurations, and dashboard UIs are proprietary. An OTEL export path does not mean you can migrate your eval thresholds overnight.
