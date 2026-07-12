# S-997 · The Agent Observability Stack — When the Agent Looks OK but Decides Wrong

Your agent has been running for 6 weeks. Tickets process, summaries ship, delegations happen. On Tuesday morning a domain expert notices the routing decisions are subtly wrong. You dig in. No error logs. No exceptions. No alerts. The agent is producing systematically incorrect outputs with enough surface plausibility to pass casual inspection. The root cause: a schema change in an upstream data feed 48 hours ago that the agent's memory layer never caught. This is not a crash. This is the observability gap.

## Forces

- **Agents produce plausible failures, not errors.** Unlike traditional software, agents don't throw exceptions when they go wrong — they produce wrong answers that sound right. Standard APM (error rates, latency histograms) misses the actual failure mode entirely.
- **A single bad step compounds.** In a 12-step agent pipeline, step 3 produces degraded context. Steps 4–12 operate on that context and magnify the error. There's no rollback. By the time the final output is obviously wrong, the trace is deep and the root cause is buried.
- **"Working" is not the same as "correct."** Agents can run for weeks producing plausible, consistent outputs that are systematically wrong. Human review catches this slowly. Automated review catches it never if you haven't instrumented for it.
- **Standard telemetry is a different problem than in microservices.** Microservice observability answers "did my code run correctly." Agent observability must answer "why did the model choose this action, what context did it have, and was the output actually grounded." These require fundamentally different instrumentation.
- **The cost of catching this late is asymmetric.** The De Felice case study: 48 hours of systematic routing errors propagating through a production workflow before a domain expert noticed. The $437 incident: an 8-hour retry loop that cost $437 in API calls and zero alerts fired.

## The Move

Build a layered observability stack that answers "what happened, why, and was it right" across the full agent lifecycle.

### Layer 1 — Instrumentation: OpenTelemetry + GenAI Semantic Conventions

Adopt the OpenTelemetry GenAI semantic conventions (GenAI semconv 1.29+, now stable/near-stable as of 2025) as your instrumentation backbone. These define standard span types for the full agent vocabulary:

- **llm** spans: model, prompt, response, token counts, latency per call
- **agent** spans: reasoning steps, decisions, state transitions
- **tool** spans: which tool was called, with what arguments, what it returned
- **retrieval** spans: RAG lookups, chunk relevance scores, grounding checks
- **memory** spans: context reads/writes, session state operations

Export via OTLP HTTP JSON to any compliant backend. This decouples your instrumentation from your storage — LangSmith, Phoenix/Arize, Datadog, Grafana+Tempo, AgentLens, or your own Tempo instance all work interchangeably. The semantic conventions are now adopted by Google Cloud, AWS, Azure, and Datadog alongside purpose-built platforms.

For Python, MLflow provides native GenAI semconv export. LangGraph's built-in tracing auto-instruments all nodes. For custom agents, wrap your core loop: `start_span("agent")` → `start_span("llm")` for each model call → `start_span("tool")` for each tool → `end_span()` with outcome and metadata at each boundary.

### Layer 2 — Topology + Time-Travel Replay

Plain LLM tracing (LangSmith, Helicone) logs individual calls but doesn't show you the agent's decision topology. For multi-step agents you need:

- **Topology graph**: the full DAG of LLM calls, tool calls, and sub-agent spawns as an interactive visualization. AgentLens (open source, self-hosted) provides this specifically for agents, as does Phoenix. LangSmith's trace view captures this for LangChain/LangGraph workflows.
- **Time-travel replay**: scrub through a run frame-by-frame, seeing the exact state (context, tool results, model output) at each step. When an agent produces a bad answer at step 10, you need to see steps 1–9 with their full outputs to understand why. AgentLens, LangSmith, and Phoenix all provide this.
- **Trace comparison**: side-by-side diff of two runs, color-coded to show where trajectories diverge. Use this to understand why the same prompt produces different outputs across model versions or environments.

Bayer's PRINCE system (Bayer AG + Thoughtworks, Martin Fowler case study) persists agent state after each LangGraph node execution in PostgreSQL via LangGraph checkpointers, with application-level state in DynamoDB. This enables not just logging but full state reconstruction for any point in a run.

### Layer 3 — Deterministic Output Verification

Tracing tells you what the agent did. Verification tells you if it was right. This is the layer most teams skip and pay for later:

- **Faithfulness judges**: run a lightweight LLM judge after each agent output to score whether the answer is grounded in the retrieved context. FutureAGI's agentic RAG analysis documents this as the defining feature of 2026-era agentic RAG vs. classic RAG — the self-check loop that gates answers before they reach users. A research agent that retrieves 8 chunks and invents the 7th fact in the answer needs a faithfulness gate, not just a retrieval span.
- **Content grounding checks**: for agents that ground responses in retrieved documents, verify that every factual claim in the output has a corresponding citation in the retrieved chunks. This catches the hallucination-at-step-7 failure mode that no span alone will surface.
- **Structural assertions**: after each step, verify the agent's state matches expected schema — field X is populated, field Y has a valid value, the routing decision target exists. This would have caught the De Felice schema-change failure within minutes rather than 48 hours.

### Layer 4 — Runtime Anomaly Detection

Set up alerts on agent-specific patterns, not just infrastructure metrics:

- **Cost anomaly detection**: alert when cost-per-run exceeds a threshold, or when cost-per-session grows without a corresponding task completion. This catches the retry loop failure mode — the $437 incident ran for 8 hours with no cost alert firing on most setups.
- **Token accumulation monitoring**: track cumulative context length across a session. Alert when it grows faster than expected or approaches model context limits without a task completion signal. Silent context limit approaches are a common failure mode documented across multiple sources.
- **Repeated identical tool calls**: a tool called 3+ times with identical arguments in the same session is the signature of a retry loop. Alert on this pattern. Combine with step budget limits — set a hard maximum of N identical failed tool calls before the loop terminates and escalates.
- **Output quality signals**: length degradation (a model that typically produces 200-word summaries suddenly outputting 20 words), confidence signal shifts, or the absence of expected tool calls in a sequence. These are early warning indicators before a run produces a catastrophically wrong output.

### Layer 5 — Circuit Breakers as Architectural Primitives

Kill switches are not enough — you need circuit breakers that act at the right granularity. From multiple real-world incidents, the pattern that emerges:

- **Per-tool call budget**: maximum retry count per tool (default: 2). On the 3rd identical failure, stop retrying and escalate.
- **Per-loop step budget**: maximum total steps per agent loop (default: 20–50 depending on task complexity). On budget exhaustion, halt and surface the partial result to a human.
- **Per-session absolute timeout**: maximum wall-clock time per session regardless of step count. Prevents the "runs all night" failure mode.
- **Permission-level kill switches**: infrastructure-layer shutdown that the agent cannot override. If an agent can modify its own kill switch instructions (documented as CVE-2026-21520), the protection is illusory.
- **Monetary circuit breakers**: hard cost cap per run or per day. Several platforms (VoltAgent, LangGraph Cloud) now offer this as a first-class feature. Price it into your architecture from day one, not after an incident.

## Evidence

- **Case study (real-time incident):** A routing agent ran for 6 weeks producing systematically wrong decisions based on stale context from an upstream schema change — caught 48 hours later by a domain expert, not automated monitoring. No error logs, exceptions, or alerts were generated. The agent was functioning incorrectly with enough surface plausibility to pass casual inspection. — [gustavodefelice.com](https://www.gustavodefelice.com/p/debugging-ai-agent-infrastructure)

- **Case study (API cost incident):** An agent entered a retry loop at 11 PM; by 7 AM it had burned $437 in API calls. No alert fired. The fix took 20 minutes. The loop ran for 8 hours. — [DEV Community / waxell](https://dev.to/waxell/ai-agent-circuit-breakers-the-reliability-pattern-production-teams-are-missing-5bpg) citing an April 2026 public post-mortem

- **HN community data:** A 2025 Ask HN thread on agent testing collected 7 documented failure modes (hallucination under unexpected inputs, edge case collapse, prompt injection, context limit surprises, silent quality degradation, tool-level wrong results, cascading partial failures) with community corroboration across multiple practitioners. Gartner data cited: 40% of AI agent projects expected to fail by 2027; Gartner predicts 82% of organizations plan agent adoption in 3 years. — [HN Ask: How are you testing AI agents before shipping to production?](https://news.ycombinator.com/item?id=47325105)

- **OpenTelemetry standard (primary source):** GenAI semantic conventions define standard span types for llm, agent, tool, and retrieval operations. Adopted by Google Cloud, AWS, Azure, Datadog. Python MLflow provides native GenAI semconv export. — [OpenTelemetry Blog: AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)

- **Production reference architecture (primary source):** Bayer AG's PRINCE system (Thoughtworks + Bayer) persists agent execution state after each LangGraph node in PostgreSQL via LangGraph checkpointers, with application state in DynamoDB. Multi-model via unified OpenAI-compatible endpoint with automatic fallback between providers. — [Martin Fowler: Building Reliable Agentic AI Systems](https://martinfowler.com/articles/reliable-llm-bayer.html)

- **Open-source observability platform:** AgentLens (self-hosted) provides topology graph, time-travel replay, trace comparison, cost tracking across 27 models, live SSE streaming, anomaly alerting, and OTel ingestion. Supports LangChain, CrewAI, AutoGen, LlamaIndex, Google ADK. — [HN Show: AgentLens](https://news.ycombinator.com/item?id=47205382)

- **Industry benchmark (survey):** 82% of organizations fail at monitoring AI agents in production. 40% of AI agent projects expected to cancel before 2027 due to unclear business value and inadequate risk controls. — [BCloud Consulting](https://bcloud.consulting/en/blog/agentic-ai-observability-82-empresas-fallan-monitoring-2025/) citing Gartner 2025 data

## Gotchas

- **LangSmith/Helicone are LLM observability, not agent observability.** They track individual LLM calls well but miss agent topology. If you use LangChain, LangSmith's trace view covers both. For other frameworks, you need AgentLens or Phoenix to see the DAG, not just the calls.
- **A trace without verification is a post-mortem tool.** Most teams instrument traces and never look at them until something goes wrong. Build verification loops into the trace itself — faithfulness judges, grounding checks, structural assertions — so failures are caught during execution, not after.
- **The De Felice failure mode is the most dangerous one and the hardest to catch.** Stale context producing plausible-but-wrong outputs is not detectable by error rates or latency. It requires state assertions that verify the agent's working context against ground truth after each significant step.
- **GenAI semantic conventions are not yet universal.** Check your tooling's support before committing. MLflow, LangGraph, and Phoenix have strong support. Custom agents need explicit span instrumentation — don't assume your traces are structured until you've validated the export.
- **Cost monitoring is often the first alert that fires in agent incidents, but it's the last thing teams add.** Set monetary circuit breakers before production, not after.
