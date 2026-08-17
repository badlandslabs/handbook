# S-2800 · The Trajectory Eval Stack

_Your agent answered correctly — but it called the wrong tool first, ignored a guardrail mid-run, and recovered by accident. Endpoint scoring never caught it. The next deployment regresses the same behavior and you have no alert._

## Forces

- Endpoint scoring — grade the final answer, ignore the path — is the industry default, but agents can reach right answers through reckless trajectories, making it a false signal of reliability
- pass@1 benchmarks systematically overestimate production reliability by 2–4x because they measure single runs; in reality, the same agent succeeding 78% on run 1 may succeed 28% on run 8 (Galileo AI CLEAR framework, 2025)
- Trajectory evaluation is structurally harder than response evaluation: you must capture multi-step traces, score intermediate steps independently, and track tool selection, parameter validity, error recovery, and goal completion as separate signals
- Golden datasets decay as production traffic evolves — the eval set you built three months ago no longer represents what users actually ask, but maintaining it is a continuous cost nobody budgets

## The move

**Score the trajectory, not just the destination.**

- **Capture full execution traces** — every tool call, every parameter, every environment observation, every branching decision. Store these as structured data, not just logs. The trace is the unit of eval.
- **Build a golden dataset from real production inputs**, not synthetic prompts. Route a sample of live traffic (with consent/logging) to a shadow mode and collect the traces. This is the only dataset that actually represents what you're shipping.
- **Use trajectory rubrics** alongside endpoint rubrics. Grade intermediate steps: did the agent pick the right tool? Did it validate parameters before calling? Did it detect and recover from errors? Did it follow constraints? Each dimension gets its own threshold.
- **Calibrate LLM-as-judge against human scores before gating on it.** Run 50–100 samples through both human graders and LLM judges, compute Spearman correlation, and require ≥0.80 before trusting automated scores for pass/fail decisions. Re-calibrate quarterly — model updates shift judge behavior.
- **Integrate into CI/CD as a regression gate**, not a dashboard. Every commit triggers a golden dataset run against the key scenarios. The deployment fails if critical dimensions regress by >5%.
- **Combine frameworks, don't pick one.** Production teams routinely use RAGAS (retrieval metrics), Braintrust (human-feedback-based scoring), LangSmith (execution tracing), and Phoenix/Arize (observability) in combination. No single tool covers trajectory scoring, cost tracking, and human calibration simultaneously.

## Evidence

- **arXiv (CLEAR framework, Mehta et al. 2025):** Found that pass@1 benchmarks overestimate agent reliability by 2–4x in production conditions. Enterprise agents averaged ~60% success on single runs, dropping to ~25% across 8 runs. Published metrics show 50x cost variance between top and bottom performers on the same task set. — [arXiv:2511.14136](https://arxiv.org/abs/2511.14136)
- **HN discussion (roadside_picnic, July 2025):** Practitioner who owned an eval suite for a coding agent reported starting with hundreds of evals, then consolidating to fewer tied to specific features. Categorized evals as warning evals (canary in coal mine), acceptance evals (must-pass for any change), and regression evals (protect existing behavior). Stressed that LLM-as-judge correlation must be measured, not assumed. — [HN #44712315](https://news.ycombinator.com/item?id=44712315)
- **NVIDIA Technical Blog (Li et al., May 2026):** Distinguishes model eval (static datasets, input-to-output mapping) from agent eval (trajectory scoring across dynamic environments). Recommends WebArena, SWE-bench Verified, and GAIA as domain-matched benchmarks, with custom trajectory rubrics for production-specific behaviors. — [developer.nvidia.com](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **Inductivee blog (Sept 2025):** Reports production teams combining RAGAS, Braintrust, and LangSmith simultaneously for different eval dimensions. Stresses golden datasets as the foundation that everything else is downstream of. Notes that unit-test-style exact-match assertions are fundamentally wrong for LLM agents — evaluation must be statistical over a sample, not binary per-run. — [inductivee.com](https://inductivee.com/blog/ai-agent-evaluation-testing-framework)
- **BigDataBoutique blog (Syn-Hershko, 2026):** Describes the three-layer eval architecture: offline regression suite (golden dataset, pre-deploy), online/shadow evaluation (live traffic, non-blocking), and human calibration anchors (periodic spot-checks by domain experts). Compares DeepEval, RAGAS, Promptfoo, LangSmith, Braintrust, Phoenix, Langfuse, Opik on this framework. — [bigdataboutique.com](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **jamesm.blog (June 2026):** Argues endpoint scoring "certifies answers, not behaviour" and describes replay harnesses that capture full trajectories and allow step-level regression testing. Notes that security eval is trajectory eval — prompt injection detection lives in the path, not the output. — [jamesm.blog](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)

## Gotchas

- **LLM-as-judge has documented biases** that must be controlled: position bias (prefers first answer), verbosity bias (favors longer outputs), self-preference (judge model favors outputs from the same family), and chain-of-thought style bias. Measure and correct for these before using scores for gate decisions.
- **Golden datasets rot.** Production traffic shifts, user intent evolves, and the eval set you built in Q1 becomes unrepresentative by Q3. Treat dataset maintenance as a recurring engineering task, not a one-time setup.
- **Trajectory storage is expensive.** Full execution traces include tool responses, intermediate outputs, and branching state. A single eval run for a complex agent can generate 10–100x more data than a simple response eval. Budget storage and compute accordingly.
- **CI eval latency blocks deployments.** Golden dataset runs against a large suite can take 30–60 minutes. Teams either accept the delay or implement tiered gates: fast regression (10–20 scenarios, <5 min) for every commit, full suite (200+ scenarios) nightly.
