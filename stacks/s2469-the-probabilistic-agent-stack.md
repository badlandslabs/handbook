# S-2469 · The Probabilistic Agent Stack — Making Evaluation and Failure Recovery Real

Your AI agent works perfectly in demos. Your benchmarks show 94% accuracy. Then it ships to production, hits a rate limit, goes off the rails for 20 minutes, and nobody notices until a customer reports a hallucinated invoice. Traditional software testing assumed deterministic outputs — the same input always produces the same result. AI agents break that contract on purpose. This stack is about evaluating what actually matters for production agents and building failure recovery that survives the real world, not the happy path.

## Forces

- **Single-run benchmarks lie.** ToolBench, AgentBench, and API-Bank report single-run success rates that mask the consistency, robustness, and fault-tolerance properties production actually demands.
- **95% of AI projects fail** (MIT study, cited by Thoughtworks), and Gartner projects 40% of enterprise AI agent failures will trace to inadequate evaluation and monitoring rather than model capability gaps — meaning the problem is measurement, not model quality.
- **Agents fail in ways traditional software doesn't.** A tool call can return HTTP 200 but contain semantically wrong content. A reasoning chain can produce confident nonsense. An infinite loop can run until the budget runs out. None of these have deterministic failure states.
- **Behavioral quality beats benchmark scores.** InfoQ's analysis of real deployments (2026) concludes: "task success, graceful recovery from tool failures, and consistency under real-world variability matter more than scoring well on curated test sets."
- **Failure modes nobody demos.** Most tutorials show the happy path. Production agents encounter rate limits, 503s, timeouts, egress restrictions, Unicode edge cases, and prompt injection — none of which appear in standard benchmarks.

## The Move

Build a three-layer evaluation and resilience stack that treats the agent as a system to be measured and hardened, not a model to be trusted.

### Layer 1 — Offline Evaluation (Before Deploy)

- **Golden dataset + LLM-as-judge pipeline.** Construct a versioned set of input/expected-output pairs representative of production traffic. Use an LLM judge with a structured rubric to score agent outputs. Calibrate the judge against a small human-labeled slice — track Spearman correlation between judge scores and human labels; fix the rubric when they diverge.
- **Multi-dimensional reliability metrics.** Move beyond pass/fail: measure `pass@k` (consistency over k runs), robustness to semantically equivalent perturbations (ε-level), and fault tolerance under controlled API failures (λ-level). The ReliabilityBench framework (Gupta, arXiv:2601.06112, Jan 2026) defines this as a unified reliability surface `R(k, ε, λ)`.
- **Regression on every PR.** Treat eval runs as unit tests. DeepEval (by Confident AI), LangSmith, and Braintrust support CI integration. Any prompt or model change that drops scores below threshold should block deployment.
- **Agent behavior benchmarks, not model benchmarks.** Evaluate task completion, tool-use correctness, recovery behavior, and state management — not just per-turn accuracy. KDD 2025's tutorial framework organizes evaluation across four objectives: agent behavior, capabilities, reliability, and safety.

### Layer 2 — Failure Recovery Primitives (Survive Production)

- **Exponential-backoff retry.** Handle transient failures (503s, timeouts, rate limits) by retrying with increasing delays. Cap total retry attempts to prevent runaway loops.
- **Circuit breaker.** Track consecutive failures per upstream service. After N failures (threshold typically 5), open the circuit — stop calling the failing service and fail fast during cooldown. Prevents cascading failures from taking down the whole agent.
- **USD budget cap.** Track cumulative spend per agent run or session. Hard cap at a configurable limit prevents runaway token consumption from long reasoning chains or retry loops.
- **Egress allowlist.** Restrict external calls to a pre-approved list of domains/services. Prevents the agent from exfiltrating data or calling unauthorized endpoints even under prompt injection.
- **Partial success handling.** Design for the case where 95 of 100 tasks succeed and 5 fail. Implement retry, fallback, or escalation for the failures rather than failing the entire batch.
- **Human-in-the-loop escalation.** When automated recovery is exhausted — escalate to a human reviewer for high-risk actions (refunds, deletions, external API writes). The HN discussion thread "Ask HN: How are you monitoring AI agents in production?" surfaced this as a near-universal requirement after the Claude Code DataTalks wipe incident.

### Layer 3 — Production Observability (See What Actually Happened)

- **Distributed tracing for agents.** Instrument every LLM call, tool invocation, and decision point as a structured trace. Unlike traditional APM (request-response), agent traces capture the full reasoning chain — variable-length, non-deterministic paths where latency can vary 10x based on the chosen route. OpenTelemetry is the standard integration point; Langfuse, LangSmith, Braintrust, and Maxim AI are purpose-built platforms.
- **Five-pillar observability.** Per Maxim AI's production guide: (1) Traces — full execution path, (2) Evaluations — automated quality scoring on production output, (3) Human Review — domain expert annotation of selected traces, (4) Alerts — user-impacting failure notifications, (5) Data Engine — aggregation and analysis layer.
- **Cost and latency attribution.** Identify which sub-task in a multi-step workflow consumes 80% of tokens or adds 3 seconds of latency. Per-trace cost tracking is essential for agents with variable token consumption.
- **Append-only audit trail.** Log every action, tool call, and LLM response to an immutable store. Enables post-mortems, compliance requirements, and reproducing exactly what happened in a failed run.

## Evidence

- **Engineering blog:** Thoughtworks — "Evaluating AI Agents in Production: A Practical Framework" (June 2026) documents the offline/online eval split, LLM judge patterns, and the finding that 95% of AI projects fail due to measurement gaps, not model quality. — [https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production](https://www.thoughtworks.com/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)

- **Research paper:** ReliabilityBench (Gupta, arXiv:2601.06112, Jan 2026) — defines `pass^k`, ε-robustness, and λ-fault-tolerance as a unified reliability surface `R(k, ε, λ)` for tool-using agents, showing that current benchmarks miss production-critical reliability properties. ReAct outperforms Reflexion under combined stress; Gemini 2.0 Flash achieves GPT-4o-level reliability at lower cost. — [https://arxiv.org/abs/2601.06112](https://arxiv.org/abs/2601.06112)

- **GitHub reference implementation:** MukundaKatta/resilient-agent (DevNetwork Hackathon 2026) — production-grade Python agent with four primitives (retry, circuit breaker, budget cap, egress allowlist) plus JSONL audit trail, with 43 deterministic tests covering the failure modes demos hide. — [https://github.com/MukundaKatta/resilient-agent](https://github.com/MukundaKatta/resilient-agent)

- **GitHub reference implementation:** tanayshah11/ai-agent-error-patterns — production error-handling patterns for AI agents using Trigger.dev v4, covering circuit breaker, partial success, human-in-the-loop, and graceful degradation. Includes ~3ms test runtime. — [https://github.com/tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)

- **HN discussion:** "Ask HN: How are you monitoring AI agents in production?" (2025) — real practitioner reports on AgentShield SDK for execution tracing/risk detection/cost tracking, plus discussion of Claude Code DataTalks incident and the near-universal need for human-in-the-loop for high-risk agent actions. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

- **HN discussion:** "Ask HN: How are you testing AI agents before shipping to production?" (2025) — practitioner-built reliability audit framework documenting 7 core failure modes (hallucination under unexpected inputs, edge case collapse, prompt injection, context length limits, rate limit cascading, loop detection failure, output format drift) with 50+ test cases. — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)

- **GitHub issue:** Shubhamsaboo/awesome-llm-apps#442 (Jan 2026) — filed and resolved: identified that advanced AI agents lack standardized patterns for memory management, action evaluation/scoring, and failure recovery — the community confirmed this as a critical gap. — [https://github.com/Shubhamsaboo/awesome-llm-apps/issues/442](https://github.com/Shubhamsaboo/awesome-llm-apps/issues/442)

- **Industry tutorial:** KDD 2025 Tutorial: "Evaluation & Benchmarking of LLM Agents" — systematic two-dimensional taxonomy (what to evaluate: behavior/capabilities/reliability/safety; how to evaluate: interaction modes/datasets/metrics/tooling/contexts) for applied ML engineers and enterprise AI practitioners. — [https://sap-samples.github.io/llm-agents-eval-tutorial/](https://sap-samples.github.io/llm-agents-eval-tutorial/)

## Gotchas

- **Don't trust single-run success rates.** An agent that passes 90% on a curated benchmark may only succeed 60% of the time on production traffic with real perturbations. Run `pass@10` before deploying anything that matters.
- **LLM-as-judge needs calibration.** An uncalibrated judge can have systematic biases that miss failure modes or flag false positives. Always compare judge scores against a small human-labeled slice and track correlation — don't skip this step.
- **Circuit breakers and budget caps must be in place before production, not after.** Teams that skip these resilience primitives in dev typically discover their need only after a real incident. Build them into the agent scaffold from the start.
- **Observability is not logging.** Standard request/response logging misses the multi-step reasoning chains that define agent behavior. You need structured traces that capture tool calls, LLM decisions, and context retrieval as first-class events — not just the final output.
- **Production distribution shift is the silent killer.** GPT-4 showed measurable behavior changes across model versions (tasks at 97% accuracy in March 2023 dropped to 87% by June 2023 on the same benchmark). Agents require continuous evaluation, not point-in-time certification.
