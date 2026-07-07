# S-759 · The Eval Gap: Traces Outnumber Verdicts 3-to-1 in Agentic Systems

Most agentic teams instrument their agents to death. LangSmith logs every span. Phoenix traces every node. Arize processes a trillion spans per month. But 37 percentage points below that observability layer sits the verification gap: teams can replay what an agent did, but they still cannot confirm whether it was right.

## Forces

- **Observability is passive.** Tracing captures execution paths, latency, and token counts — not correctness. You can watch an agent call the wrong tool with the right schema and never know it failed.
- **Eval tooling arrived late and stayed fragmented.** RAGAS, DeepEval, LangSmith evals, Promptfoo, Arize Phoenix, and Weights & Biases Weave all do overlapping things with different mental models. Teams adopt tracing because it's one dashboard. They skip evals because it requires four more.
- **Agent outputs resist ground truth.** Unlike classification or extraction, agentic outputs are multi-step, context-dependent, and often non-deterministic. Traditional CI assertions don't apply. You need a judge — and running a judge LLM on every response is expensive at scale.
- **Multi-agent failures compound invisibly.** In orchestrator-worker workflows, the error originates in one agent but surfaces in another. Observability shows you the handoff; evals show you whether the handoff corrupted the result.
- **Regulated industries amplify the gap.** 70% of regulated enterprises rebuild their agent stack every 3 months or faster. Rapid iteration without regression tests means quality silently degrades between deployments.

## The move

Build a two-layer eval strategy: **blocking evals in CI** that gate every deploy, and **sampling evals on production traffic** that detect drift over time. Treat them as separate concerns with separate SLAs.

**Blocking layer (CI/CD gate):**
- Use DeepEval or pytest-style assertions for deterministic checks: tool-call schema conformance, output format validity, exact-match ground-truth cases.
- Run a judge-LLM on a fixed eval set (50-200 cases) against the four canonical failure modes: hallucination, tool-call accuracy, instruction adherence, and output completeness.
- Block the deploy if the judge score drops below a threshold. Treat it like a lint gate, not a research exercise.

**Sampling layer (production monitor):**
- Route 1-5% of live agent sessions to an async eval job. At this sampling rate, judge-LLM cost is roughly $15/month per 10,000 sessions.
- Track faithfulness, context precision, and answer relevance with RAGAS metrics — each has a published academic methodology that survives auditor scrutiny.
- Alert on drift: if week-over-week faithfulness drops 5 points, surface it before it becomes a user complaint.

**Trace linkage:**
- Store eval results linked to the originating trace ID. When an eval fails, you can replay the full execution, not just the output.
- The 52% of teams that do have evals — but don't link them to traces — cannot do this replay. They know something failed; they don't know why.

**Evaluator model selection:**
- Use a stronger model as judge than the model under test. Using GPT-4o as judge for GPT-4o outputs produces inflated scores due to confirmation bias.
- Open-source judges (e.g., Prometheus, F琶) work for low-stakes domains. For regulated industries, a proprietary judge with chain-of-thought reasoning is defensible.

## Evidence

- **Survey:** 89% of organizations with agents in production have observability infrastructure; only 52% have structured evals — a 37-point gap. — *Cleanlab, "AI Agents in Production 2025," August 2025 (1,837 respondents, 95 with live production agents)* — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Survey:** 63% of agentic teams plan to invest in observability or evaluation improvements over the next year, making it the top stated priority. — *Cleanlab, same survey, 2025* — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Benchmark:** Most mature AI teams run two frameworks in parallel — DeepEval in pytest to block deploys on quality regressions, and RAGAS as a scheduled job sampling 1-5% of live traces for faithfulness drift. At 10,000 evaluations per day, monthly judge-LLM cost is roughly $15. — *AIML.QA, "LLM Evaluation Framework Benchmark 2026," April 2026* — [https://aiml.qa/llm-evaluation-framework-benchmark-2026](https://aiml.qa/llm-evaluation-framework-benchmark-2026)
- **Framework:** LangSmith processes traces from 400+ companies and 1 trillion+ spans monthly, but traces alone cannot determine correctness — they require paired eval logic to produce verdicts. — *OptinAmpOut, "Agent Observability Transforms Agentic AI Production," October 2025* — [https://www.optinampout.com/blogs/agent-observability-transforms-production-ai.html](https://www.optinampout.com/blogs/agent-observability-transforms-production-ai.html)
- **HN thread:** Ask HN discussants building multi-agent systems consistently raised "how do I know if it's doing the right thing?" as the core unresolved question — more common than orchestration or cost concerns. — *Hacker News, "Ask HN: How to manage multiple AI agents in production?" ~March 2025* — [https://news.ycombinator.com/item?id=45721705](https://news.ycombinator.com/item?id=45721705)
- **RAG-specific:** RAGAS provides 8 purpose-built RAG metrics (faithfulness, context precision, noise sensitivity, etc.) each with published academic methodology — making them the defensible choice for regulated industries where auditors require reproducible measurement. — *AIML.QA benchmark, 2026*

## Gotchas

- **Tracing without evals is theater.** You can watch an agent burn $200 in tokens on a hallucinated tool loop and only know something went wrong if you have a cost alert — not a correctness alert. The span dashboard is not a quality signal.
- **Eval datasets rot.** Agent behavior changes with model upgrades, prompt changes, and schema changes. A fixed eval set from six months ago no longer reflects what you're shipping. Re-generate eval sets quarterly or after any major stack change.
- **Judge bias is a real problem.** Using the same model family as judge and agent produces inflated scores. Use a categorically different model (e.g., Claude as judge for a GPT-based agent) to reduce confirmation bias.
- **The 1-5% sampling floor is not enough for low-frequency, high-stakes actions.** If an agent sends an email once per day, sampling 5% means you might evaluate that action once per month. For high-stakes actions, instrument explicit eval triggers rather than relying on statistical sampling.
- **Multi-agent handoff eval is its own problem.** Evaluating whether Agent B correctly interpreted Agent A's output requires replayable state and a reference schema for the handoff contract. Most eval frameworks treat agents as black boxes and miss inter-agent corruption entirely.
