# S-1401 · The Agent Eval-in-CI Stack — When Your Agent Passed the Demo and Broke in Production

Your agent works in the notebook. It works in staging. It fails on three real user inputs Monday morning — silently, without an exception, without a log line, without a ticket. The regression test suite passed. It passed because it tested what the old agent did, not whether the new agent does the right thing. You need eval infrastructure that lives alongside your code, runs on every change, and catches trajectory failures before users do.

## Forces

- **Agents fail by trajectory, not by output.** The agent calls the wrong tool, calls tools in the wrong order, or loops 30 times then produces a plausible wrong answer. Traditional assertions on outputs miss this entirely.
- **Most teams have observability but no evaluation.** 52.4% of teams run offline evaluations on test sets; only 37.3% run online evaluations on production traffic. You can see what the agent did — you still can't tell if it was right.
- **Agents are non-deterministic across runs.** The same input can produce correct output via different tool sequences. Diffing outputs catches nothing. You need to evaluate the *reasoning path*, not just the result.
- **Eval quality decays with team velocity.** As the codebase grows, golden datasets grow stale. New edge cases surface in production that never existed in the test set. Without active data collection, evals drift toward the happy path.
- **CI pipelines assume determinism.** A test that sometimes passes and sometimes fails on the same input is a flaky test — except with agents, that variability is structural, not random. You need to design for it.

## The move

### 1. Build purpose-built evaluation datasets, not general ones

Start with fewer, tightly-scoped eval sets tied to specific features and product goals — not a sprawling dataset trying to cover everything. According to eval team leads on the HN "Principles for production AI agents" discussion, the instinct to build broad, general-purpose evals early produces datasets that are expensive to maintain and dilute in signal.

Each eval dataset should:
- Target one failure mode (e.g., null input handling, context window overflow, tool schema mismatch)
- Include both positive and negative examples
- Be versioned alongside the agent code (commit hash in eval metadata)

Sources: HN "Principles for production AI agents" discussion (128 pts, app.build) — https://news.ycombinator.com/item?id=44712315

### 2. Separate safety-critical paths from quality-of-output paths

Not all agent failures are equal. Route different concerns to different evaluation strategies:

- **Deterministic guardrails** (regex, schema validation, policy checks): Catch dangerous tool calls, schema violations, and PII leaks. These belong in unit tests — fast, deterministic, fail-safe.
- **Trajectory evaluation** (LLM-as-judge, embedding similarity, tool-call sequence matching): Catch whether the agent chose the right tools in the right order. This is the hard part and requires human-designed rubrics.
- **Output quality evaluation** (groundedness, relevance, coherence): Use LLM-as-judge evaluators like GroundednessEvaluator and RelevanceEvaluator from arXiv 2512.08769 — these measure whether the response is anchored in source context and coherent to the query.

The safety-critical path belongs in CI as a hard gate. Quality-of-output evaluation runs on every PR but is advisory, not blocking — at least until the eval stabilizes.

Sources: arXiv:2512.08769 (Bandara et al., Dec 2025) — https://arxiv.org/pdf/2512.08769; Mastra.ai AI Agent Evaluation guide (June 2026) — https://mastra.ai/articles/ai-agent-evaluation

### 3. Instrument for trace collection from the start

Every agent execution should produce a structured trace: tool calls, parameters, outputs, token counts, latency, and final output. LangSmith, Phoenix, and Arize all support this. The traces are your raw material for both online and offline evaluation. Without instrumentation, you have nothing to evaluate.

LangSmith's agent benchmarking interface captures traces, lets you define eval datasets against those traces, and runs benchmark evals offline against known examples — then routes production traffic through the same eval pipeline.

The collection must be lightweight enough to run in CI on every commit without blowing up build times. Set a sampling rate for long-running integration evals (e.g., evaluate 10% of CI runs fully, 100% for safety-critical paths).

Sources: LangSmith agent benchmarks — https://info.langchain.com/agent-benchmarks

### 4. Define regression catchers for the 7 core failure modes

The HN "How are you testing AI agents before shipping" discussion (harperlabs) identified 7 failure modes that teams consistently discover in production. Map each to a test:

| Failure Mode | Eval Strategy |
|---|---|
| Hallucination under unexpected inputs | LLM-as-judge groundedness check |
| Edge case collapse (null, Unicode, empty fields) | Deterministic schema + boundary-value tests |
| Context limit surprises | Inject max-context scenarios; assert graceful truncation or rejection |
| Tool hallucination (calling non-existent tools) | Tool-call sequence audit; verify all called tools exist at runtime |
| API timeout cascades | Fault-injection tests; verify retry budget and circuit breaker |
| Rate limit silent degradation | Monitor tool call success rate; assert minimum throughput threshold |
| Prompt injection via user input | Adversarial input eval set; verify agent doesn't deviate from task |

Each of these is a discrete test in CI — not a vague "does it work?" assertion.

Sources: HN "How are you testing AI agents before shipping to production?" — https://news.ycombinator.com/item?id=47325105

### 5. Run online evals on a production sample

Offline evals catch known failure modes. Online evals catch what you didn't anticipate. Route a percentage of production traffic through your eval pipeline — Mastra.ai reports only 37.3% of teams do this, making it a significant differentiation.

Use statistical sampling: evaluate 5% of production traces, alert on sudden drops in groundedness or tool-call accuracy, and automatically add failing production cases to the eval dataset (with label, not auto-labeled).

This closes the loop between production reality and the test suite — your eval set grows from actual failures, not guesses about what might go wrong.

Sources: Mastra.ai AI Agent Evaluation (June 2026) — https://mastra.ai/articles/ai-agent-evaluation

## Evidence

- **HN Ask thread (harperlabs):** "How are you testing AI agents before shipping to production?" — 7 core failure modes identified with specific testing strategies, GCP/AWS/Azure tooling recommendations, and emphasis on reliability audits before deployment — https://news.ycombinator.com/item?id=47325105
- **Mastra.ai article (Schuhmann & Thomas, June 2026):** 52.4% of teams run offline evals; only 37.3% run online evals on production traffic. Details the eval pipeline architecture, LLM-as-judge design, CI integration patterns, and regression detection — https://mastra.ai/articles/ai-agent-evaluation
- **HN "Principles for production AI agents" (128 pts):** Eval team leads share that fewer tightly-scoped evals outperform broad datasets, golden datasets catch regressions, and eval versioning should track agent code versions — https://news.ycombinator.com/item?id=44712315
- **arXiv:2512.08769 (Bandara et al., Dec 2025):** GroundednessEvaluator and RelevanceEvaluator as production-ready building blocks; SDK-built evaluators for query/response, RAG, and custom scenarios — https://arxiv.org/pdf/2512.08769

## Gotchas

- **Flaky evals aren't always a sign of bad tests.** Agent non-determinism is structural. Set statistical thresholds (e.g., pass if 4/5 runs succeed) rather than expecting 5/5.
- **Golden datasets decay.** Without active collection from production failures, your eval set becomes a happy-path trophy case. Schedule quarterly eval dataset reviews.
- **LLM-as-judge has its own failure modes.** Judge models are susceptible to length bias, style bias, and being fooled by confident wrong answers. Validate judge outputs periodically against human labels.
- **CI time scales with eval scope.** Full trajectory evaluation on 500 test cases can take 30+ minutes. Budget accordingly: run full suites on main/PR merge, run targeted smoke evals on every commit.
- **Observability tools ≠ eval tools.** Langfuse, Phoenix, and Arize trace what happened. They do not tell you whether it was right. You need both layers, and teams often stop at the tracing layer.
