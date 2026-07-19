# S-1360 · The Trace Reconstruction Stack — When Your Agent Fails but Everything Looks 200 OK

When you reach for it: Your agent returned HTTP 200, every LLM call succeeded, every tool ran without throwing — and the output was wrong. You have no idea why. Logs show individual events but not the causal chain that led to failure. You need to reconstruct the execution trajectory, not just inspect individual steps.

## Forces

- **Success signals are shallow for agents.** A standard APM marks a run as healthy if HTTP responses are 200 and no exceptions are raised. An agent can return 200 while selecting the wrong tool, violating a tenant boundary, or hallucinating evidence — because the deterministic layer did exactly what the probabilistic output told it to do.
- **Failures are causal and distributed.** An error in step 2 of a 12-step run silently corrupts steps 3–12. By the time the agent surfaces a result, the original cause is buried under 10 layers of compounding downstream effects. Standard logging never captures this dependency graph.
- **Reproducing failures is expensive.** Agents are non-deterministic — the same prompt can trigger 2 steps or 20 depending on model reasoning. A production failure that happens 1% of the time can't be reproduced by re-running the same input; you need the actual execution trace to understand what state caused the deviation.
- **Evaluation divorced from tracing misses the point.** LangChain's own docs state the feedback loop: add failing production traces to your dataset, create targeted evaluators, validate fixes with offline experiments, redeploy. Without the trace, you can't enter the loop.

## The move

**Instrument full execution traces, not just step outcomes. Then close the loop from production failure to eval dataset to regression test.**

1. **Capture structured traces with causal links.** Use OpenTelemetry spans or a platform like LangSmith, LangFuse, or Arize Phoenix. Each span records: step number, LLM input/output, tool called, tool args, tool result, token count, latency, cost. Spans must link parent→child so the trajectory is reconstructable as a directed graph, not a flat event log.

2. **Attach quality signals at the trace level.** Log user feedback (thumbs up/down, corrections) and LLM-as-judge evaluation scores directly to the trace, not to individual calls. A single aggregate quality score per trace makes it possible to filter "healthy" vs. "degraded" production cohorts for dataset mining.

3. **Build eval from failing production traces.** The standard workflow: production trace fails → add to eval dataset with expected output → write targeted evaluator (regex for format, LLM judge for quality, ground-truth comparison for function calls) → offline experiment validates fix → redeploy. Never try to reproduce a failure from memory; reproduce it from the trace.

4. **Use four eval modalities in a tiered pipeline.** Run fast unit-style checks (format, schema, regex) on every commit via CI. Use LLM-as-judge for quality assessment on a sample of production runs. Reserve human-in-the-loop eval for subjective or high-stakes outputs. Use synthetic eval (one model judges another) for regression sweeps on large historical datasets. Run them at different cadences — cheap checks are continuous, expensive ones are periodic.

5. **Hard-cap execution to bound investigation scope.** Set `MAX_STEPS = 12` (LangGraph: `recursion_limit=12`). When the agent hits the cap, raise `AgentExceededSteps`, record the partial trace, and escalate. This prevents runaway loops (documented: 50,000 requests/hour from a retry loop spiraling in production) and ensures every failure has a bounded trace footprint.

6. **Instrument cost and token counts per trace.** Token accounting is part of observability, not an afterthought. A single agentic run can consume $0.47–$5+ depending on model, steps, and context length. Without per-trace cost visibility, you can't detect cost anomalies, optimize prompt density, or set budgets that actually work.

## Evidence

- **HN post (Show HN):** "AI agents are bad at API integrations — we fixed it" — APIMatic, showing how better tool schema definition and context plugins reduced agent failure rates on API calls. Tool selection errors were traced to ambiguous tool descriptions, not model quality — [https://news.ycombinator.com/item?id=47704728](https://news.ycombinator.com/item?id=47704728)
- **Blog post:** Zylos Research — "Trace-Driven Debugging for AI Agent Failures: From Production Incident to Regression Test" — Documents the 88% figure (infrastructure gaps cause most agent failures, not model quality), the trace→dataset→eval pipeline, and agent-native observability vs. traditional APM for multi-step workflows. — [https://zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures/](https://zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures/)
- **Reddit r/AI_Agents:** Thread "Our AI agent got stuck in a loop and brought down production" — Real incident where a retry loop generated ~50,000 requests/hour, taking down a production database. Community consensus: "When you design an agent only to succeed, you neglect to give it a safe way to fail." — [https://www.reddit.com/r/AI_Agents/comments/1r9cj81/](https://www.reddit.com/r/AI_Agents/comments/1r9cj81/)
- **Blog post:** Manvendra Rajpoot — "LLM Agent Error Recovery in 2026: Patterns That Don't Loop Forever" — Provides the hard step cap pattern (`MAX_STEPS=12`), tool-level retry semantics (errors must guide, not confuse), fallback paths, cost circuit breakers, and state checkpointing. — [https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **Docs:** LangChain / LangSmith — Evaluation guide covering online evaluators on production traces, feedback loop from failing traces to datasets, and the CI→staging→production eval pipeline. — [https://docs.langchain.com/langsmith/evaluation](https://docs.langchain.com/langsmith/evaluation)
- **arXiv (Dec 2025):** "Evaluation and Benchmarking of Generative and Agentic AI Systems: A Comprehensive Survey" — Comprehensive survey of agent eval approaches including trajectory-level evaluation, tool-call accuracy benchmarks, and the distinction between single-step and multi-step agent benchmarks. — [https://arxiv.org/abs/2510.24358](https://arxiv.org/abs/2510.24358)
- **KDD 2025 Tutorial:** "Evaluation & Benchmarking of LLM Agents" — SAP Labs tutorial covering evaluation platforms (LangSmith, Langfuse, Arize Phoenix, Braintrust, Maxim AI), four evaluation approaches (unit-style, human-in-the-loop, synthetic, hybrid), and continuous evaluation for LLM drift detection. — [https://sap-samples.github.io/llm-agents-eval-tutorial](https://sap-samples.github.io/llm-agents-eval-tutorial)

## Gotchas

- **Logging individual tool calls is not tracing.** Spans must have causal parent-child relationships to be useful. Flat logs of independent events require manual correlation and miss the execution trajectory. Use a platform that builds the graph automatically (LangSmith, LangFuse, Phoenix all do this).
- **LLM-as-judge has known biases.** Research (arxiv 2509.25154) shows LLM judges can be systematically biased toward outputs similar to their training distribution. Validate judge scores against human eval on a sample before trusting them for high-stakes decisions. Pair with ground-truth comparison for functional correctness (e.g., did the agent call the right API with the right args?).
- **Eval datasets go stale.** LLMs drift over time. An eval dataset built 3 months ago may no longer reflect current model behavior. Re-run golden datasets periodically and add new failure cases from production continuously. The pipeline only works if the dataset is living.
- **Hard step caps catch loops but don't explain them.** A step cap stops the spiral but leaves you with a partial trace. Always record the partial trace before stopping — the truncated trajectory is the evidence you need to fix the root cause.
