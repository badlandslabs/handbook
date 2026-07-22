# S-1480 · The Four-Layer Eval Stack — When a Single Metric Lies About Quality

Your eval suite reports 91% accuracy. Your on-call dashboard shows a 34% failure rate on real customer tasks. Your QA team passed the agent before release. Your users found 11 edge cases in week one. The disconnect is structural: you are measuring one thing and shipping another. The teams shipping reliable agents have abandoned the single-metric model entirely — they measure quality at four distinct layers, each answering a different question, each wired into a different part of the deployment lifecycle.

## Forces

- **Single-metric collapse hides critical failure modes.** Compressing agent quality into one number — accuracy, pass rate, task completion — masks failures in schema validity, escalation behavior, trajectory efficiency, and latency. An agent that achieves 90% accuracy and 0% escalation correctness is a compliance and safety disaster wearing a passing grade.
- **End-to-end metrics can't isolate components.** When an agent fails, you need to know whether the failure lives in retrieval, planning, tool execution, or output generation. A single score tells you something broke. It doesn't tell you where.
- **Scorers must match the property you're measuring.** Deterministic checks work for exact-match properties (schema validity, tool name correctness, JSON structure). They fail for semantic properties (is the explanation coherent? is the escalation justified?). Using the wrong scorer type is the most common eval design mistake.
- **Offline evals and production distributions diverge.** A test set curated by engineers in February will not reflect the input distribution in June. Without continuous refresh, your eval suite becomes an increasingly inaccurate proxy for production behavior.

## The Move

Build a four-layer eval harness that separates what you're measuring and wires each layer into the appropriate stage of your deployment pipeline:

**Layer 1 — End-to-End (Did the task succeed?)**
- Task completion rate: binary or rubric-scored pass/fail per task
- Run against a golden dataset: curated inputs with known correct outputs
- Wire into: CI gate — must pass before any agent promotion

**Layer 2 — Trajectory (Was the path efficient and correct?)**
- Tool call accuracy: correct tool selected, correct arguments passed
- Step count vs. optimal path: penalize unnecessary loops or redundant calls
- Error recovery rate: does the agent self-correct after a tool failure?
- Wire into: pre-deploy review — used by engineers to catch planning regressions

**Layer 3 — Component (Which specific span broke?)**
- Retrieve the exact trace span responsible for each failure
- Tag spans by type: retrieval, reasoning, tool execution, output generation
- Route low scores back to the component owner
- Wire into: continuous monitoring — runs on every production trace

**Layer 4 — Production Distribution (What is actually breaking?)**
- Log every production failure as a candidate test case
- Run periodic human review on a sample to calibrate LLM-as-judge scorers
- Refresh the golden dataset quarterly — never let it drift more than two quarters from production
- Wire into: dataset maintenance — keeps evals representative of reality

**Scorer rules:**
- Deterministic scorers (exact-match, regex, JSON schema validation) for properties where correctness is unambiguous
- LLM-as-judge for semantic properties (coherence, relevance, escalation appropriateness) — pair with periodic human calibration to catch scorer drift
- Never use LLM-as-judge to score the same model being evaluated (circular; use a different model class or version)

## Evidence

- **Enterprise research study:** Cleanlab's 2025 survey of 1,837 enterprise teams found that <5% of AI agent projects reached reliable production status, with <1 in 3 teams satisfied with their observability and eval tooling. The top investment priority: improving evaluation infrastructure. — [Cleanlab AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Framework architecture:** AWS Labs' `agent-evaluation` (370 stars, Apache 2.0) implements a multi-layer eval harness with separate hooks for trajectory analysis, component scoring, and end-to-end task completion — designed to isolate which part of a multi-step agent failed. — [awslabs/agent-evaluation · GitHub](https://github.com/awslabs/agent-evaluation)
- **Golden dataset from production failures:** Arthur.ai describes the core loop as: production failure → trace capture → test case definition → golden dataset entry → CI gate. Every regression test in the dataset is traceable to a real failure that occurred in production. — [Arthur.ai — Regression Test Datasets for AI Agents From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **Aggregating to one score is the original sin.** The moment you average four layers into one number, you've lost the ability to route failures to the right owner. Keep the layers separate in dashboards and only produce a summary for non-technical stakeholders.
- **LLM-as-judge scorers drift.** A judge model evaluated against the same behavioral patterns it was trained on will trend toward false positives over time. Run human calibration checks quarterly at minimum.
- **Golden datasets decay.** Input distributions shift. A dataset that reflected production in Q1 will be stale by Q4. Schedule quarterly refreshes and weight new production failure cases higher than old synthetic cases.
- **Step count is not the same as quality.** An agent that calls the wrong tool three times and then corrects itself has a higher step count than a direct path — but a worse outcome. Always pair trajectory metrics with outcome metrics, never replace one with the other.
