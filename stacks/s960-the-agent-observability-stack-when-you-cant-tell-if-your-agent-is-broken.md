# S-960 · The Agent Observability Stack — When You Can't Tell If Your Agent Is Broken

Your AI agent works in development. It passes tests. You deploy it. Three days later a user reports it gave a completely wrong answer — but the system returned 200 OK the entire time. Without observability, debugging an agent is like debugging a web app with no logs: you can't see which tools it called, what the LLM returned at each step, why it chose one path over another, or where the reasoning broke down.

## Forces

- Agents are non-deterministic by design — the LLM decides the execution path at runtime, so you can't predict the control flow to instrument it in advance
- Agent failures are quiet — the pipeline returns 200 OK, each step looks fine in isolation, and the wrong conclusion surfaces three steps later as a downstream symptom
- Agent cost and latency vary 10x based on reasoning path — a single request can consume 50 tokens or 50,000, making per-request budgeting meaningless without visibility
- Traditional APM (New Relic, Datadog APM) knows about function calls but not LLM reasoning steps, tool selections, or guardrail decisions
- OpenTelemetry is the standard transport, but agent-native debugging (step-level traces, tool call inspection, guardrail attribution) requires a higher-level SDK on top

## The Move

Build observability in three layers: **traces** for execution paths, **logs** for step-level events, and **metrics** for aggregate performance — then wire the agent layer into your existing platform telemetry via OpenTelemetry.

**Trace every step, not just the outer request.** Instrument at the tool-call level: log the tool name, arguments passed, result returned, and whether the result was used or discarded by the next step. A candidate evaluation agent that "hallucinated tool parameters" (Harsh Rastogi, Modelia.ai) looks fine if you only log the API response; it becomes debuggable when you log what parameters were actually called.

**Use a split-stack: agent-native SDK + platform telemetry.** The practical 2026 stack is OpenAI Agents SDK (step-level tracing) → LangSmith (debugging, evaluation, run inspection) → OpenTelemetry (vendor-neutral export into your existing Datadog/Grafana/Prometheus). This avoids lock-in while giving you agent-aware debugging.

**Log guardrail and handoff decisions explicitly.** When an agent's flow is diverted by a policy check, a retry, or a multi-agent handoff, that decision should be a first-class log event with the trigger, the options considered, and the outcome. Without this, you know the run derailed but not why.

**Capture cost and latency per step, not per request.** Agents that loop or call expensive tools drive cost surprises. Tag every step with its token count and wall time so you can answer "why did this run cost $4.70?" — not just "the batch ran."

**Retain traces for replay, not just debugging.** Store full step-level traces for failed runs. When an agent makes a wrong decision, you replay the trace: the retrieval output, the tool result that misled it, the guardrail that fired. This is how you close the loop between an incident and a code fix.

## Evidence

- **Engineering blog (Paxrel, 2026):** "Without observability, debugging an AI agent is like debugging a web app with no logs — impossible. You can't see which tools it called, what the LLM returned at each step, why it chose one path over another, or where the reasoning broke down." Identifies three pillars: traces (full execution path), logs (step-level events), metrics (aggregate performance). — [paxrel.com/blog-ai-agent-observability](https://paxrel.com/blog-ai-agent-observability)
- **Engineering post (Bhuvaneshwar A, DEV Community, 2026):** Documents the split-stack pattern: OpenAI Agents SDK for step-level tracing, LangSmith for debugging/evaluation, OpenTelemetry as the vendor-neutral transport. Notes LangSmith supports OpenTelemetry-based tracing for non-LangChain applications, avoiding framework lock-in. — [dev.to/chunxiaoxx/ai-agent-observability-in-2026](https://dev.to/chunxiaoxx/ai-agent-observability-in-2026-openai-agents-sdk-langsmith-and-opentelemetry-3ale)
- **Ask HN thread (Hacker News, 2025):** "With the recent incidents (DataTalks database wipe by Claude Code, Replit agent deleting data during code freeze), it's clear that monitoring AI agents in production is a category that hasn't been solved yet." Comments surfaced Airflow/Prefect/custom queues for orchestration state, vector DB vs KV stores for memory/retrieval, and the need for tracing + metrics + evals that actually predicted incidents. — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

## Gotchas

- **Don't instrument after the fact.** Retrofitting tracing into an existing agent is painful because you need to know which decisions to capture — you have to design the instrumentation before you know where the agent will fail.
- **LLM-as-judge logging is not the same as trace logging.** Running an LLM to evaluate a past run produces an assessment, not the raw execution data. You need both: traces for reconstruction, judge outputs for quality scoring.
- **Context window costs accumulate invisibly.** If you're not logging token counts per step, a looping agent can silently eat your budget. Budget alerts need per-step granularity, not per-request summaries.
- **Guardrail decisions need to be attributed to specific runs.** A run that gets blocked by a content filter should be logged with the triggering content, the policy evaluated, and whether a retry succeeded — otherwise you can't distinguish "correctly blocked" from "incorrectly blocked and never retried."
