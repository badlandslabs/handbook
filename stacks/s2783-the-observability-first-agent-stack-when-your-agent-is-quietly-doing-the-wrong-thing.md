# S-2783 · The Observability-First Agent Stack — When Your Agent Is Quietly Doing the Wrong Thing

Your Grafana dashboard is green. Your Prometheus metrics look healthy. Your agent is returning HTTP 200. But it has been sending slightly wrong answers to customers for three days, burning through $2,400 in API calls, and calling tools in an increasingly confused order. No alert fired. No engineer noticed. This is the observability gap — the missing layer between "the agent is running" and "the agent is doing what you think it's doing."

## Forces

- **Agents fail silently.** Unlike traditional software that throws a visible error, a degraded agent typically returns 200 OK with wrong-but-plausible outputs. The failure is invisible unless you're looking at decision-level traces.
- **Standard infrastructure metrics miss the point.** CPU, memory, and latency are necessary but insufficient. You need to see *which tools the agent called, in what order, with what reasoning, and what it decided to do next*.
- **Drift is gradual, not sudden.** An agent that worked correctly Monday may be subtly degraded by Thursday — degrading on edge cases, drifting toward worse tool-selection strategies, accumulating context errors. Traditional alerting on error rates won't catch this.
- **The 82% failure rate.** Research by bcloud consulting found 82% of companies fail at agentic AI monitoring specifically — not because they don't have monitoring, but because they have the wrong kind. Observability for agents requires different primitives than observability for traditional software.
- **Debugging is path-dependent.** An agent that took 47 steps to reach a wrong answer is a different failure than one that took 3 steps. Knowing the output is wrong tells you nothing about *how* it went wrong.

## The move

Build observability into the agent from day one — not as an afterthought, not as a logging statement you add when something breaks. Treat agent traces the way you treat distributed traces for microservices: as a first-class artifact that captures the full execution path.

**Structured trace capture at decision granularity:**
- Log every model call: input tokens, output tokens, model version, latency, cost
- Log every tool call: tool name, arguments, return value, time-to-execute
- Log every routing decision: which agent or branch was chosen and why
- Log reasoning steps (if the model emits them) separately from tool outputs

**Three-tier observability stack:**

- **Trace layer:** OpenTelemetry (OTel) is the emerging standard for agent instrumentation, replacing ad-hoc logging. Frameworks like KaibanJS (`@kaibanjs/opentelemetry`) and VoltAgent build OTel natively. LLM-specific semantic conventions cover request attributes, usage metrics, and response attributes. This gives you trace-level visibility into the agent's actual decision path.
- **Eval layer:** Platforms like Langfuse (open-source, self-hostable), Maxim AI, and Comet Opik sit above raw traces and provide trajectory-level evaluation: did the agent complete the task, how efficiently, and did it recover gracefully from failures? They support LLM-as-judge scoring, human annotation workflows, and regression testing against known failure cases.
- **Alert layer:** Alert on agent-level signals, not just infrastructure-level ones. Set thresholds for: cost-per-session (catching runaway token usage), step-count-per-task (catching loops or excessive deliberation), silent-failure rate (tool calls that return errors the agent swallowed), and answer drift (LLM-as-judge comparing outputs against a known-good baseline).

**The golden signal for agents:**

- **Correctness rate** — % of tasks where the agent achieved the stated goal, not just returned a response
- **Efficiency ratio** — actual steps vs. expected steps for a given task class
- **Graceful degradation** — did the agent surface uncertainty or errors rather than returning confidently wrong answers?
- **Cost per task** — token spend normalized by task type, enabling cost regression alerts

## Evidence

- **Show HN post:** VoltAgent — an open-source TypeScript agent framework built "observability-first" with native OpenTelemetry, Langfuse, and Prometheus integration. Posted May 4, 2025, reached 32 points on HN. The explicit design choice was to make tracing non-optional by making it the default path. — [github.com/VoltAgent/voltagent](https://github.com/VoltAgent/voltagent) + [news.ycombinator.com/item?id=43888290](https://news.ycombinator.com/item?id=43888290)
- **Community article:** KaibanJS published a detailed walkthrough of instrumenting multi-agent workflows with OpenTelemetry, covering the full trace structure, LLM-specific semantic conventions for request/usage/response attributes, and production deployment patterns. — [huggingface.co/blog/darielnoel/kaibanjs-ai-agent-opentelemetry](https://huggingface.co/blog/darielnoel/kaibanjs-ai-agent-opentelemetry)
- **Enterprise research:** bcloud consulting's survey of enterprise agentic AI deployments found 82% of companies fail at agent monitoring specifically — not at deployment, not at model selection, but at observing what the agent is actually doing once deployed. A senior developer on HN summarized it: "It's not that your GPT-4 model is hallucinating. It's that the system orchestrating 5 autonomous agents is gradually degrading without anyone noticing. Your Prometheus dashboard shows perfect CPU metrics." — [bcloud.consulting/en/blog/agentic-ai-observability-82-empresas-fallan-monitoring-2025](https://bcloud.consulting/en/blog/agentic-ai-observability-82-empresas-fallan-monitoring-2025)
- **LLMOps case study:** Rasgo's year-in-production retrospective (2024) — one of their key lessons was that the "agent-computer interface" (how the agent interacts with tools and data) is more critical to debug than the model itself, and required deep introspection into tool call sequences to debug failures. — [zenml.io/llmops-database/production-lessons-from-building-and-deploying-ai-agents](https://www.zenml.io/llmops-database/production-lessons-from-building-and-deploying-ai-agents)

## Gotchas

- **Verbose tracing is expensive.** Every logged tool call and model response adds latency and storage cost. Scope granularity: log everything to a fast buffer (Redis, in-memory queue), sample aggressively in high-volume paths, retain full traces for flagged sessions.
- **Context engineering ≠ prompt engineering.** The Redis engineering guide on agents (Dec 2025) frames this precisely: you can't observe your way out of a poorly designed information architecture. Fix the signal-to-noise ratio in what the agent sees before you instrument it.
- **LLM-as-judge introduces its own drift.** Using a second model to score the first model's outputs creates a meta-layer that can be systematically biased. Cross-validate with human spot-checks, especially for high-stakes outputs.
- **Retention vs. cost.** Agent traces are verbose. Full retention of every session is expensive. Tiered storage (full traces for flagged/error sessions, sampled traces for healthy sessions) is the practical pattern. OpenTelemetry's sampling APIs support this natively.
- **Instrument before you need it.** Retrofitting observability onto a working agent is painful because you'll need to re-run sessions to capture the traces you should have had. Treat it as part of the agent scaffold, not a post-incident investigation tool.
