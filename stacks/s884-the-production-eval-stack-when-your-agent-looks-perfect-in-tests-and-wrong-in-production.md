# S-884 · The Production Eval Stack — When Your Agent Looks Perfect in Tests and Wrong in Production

Your agent scores 94% on your test set. In production, it loops on edge cases, misuses tools on unexpected API shapes, and silently fails in ways you only notice from customer complaints. The test set lied to you — not because it was wrong, but because it was frozen in time. The fix is not a bigger test set. It is a layered eval architecture that runs offline CI gates, live production traces, and a closed loop that promotes failures back into the training signal.

## Forces

- **Traditional metrics miss the process.** Accuracy, precision, and BLEU/ROUGE score only the final output. An agent can reach the right answer through the wrong steps — and that matters because the next input will expose the broken reasoning.
- **Agent-step compounding is structural math.** If each of 8 agent steps succeeds 95% of the time, end-to-end success is only 66%. Single-turn rubrics never catch this; trajectory scoring does.
- **The eval set ages at multiple speeds.** Dataset drift (weeks), tool-API drift (overnight), prompt drift (before lunch), retrieval-corpus drift (silent until re-index). The offline set that passed last week is measuring a version of the system that no longer exists.
- **Eval tooling fragmentation is the norm.** Every team picks a different combination — RAGAS for retrieval metrics, DeepEval or Braintrust for CI regression, LangSmith or Langfuse for tracing, custom LLM judges for offline scoring. No single tool covers the full lifecycle.

## The move

Build a three-tier eval architecture: **offline CI gate** (golden dataset + automated scoring), **online trace evaluator** (production sampling + LLM judge), and **drift detection + regression loop** (promote failures back into the offline set).

- **Golden dataset from production traces, not hand-authoring.** Start with the most failure-prone scenarios from live traffic. Synthetic data covers surface cases; production failures cover the messy middle where real systems break. Preserve every identified regression permanently in the set.
- **Score trajectories, not just final answers.** The Snowflake/TruLens GPA framework (Goal-Plan-Action) evaluates three reasoning phases: was the goal correctly understood, was the plan sound, and were the actions executed correctly. GPA judges outperform baseline LLM judges in benchmark testing.
- **Run a tiered scoring system.** Tier 1: exact-match or simple heuristics (fast, cheap, no LLM needed). Tier 2: LLM-as-judge on a gold reference set (requires human-annotated ground truth). Tier 3: distilled judge model calibrated against the gold set, used at scale. Block merges on Tier 1 regressions; use Tier 3 for production sampling.
- **Measure four dimensions simultaneously.** Task completion rate, tool-call accuracy, output quality, and failure-recovery behavior. No single framework covers all four — teams combine RAGAS (retrieval metrics), DeepEval or Braintrust (CI regression), LangSmith/Langfuse (execution traces), and custom LLM judges.
- **Gate releases on eval regressions.** Treat eval results as first-class deployment criteria, not post-launch quality theater. Braintrust and LangChain Engine both support merge-blocking based on eval score regression.
- **Calibrate LLM judges against human judgment.** Track inter-rater agreement (kappa). If the judge and humans diverge, the judge will mislead you at scale. Re-calibrate when the prompt, model, or product changes.
- **Monitor rolling means per route, per version, per cohort.** Page on degradation. Drift detection catches silent failures that individual eval runs miss — especially retrieval-corpus drift, which has no obvious signal until an unrelated query suddenly retrieves wrong chunks.

## Evidence

- **Snowflake Engineering Blog (Nov 2025):** The Agent GPA framework (Goal-Plan-Action), developed by Snowflake AI Research and open-sourced in TruLens, evaluates agents across goal alignment, plan quality, and action correctness — surfacing hallucinations, poor tool use, and missed plan steps that final-answer scoring misses. GPA judges consistently outperformed baseline LLM judges in benchmark testing. — [https://www.snowflake.com/en/blog/engineering/ai-agent-evaluation-gpa-framework](https://www.snowflake.com/en/blog/engineering/ai-agent-evaluation-gpa-framework)
- **FutureAGI Blog (April 2026):** Six drift modes age every offline eval set: dataset drift, tool-API drift, prompt drift, retrieval-corpus drift, user-distribution drift, and agent-step compounding. The core thesis: "The right unit of evaluation is the production trace, not the curated test case." The fix is a closed loop that promotes production failures back into the offline set. — [https://futureagi.com/blog/agent-passes-evals-fails-production-2026](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)
- **Inductivee Blog (Sept 2025):** Production teams evaluate across four simultaneous dimensions — task completion rate, tool-call accuracy, output quality, and failure-recovery behavior — using RAGAS for retrieval pipeline metrics, Braintrust for human-feedback-based quality scoring, and LangSmith for execution tracing. The foundation is a well-constructed golden dataset representing real production inputs. — [https://inductivee.com/blog/ai-agent-evaluation-testing-framework](https://inductivee.com/blog/ai-agent-evaluation-testing-framework)
- **InfoQ (March 2026):** Hybrid evaluation combining automated scoring (LLM-as-judge, trace analysis, load testing) with human judgment is non-negotiable for production agents. Operational constraints — latency, cost per task, token efficiency, tool reliability, policy compliance — are first-class evaluation targets, not afterthoughts. Safety, PII handling, and permission boundary testing complete the picture. — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Over-relying on synthetic data:** Synthetic coverage is cheaper but misses real ambiguity and real-world messiness. Production traces will surface failure modes that hand-authored tests never anticipate.
- **Calibrating once and forgetting:** An LLM judge calibrated against human annotation today diverges from human judgment tomorrow when the model, prompt, or product changes. Build recalibration into your release cycle, not your onboarding.
- **Scoring only the last message:** The final output is the least informative signal. An agent can fail the goal phase (misunderstanding intent), pass the plan phase, and fail the action phase — scoring only the output misses all three failure modes and gives you a false 90%.
- **Blocking CI on flaky LLM judges:** Tier 3 (distilled judge) and Tier 2 (LLM judge) scoring has intrinsic variance. Blocking merges on these tiers without a minimum kappa threshold will create a noisy pipeline that trains developers to ignore the gate.
