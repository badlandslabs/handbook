# S-1404 · The Agent Eval Stack — When Your Agent Passed the Demo but Nobody Knows If It'll Break on Tuesday

Your agent aced the demo. Three use cases worked beautifully, the output looked sharp, and the PM signed off. Three weeks later, a prompt tweak and a model update landed in production on a Tuesday afternoon. Nobody ran anything. The agent started failing — silently, plausibly, returning HTTP 200 with semantically wrong output. Your dashboard showed green. Your users noticed. This is the eval gap: the missing infrastructure between "it works in the demo" and "it still works after the Tuesday deploy."

## Forces

- **LLM output is non-deterministic** — unlike traditional code, you can't assertEquals(output, expected). There are infinite valid answers to most prompts, making automated comparison genuinely hard
- **The lucky-run trap** — a 70%-per-trial agent gets 97% with pass@3 (best of 3) but only 34% in pass^3 (all runs must succeed). Demo success often means you got lucky
- **Eval is not a tool — it's a layered system** — picking between DeepEval, Ragas, LangSmith, or MLflow is downstream of a design question most teams never answer: what does our evaluation architecture look like?
- **74% of production agents still rely primarily on human evaluation** — the industry is early; most teams have no automated feedback loop, which means regressions go undetected until users report them
- **Quality, cost, and latency are equally first-class** — a 99%-accurate agent that costs $4/task and takes 45 seconds is not production-ready regardless of its accuracy
- **Public benchmarks don't answer whether your application works** — MMLU-Pro, GPQA, SWE-bench tell you which base model to pick; they say nothing about whether your specific agentic workflow holds up

## The move

Build a layered eval system — not a single tool, but a pipeline with three gates and three layers:

### Gate 1: The fast regression suite (CI/PR level)
- Run a curated **golden dataset** (50–200 hand-picked examples, versioned alongside code) against every prompt or model change
- Measure **pass rate**, **cost per task**, **latency**, and **step count** — not just accuracy
- Block deploy if CRITICAL-tagged tasks fail or >20% of tasks regress; require review if >10% regress
- Use `pass^3` (all runs must succeed) as the primary metric, not `pass@3` (best-of-N) — the latter is what makes 70% look like 97%

### Gate 2: The full evaluation suite (pre-release)
- Run the complete golden dataset plus sampled production failures
- Apply **LLM-as-judge** with a rubric-decomposed prompt (score each criterion independently, not holistically)
- Calibrate the judge against a human holdout set — measure Cohen's κ between judge and human. Reject judges with κ < 0.6
- Compare candidate against baseline with a **regression detector**: classify severity (CRITICAL/HIGH/MEDIUM/LOW) and surface the specific failures

### Gate 3: Production monitoring (shadow + continuous)
- Route a representative sample of production traffic to eval — run it against the same golden answers without user-facing impact
- Track **drift** in LLM-judge scores over time (a slow degradation in faithfulness or tool-call accuracy often precedes visible failures)
- Use **node-level eval** on individual steps within multi-turn trajectories — pinpoint which operation causes quality issues rather than scoring the whole run

### The eval dimensions (measure all four)
| Dimension | What it captures | How to measure |
|-----------|-------------------|----------------|
| **Capability** | Does it do the right thing? | Golden dataset pass rate, task success rate |
| **Reliability** | Does it do it consistently? | pass^3 (all runs), regression delta |
| **Efficiency** | At what cost and speed? | Cost/task, latency, step count |
| **Safety** | Does it avoid harm or hallucinations? | Faithfulness, structured-output validity, drift monitoring |

## Evidence

- **MAP Study (arxiv/2512.04123v1):** First large-scale study of production agents — 306 practitioners, 20 case studies across 26 domains. 74% depend primarily on human evaluation. 68% of agents execute ≤10 steps before human intervention. Critical eval metrics identified: task success rate, cost per task, latency, step count. — [https://arxiv.org/html/2512.04123v1](https://arxiv.org/html/2512.04123v1)

- **TribeAI/claude-evals (GitHub, Apache-2.0):** Production eval framework for Claude Agent SDK with native SDK lifecycle hooks (PreToolUse, PostToolUse, SubagentStop), 50-case golden dataset, regression detector with severity tiers (CRITICAL: >20% regressed → block deploy; HIGH: >10% → review required), one-command model comparison. — [https://github.com/TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)

- **HN thread "Principles for production AI agents" (128 points):** Community consensus that "evaluations are vital for improving performance" (roadside_picnic). LLM-as-judge debate: false positives are a real risk, systematic eval is the answer. — [https://news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

- **reaatech/agent-eval-harness (GitHub, MIT):** TypeScript evaluation harness with 12 composable packages. Features: trajectory evaluation, tool-call validation, cost tracking, latency budgets, golden trajectory comparison, CI regression gate, and MCP tool server. Maps to full agent runs, not just classifiers. — [https://github.com/reaatech/agent-eval-harness](https://github.com/reaatech/agent-eval-harness)

- **Digitalapplied.com "AI Agent Evaluation Pipeline 2026":** pass@3 ≈ 97% vs pass^3 ≈ 34% for a 70%-per-trial agent — the core statistical insight that demo success is often a lucky run. Makes the case for evaluating all runs, not best-of-N. — [https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)

- **BigDataBoutique "LLM Evaluation in Production":** Layered eval architecture (offline regression + online/shadow + human calibration + production monitoring). Golden datasets as the differentiator. LLM judges need calibration via rubric decomposition, pairwise comparisons, and audited human holdouts. — [https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)

## Gotchas

- **Using pass@3 instead of pass^3** — you're measuring the best possible outcome, not the average case. A 70%-per-trial agent looks 97% accurate. This is what makes agents look production-ready in demos and then fail on Tuesday.

- **LLM judges without calibration** — an uncalibrated judge has unknown bias. Measure Cohen's κ against a human-labeled holdout set before trusting any judge score. MLflow's `memalign` (MEMAlign) reportedly improves judge-human agreement by 30–50%, but only with explicit calibration feedback.

- **Golden datasets that aren't golden** — a golden dataset that only covers happy paths is a false sense of security. Include edge cases, failure modes, and regressions from past incidents. Version it alongside code.

- **Eval latency as a blocker** — a 2-hour eval suite doesn't run in CI. Separate into tiers: fast regression (sub-5-min, PR gate) vs full suite (pre-release). Route production traffic to shadow eval continuously to catch drift.

- **Measuring quality but not cost** — a 99% accurate agent that costs $4/task and takes 45 seconds isn't production-ready for a high-volume use case. Put cost and latency in the same scorecard as quality.
