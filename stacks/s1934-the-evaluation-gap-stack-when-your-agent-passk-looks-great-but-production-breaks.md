# S-1934 · The Evaluation Gap Stack — When Your Agent pass@k Looks Great but Production Breaks

When you've shipped an agent that scores well in dev but fails silently in production, and you need a measurement system that actually catches failure before users do.

## Forces

- **The compounding reliability problem** — With 20 sequential steps each at 95% reliability, your agent succeeds only ~36% of the time. Yet pass@3 (any 1 of 3 attempts succeeds) shows ~97%. You're measuring the wrong thing.
- **LLM judges need calibration before trust** — LLM-as-judge is the dominant approach in RAGAS, TruLens, and DeepEval, but deploying an uncalibrated judge produces confident wrong scores. Teams that skip calibration optimize a dashboard, not a product.
- **Deterministic checks don't cover interpretation** — Tool call ordering, argument shapes, and loop invariants are checkable with rules. Whether the agent's reasoning was sound requires a judge. Mixing these is the most common eval mistake.
- **Golden datasets rot** — Production failure traces are the highest-quality signal, but most teams never feed them back into the eval set. The gap between the eval distribution and the real distribution grows until the eval is useless.
- **Eval gets 5% of dev time when it needs 60-80%** — Successful teams in 2025-2026 spend the majority of their engineering effort on measurement. Most teams do the opposite.

## The Move

Build a three-layer eval system: **outcome metrics** (did the task complete), **trajectory metrics** (did it take the right path), and **component metrics** (did each tool and reasoning step work). Run it on a versioned golden dataset sourced from production traces, graded by a calibrated LLM judge, and gated in CI.

### The measurement loop

1. **Capture production traces** — instrument your agent with OpenTelemetry spans. Store complete trajectories (input → reasoning → tool calls → intermediate results → output). Do not discard failures.
2. **Label and cluster failures** — run a human reviewer over a sample of production traces. Cluster by failure type. Store the trace ID in metadata alongside each label. Pick one representative golden per cluster.
3. **Build the golden dataset** — combine manually authored cases (edge cases you anticipated), failure-derived cases (from production clusters), and adversarial cases (prompt injection, null values, Unicode names like O'Brien or 北京). Version it like code.
4. **Calibrate your LLM judge** — run the judge against 100+ human-labeled examples. Require Cohen's κ ≥ 0.6 before trusting any score. Recalibrate every 30 days or after any major prompt/model change.
5. **Gate CI on pass^k** — measure pass^k (all k attempts must succeed) for task-completion metrics. A 70%-reliable-per-trial agent scores ~97% on pass@3 but only ~34% on pass^3. Gate on the conservative number.
6. **Run two grader types** — use **deterministic checks** for tool ordering, argument schemas, loop counts, and output format. Use **LLM judges** only for interpretation: did the reasoning make sense, was the answer grounded, did it complete the user's actual goal.

### The pass^k formula

For an agent that succeeds at probability p per trial:
- pass@1 = p
- pass@3 = 1 − (1−p)³
- pass^3 = p³

At p=0.70: pass@3 ≈ 97%, pass^3 ≈ 34%. Shipping on pass@3 means shipping a system that fails ~2 out of 3 production runs. The gap is 63 percentage points. This is the most common eval mistake in the industry.

### Tool choice

| Framework | Focus | Key Feature |
|-----------|-------|-------------|
| **RAGAS** | RAG + agents | Faithfulness, answer relevance, context precision/recall; reference-free options |
| **TruLens** | Agent grounding | LangChain/LlamaIndex integration; trace-based evaluation |
| **DeepEval** | CI/CD integration | pytest-compatible; traces built automatically from agent runs |
| **Lucidic** (YC W25) | Agent interpretability | Captures tool calls, memories, events — not just input/output pairs |
| **LangSmith** | End-to-end observability | Full trace replay, eval runs, dataset management |

## Evidence

- **HN Ask: Testing AI agents before production:** A practitioner (harperlabs) documented 7 failure modes found through production reliability audits — hallucination under unexpected inputs, edge case collapse with null/Unicode/empty fields, prompt injection, and context window overflow. Gartner predicted over 40% of AI agent projects will fail by 2027. A January 2026 prompt injection in a customer support agent processed a $47,000 fraudulent refund before being caught. — [HN Discussion](https://news.ycombinator.com/item?id=47325105)
- **"Six Principles for Production AI Agents" by app.build:** Found that evaluations are vital but LLM-as-critic has no empirical evidence of working without human calibration. Frustrating agent behavior almost always indicates a system design problem, not a model failure. — [App.build Blog](https://www.app.build/blog/six-principles-production-ai-agents) · [HN Thread 128pts](https://news.ycombinator.com/item?id=44712315)
- **Lucidic AI (YC W25):** Stanford AI Lab team built an e-commerce agent that kept failing at checkout. Every one-line change (prompt tweak, model switch, tool logic adjustment) required a 10-minute rerun to diagnose. Core insight: traditional LLM observability platforms don't capture agent complexity — agents have tools, memories, events, not just input/output pairs. — [HN Launch Thread](https://news.ycombinator.com/item?id=44735843) · [Dashboard](https://dashboard.lucidic.ai)
- **"AI Agent Testing Guide 2026" by RockB:** Found 79% of organizations have adopted AI agents (Multimodal.dev), 57% have agents in production, yet 40%+ of agentic AI projects at risk of cancellation by 2027 due to governance and ROI clarity failures. Three undetectable failure modes: invisible reasoning errors, cascading tool failures, and gradual distribution shift. — [AI Agent Testing Guide 2026](https://baeseokjae.github.io/posts/ai-agent-testing-guide-2026)
- **"From Traces to Test Suites" by Slava Dubrov:** The three eval layers (outcome, trajectory, component) with a concrete loop: trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring. Emphasizes Schema-Guided Reasoning (SGR) to shape judges, and that deterministic checks should cover tool ordering while LLM judges handle interpretation. — [Edge of Context Blog](https://slavadubrov.github.io/blog/2026/06/10/agent-evals-traces-to-test-suites)
- **"AI Agent Evaluation Pipeline 2026" by Digital Applied:** Quantified the pass^k gap: 70%-reliable agent → 97% pass@3 vs 34% pass^3 (63pp gap). Minimum 100+ labeled examples for judge calibration. Acceptable Cohen's κ ≥ 0.6. Successful teams spend 60-80% of dev time on evaluation. — [Digital Applied](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)
- **"Evaluating AI Agents in Production" by Thoughtworks:** 95% of AI projects fail (MIT via Forbes) — not because models are bad, but because organizations can't measure whether the system is working. Traditional testing assumes deterministic behavior; agents are probabilistic and require outcome-focused evaluation. — [Thoughtworks](https://www.thoughtworks.com/en-us/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)
- **DeepEval documentation:** Agent evals run like pytest tests — `assert_test()` for individual cases, `deepeval test run` for CI gates. Supports instrumented tracing for LangChain, LangGraph, OpenAI, LlamaIndex, CrewAI, Google ADK, and more. — [DeepEval](https://deepeval.com/guides/guides-ai-agent-evaluation)

## Gotchas

- **Reporting pass@k instead of pass^k** — If you show 97% but gate on the wrong metric, you ship a system that fails 2/3 of production runs. Know which metric your stakeholders are looking at.
- **Deploying an uncalibrated LLM judge** — Without Cohen's κ ≥ 0.6 on 100+ human labels, your judge produces confident wrong scores. Calibrate before trusting.
- **Keeping goldens static** — Production traces are your best source of new test cases. If you're not feeding failures back into the golden set, the distribution skew grows until your eval is meaningless.
- **Using exact-match assertions** — Standard unit tests don't work for probabilistic outputs. Assert on outcomes, groundedness, and goal completion — not on exact string matches.
- **Spending <10% of dev time on evaluation** — Successful teams spend 60-80%. If you're spending less, your eval coverage is probably insufficient for the compounding failure problem at scale.
- **Ignoring trajectory in favor of outputs** — The final answer can be correct for the wrong reason (from a failed tool that happened to be recoverable). You need to trace the full decision path, not just the endpoint.
