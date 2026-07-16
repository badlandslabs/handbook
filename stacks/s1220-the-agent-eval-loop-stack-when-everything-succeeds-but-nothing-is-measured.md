# S-1220 · The Agent Eval Loop Stack — When Everything Succeeds But Nothing Is Measured

Your agent passes its demo. It passes your unit tests. You ship it. Three weeks later, a class of inputs quietly degrades while your dashboard shows green. Nobody noticed because nobody was measuring the right thing. This is the eval gap — the distance between "the agent worked in testing" and "the agent works in production."

## Forces

- **Determinism is a lie agents tell you.** Traditional tests assert `input → function → output`. Agents perceive context, select tools, and interpret intermediate results. The same input can produce different outputs — and so can your tests.
- **Scaffolding dominates raw capability.** GAIA bare-model scores differ by 30+ percentage points from scaffolded versions. An agent's tooling, orchestration, and prompt harness matter as much as the base model — but most benchmarks measure only the model.
- **You evaluate hallucinations with evaluations that can hallucinate.** LLM-as-judge is non-deterministic. You're testing for unreliable outputs with an unreliable scorer.
- **pass@1 hides the consistency problem.** A 70%-per-trial agent looks acceptable on pass@1. On pass^3 (all attempts succeed), it scores ~34%. That gap is invisible unless you're measuring it.
- **Outcome correctness is insufficient.** Braintrust's 2026 research found that trajectory scoring catches regressions outcome scoring misses — an agent can reach the right answer through the wrong path, which will fail under slightly different inputs.

## The Move

Measure the loop, not the output.

**Build a golden set from real failures.** Curate 50-100 representative production tasks with known expected outcomes — drawn from actual agent failures, not synthetic test cases. This is the single highest-leverage practice. Run it before every deployment, after every model update, and whenever you modify the agent's tools or prompt.

**Score trajectories, not just outcomes.** Track the full decision path — tool calls, intermediate outputs, reasoning steps — not just whether the final answer is correct. A correct answer via a broken path will break on the next similar input.

**Measure both pass@1 and pass^k.** Run each eval task k times. Report the consistency number alongside peak performance. A gap between them is a reliability signal. If pass@1 is 70% and pass^3 is 34%, the agent is not production-ready regardless of what pass@1 says.

**Gate CI/CD on eval scores.** Require a minimum Cohen's κ ≥ 0.6 between your LLM judge and human reviewers before the score is trustworthy enough to gate on. Below 100 labeled calibration examples, you have no statistical confidence.

**For failure handling: prefer grounded correction over self-reflection.** Intrinsic self-correction (model judging itself) is fragile. Grounded self-correction — anchored in execution results, structured critics, or Process Reward Models — produces reliable gains. Zylos Research found that LLMs cannot reliably correct reasoning errors without external signals.

**Keep recovery lightweight.** Seven patterns dominate production failure handling: retry with exponential backoff, circuit breakers, model fallback (primary → fallback model on timeout), graceful degradation (partial results over total failure), dead letter queues for failed task deferred retry, human-in-the-loop escalation for uncertain outputs, and idempotent operations so retries are safe.

## Evidence

- **InfoQ:** AI agents must be evaluated as systems — task success, graceful tool failure recovery, and consistency under real-world variability matter more than benchmark scores on curated test sets. Classical NLP metrics (BLEU, ROUGE) and single-turn accuracy don't capture agent failure modes. Hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis) with human judgment is non-negotiable. Operational constraints — latency, cost, token throughput — are first-class evaluation targets. — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Monte Carlo Data:** Four categories of changes that break agentic systems in production: (1) Data — real-world input drift, unavailable context; (2) System — changes to provided tools or orchestration logic; (3) Code — prompt updates, agent framework version bumps; (4) Model — base model swaps or version updates. Each requires a different eval response. They recommend golden test sets per category and continuous evaluation integrated into the deployment pipeline. — [https://montecarlo.ai/blog-ai-agent-evaluation](https://montecarlo.ai/blog-ai-agent-evaluation)
- **GAIA Benchmark (Meta/HuggingFace/AutoGPT):** In 2023, GPT-4 with plugins scored 15% on GAIA; humans scored 92%. By late 2025, top scaffolded systems reached 74% — closing the gap from 77 points to 17. Critically, bare model vs. scaffolded model scores differ by ~30 percentage points on the same benchmark, meaning the scaffolding harness is as important as the model itself. SWE-bench alone is insufficient for real-world capability assessment. — [https://agentmarketcap.ai/blog/2026/04/10/gaia-benchmark-2026-general-ai-agent-performance-test](https://agentmarketcap.ai/blog/2026/04/10/gaia-benchmark-2026-general-ai-agent-performance-test)
- **Digital Applied:** 17.14% of multi-step agent failures are step repetitions (loops without progress); 13.98% are reasoning-action mismatches (stated reasoning diverges from actual tool call). Both are invisible to outcome scoring but caught by trajectory evaluation. Successful teams spend 60-80% of engineering time on evaluation — it is the core engineering activity, not a QA step. — [https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)
- **Zylos Research:** Reflexion (NeurIPS 2023) demonstrated that storing verbal self-critiques in memory and retrying with that context achieved 91% pass@1 on HumanEval vs. GPT-4's 80% baseline. However, intrinsic self-correction (model judges itself) is unreliable. Grounded self-correction — anchored in execution, structured critics, or PRMs — is the reliable pattern. Process Reward Models (PRMs) score each step and provide actionable diagnostic signals; Outcome Reward Models (ORMs) score only the final answer and achieved only 66.77% accuracy in multi-step agentic RAG scenarios. — [https://zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm](https://zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm)

## Gotchas

- **Saturated benchmarks give false confidence.** MMLU, HumanEval, and MBPP no longer discriminate frontier models. Check which version of a benchmark you're running — MMLU-Pro, GPQA-Diamond, and ARC-AGI-2 replace their predecessors for current model comparisons.
- **LLM-as-judge accuracy degrades in expert domains.** ~80% agreement with human evaluators in general domains drops to 60-70% in legal, medical, or specialized technical contexts. Calibrate against domain experts before gating critical deployments.
- **Don't confuse pass@k with pass^k.** Reporting pass@3 as your reliability metric while ignoring pass^3 hides a 63 percentage-point gap for a 70%-per-trial agent. Report both.
- **Agent checkpointing is not the same as task completion.** Long-horizon agents (50+ step interactions) need state snapshots at intervals, not just a final success/fail flag. Without checkpointing, a 3-hour multi-step task has no recovery path when it fails at step 45.
