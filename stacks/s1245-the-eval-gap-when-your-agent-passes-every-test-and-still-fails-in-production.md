# S-1245 · The Eval Gap: When Your Agent Passes Every Test and Still Fails in Production

Your agent scored 94% on your eval suite. Three weeks into production, a finance team discovers it has been approving expense reports it shouldn't — quietly, consistently, correctly formatted. The benchmark said it was good. The benchmark was wrong about what "good" meant.

The eval gap is the systematic mismatch between what agent benchmarks measure and what production failure looks like. It is not a measurement error. It is a structural problem: agents behave unpredictably (like people), but teams still test them like code (like a function).

## Forces

- **Final-answer scoring hides path failures.** An agent can reach a correct output via a dangerous or inefficient path, and your pass/fail will miss it. A refund processed correctly after three wrong attempts costs more than the refund itself — in tokens, latency, and trust.
- **Trajectory quality is invisible to outcome metrics alone.** Loops, unnecessary tool calls, incorrect tool selection, and recovery from errors are all invisible to a "did it get the right answer?" check. Trajectory metrics (step efficiency, tool-call precision, recovery rate) are what separate a robust agent from a lucky one.
- **LLM-as-judge has no taste.** HN discussions on production AI agent principles surfaced a recurring finding: LLMs cannot reliably distinguish good critique from bad critique for non-trivial inputs. "LLMs don't have taste — it's easy to get an LLM to give praise, and easy to get it to give criticism, but getting it to praise good things and criticize bad things is currently impossible for non-trivial inputs." (colonCapitalDee, HN). A judge that cannot detect its own bad calls is a floor, not a ceiling.
- **Benchmarks saturate while real-world tasks don't.** SWE-Bench Verified climbed from 13% (early 2024) to 78% (May 2026) for top coding agents — yet real-world PR acceptance for the same agents sits at 35–50%. The benchmark measures what it can measure; production measures what you actually care about.
- **Operational constraints are first-class eval targets.** Latency, cost per task, token efficiency, tool reliability, and policy compliance are not afterthoughts. An agent that answers correctly in 30 seconds at $2.40 per query is not the same product as one that answers correctly in 3 minutes at $0.12. InfoQ's production AI evaluation analysis concluded: "Latency, cost per task, token efficiency, tool reliability, and policy compliance aren't afterthoughts — they are what determines whether a technically capable agent is viable at enterprise scale."

## The move

Build a three-layer eval stack that measures trajectory, not just outcome, and gate production on it.

- **Layer 1 — Final-answer eval:** Pass/fail on end-to-end task completion. Does the agent produce the correct output? This is your floor. Use it, but don't stop here.
- **Layer 2 — Trajectory eval:** Score the execution path. Count unnecessary tool calls, flag loops, measure tool-selection precision, and check recovery from errors. An agent that gets the right answer via a dangerous path scores lower than one that gets there cleanly. Confident AI's analysis recommends tracking: tool call accuracy, argument correctness, step efficiency, and handoff correctness between sub-agents.
- **Layer 3 — Per-turn production labels:** Label each turn in production traces (not just test runs) as correct/incorrect/recovering. These labels feed back into the eval set, into fine-tuning data, and into RL reward terms. The MorphLLM framework found a <90ms per-turn classifier latency makes continuous production labeling feasible. Every production failure becomes tomorrow's training signal.
- **Golden dataset across four buckets:** Futureagi.com's golden set design guide recommends four buckets: stratified production samples (60%), adversarial coverage (15%), edge cases (15%), and failure replays (10%). Labeler drift is the primary failure mode — strict annotation guidelines and multi-rater calibration (Cohen's kappa) are mandatory for the baseline to stay trustworthy.
- **LLM-as-judge with human calibration, not human replacement:** Run LLM-as-judge at scale for regression coverage. Run human rubrics on a 5–10% sample of traces to calibrate whether the judge is trustworthy. When the judge and the human disagree, trust the human and update the rubric.
- **Gate in CI/CD, not after deploy:** Integrate eval runs into the deployment pipeline. Catch regressions on every PR. Platforms like DeepEval and Maxim AI support `@observe` decorators and trajectory-level scoring directly in CI. The eval that runs only in staging is not an eval — it is a hope.

## Evidence

- **HN thread (11 months ago, 128 points):** "Principles for production AI agents" — discussion of why LLM-as-critic fails without taste, and why hybrid human+automated evaluation is necessary. Quote on LLM taste deficit widely cited in subsequent agent eval discussions. — [HN Thread](https://news.ycombinator.com/item?id=44712315)
- **NVIDIA Technical Blog (May 2026):** "Mastering Agentic Techniques: AI Agent Evaluation" — formal three-layer eval model distinguishing model evaluation (MMLU, GSM8K, HumanEval) from agent evaluation (GAIA, SWE-bench, WebArena). Recommends trajectory metrics (task success, tool-call precision, step efficiency) as primary agent signals. — [NVIDIA Blog](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation)
- **Presenc AI Research (May 2026):** Coding agent benchmarks showing SWE-Bench Verified at 74–78% (top agents) vs estimated real-world PR acceptance at 35–50%. Documents the benchmark-to-production gap empirically for coding agents — the most measurable agent category. — [Presenc AI](https://presenc.ai/research/coding-agent-benchmarks-2026)
- **Confident AI Blog (Apr 2026):** "AI Agent Evaluation: Metrics, Traces, Human Review, and Workflows" — three-layer eval framework (final-answer, trajectory, per-turn), golden dataset composition, and CI integration pattern. — [Confident AI](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)
- **InfoQ (Mar 2026):** "Evaluating AI Agents in Practice" — "Hybrid evaluation is non-negotiable. Automated scoring (LLM-as-a-judge, trace analysis, and load testing) gives you repeatability and scale. Human judgment captures what automation misses." — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **A green eval suite with no trajectory metrics is a false signal.** You know the agent produced the right answer. You don't know if it got there dangerously, expensively, or in a way that will fail on the next slightly-different input.
- **Synthetics accelerate coverage but cannot replace domain experts for high-stakes ground truth.** Tonic.ai and similar synthetic data pipelines solve the data scarcity problem, but the labels on safety-critical, regulatory-critical, or domain-expert-dependent cases still need human annotation. EU AI Act compliance, specifically, requires human-verified evaluation corpora — not just model-generated ones.
- **Model stochasticity means single-run pass/fail is unreliable.** Run eval scenarios 3–5 times and track pass rate, not just pass/fail. An agent that passes 60% of the time is a different product than one that passes 98% — even if their mean score looks identical.
- **Golden datasets drift.** User behavior, product features, and agent capabilities evolve. An eval set that accurately represents production in Q1 may be misleading by Q3. Version your golden sets and monitor distribution shift between eval inputs and actual production queries.
- **LLM-as-judge judges itself poorly on non-trivial cases.** If you cannot get a judge that criticizes bad work and praises good work for your specific domain, do not trust it as the source of truth. Use it as a filter, not a verdict.
