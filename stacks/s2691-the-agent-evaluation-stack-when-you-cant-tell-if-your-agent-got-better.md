# S-2691 · The Agent Evaluation Stack · When you can't tell if your agent got better

When your agent ships without a way to measure whether it's improving — and you won't know it broke until a user reports it.

## Forces

- **Static metrics don't track dynamic behavior** — BLEU/ROUGE score text, not tool-call chains, planning loops, or recovery paths. An agent can fail silently (wrong API called, error swallowed) and still produce readable output.
- **Task under-specification** — benchmarks have explicit goals; production tasks have implicit constraints and evolving business rules invisible to outsiders. You can't test what you haven't defined.
- **Judgment subjectivity** — a single accuracy number obscures trade-offs between cost, latency, safety, and reliability. Optimizing accuracy alone can make agents 4.4–10.8× more expensive than cost-aware alternatives with comparable performance.
- **The trial-by-fire discovery** — teams that skip evals discover failures reactively: surprise LLM bills, risky outputs, database wipes. By then, the damage is done.
- **Standard benchmarks miss production gaps** — existing frameworks (HELM, MT-Bench, AgentBench, BIG-bench) evaluate in controlled single-session settings. At production scale, they fail to detect 4 out of 7 failure modes entirely.

## The Move

Separate *what* the agent achieves (outcome) from *how* it gets there (trajectory), and run both continuously.

### Evaluation dimensions

- **Task success rate** with milestone/sub-goal decomposition (KPI scoring) — don't score only the final output; score intermediate steps.
- **Trajectory quality** — did the agent take an efficient path, or waste steps on loops or unnecessary API calls? Tools like `agent_trajectory_evaluation` (GitHub, 2025) score reasoning efficiency, hallucination, and adaptivity via LLM-as-judge without needing ground truth.
- **Cost and latency** — token cost per task, p50/p95 latency. The CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) from arXiv:2511.14136 shows this multi-dimensional approach predicts production success at ρ=0.83 vs. accuracy-only at ρ=0.41.
- **Safety and drift** — detect output drift over time, risky tool invocations, and cascade failures. Standard metrics (ROUGE, BERTScore, accuracy) fail to catch 4/7 production failure modes at billion-event scale.

### Eval harness pattern (from Anthropic engineering)

```
Task (test case) → Agent harness (scaffold) → Transcript (full trace)
                                                      ↓
                                              Grader (multiple assertions)
                                                      ↓
                                              Score + regression signals
```

- **Transcript** captures every tool call, reasoning step, intermediate result.
- **Grader** is a separate LLM judge with a defined rubric — not the agent grading itself.
- Run **two suites**: quality benchmarking (aspirational bar) + regression testing (did we break something?).

### Practical setup

- Use a **separate judge model** (different from the agent model) to reduce self-grading bias in production setups.
- Define **human-calibrated ground truth** for critical dimensions; use LLM-as-judge for softer criteria (tone, helpfulness, instruction following).
- **Human-in-the-loop approval** gates for high-risk actions (database writes, external API calls with destructive potential) — not evaluated after the fact, enforced at runtime.
- **CI/CD integration**: evals run on every model/prompt/tool change. LangChain AgentEvals, DeepEval, and InspectAI all support pytest-style CI integration.
- **Periodic human calibration** — re-grade a sample of outputs manually every sprint; adjust the rubric. LLM judges drift too.

### Production observability layer

- **Execution tracing**: every step in the agent's trajectory is a structured span. Tools like LangSmith, Phoenix (Arize), and AgentShield provide trace-level visibility.
- **Cost tracking per agent/model**: token budgets per task, alerting on anomalies.
- **Behavioral regression detection**: run eval suite against current prod branch; alert on score drops before deploy.

## Evidence

- **AlphaEval (arXiv:2604.12162, April 2026):** Production-grounded benchmark of 94 real tasks from 7 companies. Even the best configuration (Claude Code + Opus 4.6) scores 64.41/100 — revealing that standard benchmarks miss ~35 points of production gap. Also found 63% of companies report low confidence that model updates actually improve products; 25.9% have no explicit evaluation criteria. — [https://arxiv.org/pdf/2604.12162](https://arxiv.org/pdf/2604.12162)

- **CLEAR Framework (arXiv:2511.14136, November 2025):** Multi-dimensional evaluation across Cost, Latency, Efficacy, Assurance, Reliability. Optimizing accuracy alone yields agents 4.4–10.8× more expensive than cost-aware alternatives. CLEAR predictions correlate with production success at ρ=0.83 vs. accuracy-only at ρ=0.41. Survey of 27 AI product companies. — [https://arxiv.org/html/2511.14136v1](https://arxiv.org/html/2511.14136v1)

- **Production Failure Modes Paper (arXiv:2605.01604):** Taxonomy of 7 production failure modes from billion-event scale. Standard metrics (ROUGE, BERTScore, accuracy, AgentBench) fail to detect 4/7 failure modes entirely. Proposes PAEF — 5-dimension continuous evaluation framework. — [https://arxiv.org/pdf/2605.01604](https://arxiv.org/pdf/2605.01604)

- **Anthropic Engineering (January 2026):** Descript evolved from manual grading to LLM graders with product-team-defined criteria and periodic human calibration, running two separate suites for quality benchmarking and regression testing. Bolt.new built an eval system in 3 months using static analysis, browser agents for app testing, and LLM judges for instruction-following behaviors. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **HN Ask: "How are you monitoring AI agents in production?" (2025):** Practitioners citing incidents (DataTalks database wipe by Claude Code, Replit agent deleting data during code freeze) drove demand for step-by-step execution tracing, cost tracking, and risk detection. AgentShield (useagentshield.com) and Lemma (YC F25) emerged as products addressing the gap. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

- **InfoQ (March 2026):** "In production setups, it is a good practice to use a separate judge model to reduce self-grading bias." Recommends sandboxed evaluation environments (code-executing agents evaluated in the same isolation they run in). — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Don't grade the final output alone.** A readable response can mask a broken tool-call chain. Score the trajectory — every tool invocation, every decision point.
- **LLM-as-judge has biases.** Position bias (favoring first/second response in pairwise comparisons) and verbosity bias (longer answers score higher). Calibrate against human-grades periodically.
- **Benchmarks plateau while production fails.**SWE-bench accuracy doesn't predict whether your customer-service agent will loop on refunds. Use production-grounded test cases, not just academic benchmarks.
- **Eval without regression CI is theater.** An eval that runs manually before a release is a checkpoint, not a safety net. Integrate into the deployment pipeline so a score drop blocks the deploy.
- **Don't skip human calibration indefinitely.** LLM judges accumulate rubric drift. The 2025 survey found 70.4% of companies rely on developers doing eval as a side task — this doesn't scale.
